"""Original documents next to the ALM items: page images, item locations, revision-to-revision compare.

Every real import keeps a copy of the source file (.alm/sources/<import_id>/<file>). PDF files are shown as page
images; DOC/DOCX/RTF/ODT are converted to PDF with LibreOffice when it is installed, otherwise a structural HTML
rendering of the parsed blocks is used. Each item of the document is located in the original: the text of the item
*as it was in that revision* is searched character by character (whitespace-insensitive) in the page text, in
document order, using the page hint from the import (p.11 / p.26-27) — so a requirement that wraps over lines,
table cells or a page break is still highlighted as a whole. Locations are cached per import.
"""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS source_cache (import_id TEXT NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL, at REAL NOT NULL,
                                         PRIMARY KEY (import_id, kind));
"""
OFFICE = {".doc", ".docx", ".rtf", ".odt"}
WS = re.compile(r"[\W_]+")      # compare letters and digits only: PDFs drop or move dashes, arrows, pipes


def init(repo):
    repo.con.executescript(SCHEMA)
    repo.con.commit()


def _dir(repo, iid: str) -> Path:
    if not re.match(r"^[0-9a-f]{6,32}$", iid or ""):
        raise KeyError("잘못된 import id")
    return repo.dir / "sources" / iid


def keep_source(repo, import_id: str, path: Path) -> None:
    """Called after a real import: keep the exact file that produced this revision."""
    try:
        d = _dir(repo, import_id)
        d.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, d / Path(path).name)
    except OSError:
        pass


def _import(repo, iid: str) -> dict:
    for i in repo.imports():
        if i["import_id"] == iid:
            return i
    raise KeyError(f"임포트 {iid} 없음")


def source_file(repo, iid: str) -> Path | None:
    d = _dir(repo, iid)
    if d.exists():
        fs = sorted(f for f in d.iterdir() if f.is_file() and not f.name.startswith("_"))
        if fs:
            return fs[0]
    p = Path(_import(repo, iid)["path"] or "")
    return p if p.is_file() else None


def attach(repo, iid: str, name: str, data: bytes) -> dict:
    _import(repo, iid)
    ext = Path(name).suffix.lower()
    if ext not in OFFICE | {".pdf"}:
        raise ValueError("PDF·DOC·DOCX·RTF·ODT 만 올릴 수 있습니다")
    d = _dir(repo, iid)
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    (d / Path(name).name).write_bytes(data)
    repo.con.execute("DELETE FROM source_cache WHERE import_id=?", (iid,))
    repo.con.commit()
    return meta(repo, iid)


def _pdf(repo, iid: str) -> Path | None:
    """PDF to display: the source itself, or a LibreOffice conversion (cached)."""
    src = source_file(repo, iid)
    if not src:
        return None
    if src.suffix.lower() == ".pdf":
        return src
    if src.suffix.lower() in OFFICE:
        d = _dir(repo, iid)
        d.mkdir(parents=True, exist_ok=True)
        out = d / "_view.pdf"
        if out.exists():
            return out
        from .assets import convert_with_soffice
        tmp = convert_with_soffice(src, "pdf", d / "_conv")
        if tmp and tmp.exists():
            shutil.move(str(tmp), out)
            shutil.rmtree(d / "_conv", ignore_errors=True)
            return out
    return None


def meta(repo, iid: str) -> dict:
    imp = _import(repo, iid)
    src = source_file(repo, iid)
    out = {"import_id": iid, "doc": imp["doc"], "rev": imp["rev"], "at": imp["at"], "file": src.name if src else "",
           "kind": "none", "pages": []}
    if not src:
        out["note"] = "원문 파일이 보관되어 있지 않습니다 (이 기능 이전에 가져온 개정). 같은 파일을 올리면 대조할 수 있습니다."
        return out
    pdf = _pdf(repo, iid)
    if pdf:
        import pymupdf as fitz
        with fitz.open(pdf) as d:
            out["pages"] = [{"w": round(p.rect.width, 1), "h": round(p.rect.height, 1)} for p in d]
        out["kind"] = "pdf"
        if src.suffix.lower() != ".pdf":
            out["note"] = f"{src.suffix.upper()[1:]} 을 PDF 로 변환해 표시합니다 (LibreOffice)."
    else:
        out["kind"] = "html"
        out["note"] = "LibreOffice 가 없어 원문을 구조 보기(문단·표)로 표시합니다. 쪽 모양 그대로 보려면 LibreOffice 를 설치하세요."
    return out


def page_png(repo, iid: str, n: int, dpi: int = 110) -> bytes:
    dpi = max(60, min(200, int(dpi)))
    d = _dir(repo, iid) / "_pages"
    f = d / f"{n}_{dpi}.png"
    if f.exists():
        return f.read_bytes()
    pdf = _pdf(repo, iid)
    if not pdf:
        raise KeyError("PDF 원문 없음")
    import pymupdf as fitz
    with fitz.open(pdf) as doc:
        if not 0 <= n < len(doc):
            raise KeyError("페이지 없음")
        png = doc[n].get_pixmap(dpi=dpi).tobytes("png")
    d.mkdir(parents=True, exist_ok=True)
    f.write_bytes(png)
    return png


# ---------------------------------------------------------------- items as they were in a revision
def items_at(repo, iid: str) -> list[dict]:
    imp = _import(repo, iid)
    t = imp["at"] + 1
    out = []
    for it in repo.items(doc=imp["doc"], include_deleted=True):
        if it["source_loc"] == "manual" or it["source_loc"].startswith("derived:"):
            continue
        h = repo.con.execute("SELECT version, text, status, import_id FROM history WHERE id=? AND at<=? ORDER BY version DESC LIMIT 1",
                             (it["id"], t)).fetchone()
        if not h or h["status"] == "deleted":
            continue
        changed = repo.con.execute("SELECT change FROM history WHERE id=? AND import_id=? ORDER BY version DESC LIMIT 1",
                                   (it["id"], iid)).fetchone()
        out.append({"id": it["id"], "type": it["type"], "native_id": it["attrs"].get("native_id", ""), "text": h["text"],
                    "version": h["version"], "status": h["status"], "loc": it["source_loc"], "ord": it["ord"],
                    "section": it["section"], "change": changed["change"] if changed else ""})
    out.sort(key=lambda x: x["ord"])
    return out


# ---------------------------------------------------------------- locating items in the PDF
def _page_chars(page) -> tuple[str, list]:
    s, boxes = [], []
    raw = page.get_text("rawdict")
    for b in raw.get("blocks", []):
        for ln in b.get("lines", []):
            for sp in ln.get("spans", []):
                for ch in sp.get("chars", []):
                    c = ch["c"]
                    if c.strip() and not WS.fullmatch(c):
                        s.append(c); boxes.append(ch["bbox"])
    return "".join(s), boxes


def _norm(s: str) -> str:
    return WS.sub("", s or "")


def _merge(boxes: list) -> list:
    """Character boxes -> one rectangle per text line."""
    lines = []
    for x0, y0, x1, y1 in boxes:
        for L in lines:
            if abs(L[1] - y0) < 3 and abs(L[3] - y1) < 3 and x0 - L[2] < 40:
                L[0], L[2] = min(L[0], x0), max(L[2], x1); L[1], L[3] = min(L[1], y0), max(L[3], y1)
                break
        else:
            lines.append([x0, y0, x1, y1])
    return [[round(v, 1) for v in L] for L in lines]


def _hint(loc: str) -> list[int]:
    m = re.match(r"p\.(\d+)(?:-(\d+))?", loc or "")
    if not m:
        return []
    a = int(m.group(1)) - 1
    b = int(m.group(2)) - 1 if m.group(2) else a
    return list(range(a, b + 1))


def locate(repo, iid: str, force: bool = False) -> dict:
    init(repo)
    if not force:
        r = repo.con.execute("SELECT data FROM source_cache WHERE import_id=? AND kind='locs'", (iid,)).fetchone()
        if r:
            return json.loads(r["data"])
    items = items_at(repo, iid)
    pdf = _pdf(repo, iid)
    out = {"items": items, "locs": {}, "missing": []}
    if not pdf:
        return out
    import pymupdf as fitz
    with fitz.open(pdf) as doc:
        pages = [_page_chars(p) for p in doc]
    # concatenated stream so a requirement may run over a page break
    stream, owner, offs = "", [], []
    for pi, (s, bx) in enumerate(pages):
        offs.append(len(stream))
        stream += s
        owner += [(pi, b) for b in bx]
    cursor = 0
    for it in items:
        if it["type"] == "TBL":                                # cells are joined with " | " in the item text
            rows = [_norm(r.replace("|", "")) for r in it["text"].split("\n") if r.strip()]
            t = "".join(rows)
            head, tail = rows[0][:24], rows[-1][-14:]
        else:
            t = _norm(it["text"])
            head, tail = t[:min(24, len(t))], t[-min(14, len(t)):]
        if len(t) < 4 or it["type"] in ("FIG",):
            continue
        hint = _hint(it["loc"])
        starts = []
        for p in hint:
            if p < len(offs):
                lo = offs[p]; hi = offs[p + 1] if p + 1 < len(offs) else len(stream)
                k = stream.find(head, lo, hi)
                if k >= 0:
                    starts.append(k)
        if not starts:
            k = stream.find(head, cursor)
            if k < 0:
                k = stream.find(head)
            if k >= 0:
                starts.append(k)
        if not starts and it["type"] == "HDG":                 # Word auto-numbering is not in the rendered text
            t = _norm(re.sub(r"^[\d.\s]+", "", it["text"])); head, tail = t[:24], t[-14:]
            k = stream.find(head, cursor) if head else -1
            if k >= 0:
                starts.append(k)
        if not starts:
            out["missing"].append(it["id"]); continue
        k = starts[0]
        e = stream.find(tail, k + len(head) - 1, k + int(len(t) * 1.6) + 60)
        end = e + len(tail) if e >= 0 else min(len(stream), k + len(t))
        spans = {}
        for pi, b in owner[k:end]:
            spans.setdefault(pi, []).append(b)
        nid = _norm(it["native_id"])
        if nid:                                              # table rows: highlight the ID cell too
            j = stream.rfind(nid, max(0, k - 120), k + 1)
            if j >= 0:
                for pi, b in owner[j:j + len(nid)]:
                    spans.setdefault(pi, []).append(b)
        out["locs"][it["id"]] = [{"page": pi, "rects": _merge(bx)} for pi, bx in sorted(spans.items())]
        cursor = k
    repo.con.execute("INSERT INTO source_cache VALUES(?,?,?,?) ON CONFLICT(import_id, kind) DO UPDATE SET data=excluded.data, at=excluded.at",
                     (iid, "locs", json.dumps(out, ensure_ascii=False), time.time()))
    repo.con.commit()
    return out


# ---------------------------------------------------------------- structural HTML when no PDF can be made
def html(repo, iid: str) -> dict:
    from .importer import parse_any
    src = source_file(repo, iid)
    if not src:
        raise KeyError("원문 없음")
    blocks = parse_any(src)
    items = items_at(repo, iid)
    by_loc = {}
    for it in items:
        base = it["loc"].split(" row")[0]
        row = re.search(r"row (\d+)", it["loc"])
        by_loc.setdefault(base, []).append((it["id"], int(row.group(1)) if row else None))
    esc = lambda s: (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    parts = []
    for b in blocks:
        ids = by_loc.get(b.loc, [])
        whole = [i for i, r in ids if r is None]
        attr = f' data-items="{" ".join(whole)}"' if whole else ""
        if b.kind == "heading":
            parts.append(f'<h{min(4, b.level + 1)} class="sh"{attr}>{esc(b.text)}</h{min(4, b.level + 1)}>')
        elif b.kind == "table":
            rows = []
            rowmap = {r: i for i, r in ids if r is not None}
            for ri, r in enumerate(b.grid):
                rid = rowmap.get(ri) or rowmap.get(ri + 1)
                cells = "".join(f'<td{" rowspan=%d" % c["rs"] if c.get("rs", 1) > 1 else ""}{" colspan=%d" % c["cs"] if c.get("cs", 1) > 1 else ""}>{esc(c["t"])}</td>'
                                for c in r if not c.get("skip"))
                rows.append(f'<tr{f" data-items={chr(34)}{rid}{chr(34)}" if rid else ""}>{cells}</tr>')
            parts.append(f'<table class="g"{attr}>{"".join(rows)}</table>')
        elif b.kind == "figure":
            parts.append(f'<div class="sfig muted">[그림] {esc(b.caption)}</div>')
        else:
            parts.append(f'<p class="sp"{attr}>{esc(b.text)}</p>')
    return {"html": "".join(parts), "items": items}


def sources_for(repo, doc: str) -> list[dict]:
    out = []
    for i in repo.imports():
        if i["doc"] != doc:
            continue
        src = source_file(repo, i["import_id"])
        out.append({"import_id": i["import_id"], "rev": i["rev"], "at": i["at"], "file": src.name if src else Path(i["path"] or "").name,
                    "available": bool(src)})
    return sorted(out, key=lambda x: x["at"], reverse=True)
