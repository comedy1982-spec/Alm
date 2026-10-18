"""Import pipeline: parse → build candidate items → (optional AI refine) → match against the
previous revision → assign stable IDs → write items, history and suspect flags."""
from __future__ import annotations

import difflib
import hashlib
import re
import tempfile
import time
import uuid
from pathlib import Path

from .assets import convert_with_soffice, save_asset
from .blocks import Block
from .classify import Analyzer, quantities
from .db import Repo

REQ_TYPES = {"CRS", "SYS2", "SWE1", "HSI", "HWE1"}
META_RE = re.compile(r"^\s*(ASIL\s+\S+\s*·\s*)?(검증|근거|비고)\s*[:：]")


# ---------------------------------------------------------------- parsing
_OWN_ID_SPLIT = re.compile(r"\s*(?=\[[A-Z][A-Z0-9]{1,10}(?:[-_][A-Z0-9]{1,10}){0,3}[-_]\d{1,6}\])")


def parse_any(path: Path) -> list[Block]:
    return _normalize_blocks(_parse_raw(path))


def _normalize_blocks(blocks: list[Block]) -> list[Block]:
    """Repairs that PDF extraction typically needs (harmless for DOCX):
    * a paragraph that swallowed the next bracketed requirement ("검증: HIL[REQ-X-002] ...") is split
      so each "[ID] ..." statement is its own block;
    * empty leading table rows (a header lost at a page edge) are dropped so the header is found."""
    out: list[Block] = []
    for b in blocks:
        if b.kind == "para" and b.text:
            parts = [p for p in _OWN_ID_SPLIT.split(b.text) if p.strip()]
            if len(parts) > 1:
                for p in parts:
                    nb = Block(kind="para", text=p.strip(), loc=b.loc, style=b.style, list_level=b.list_level)
                    out.append(nb)
                continue
        if b.kind == "table" and b.grid:
            while len(b.grid) > 2 and all(not (c.get("t") or "").strip() for c in b.grid[0]):
                b.grid = b.grid[1:]
            _restore_lost_header(b)
        out.append(b)
    return out


_ID_CELL = re.compile(r"^[A-Z][A-Z0-9]{1,10}(?:[-_][A-Z0-9]{1,10}){0,3}[-_]\d{1,6}$")


def _restore_lost_header(b: Block) -> None:
    """A requirement table whose header row was lost (page break in a PDF) starts directly with data
    rows "REQ-X-001 | 문장 | ...". Put a synthetic header back so the table is still read row by row."""
    rows = [r for r in b.grid if any((c.get("t") or "").strip() for c in r)]
    if len(rows) < 2 or not _ID_CELL.match((b.grid[0][0].get("t") or "").strip()):
        return
    idlike = sum(1 for r in rows if _ID_CELL.match((r[0].get("t") or "").strip()))
    if idlike < 0.6 * len(rows):
        return
    ncol = len(b.grid[0])
    lens = [sum(len((r[k].get("t") or "")) for r in rows if k < len(r)) for k in range(ncol)]
    text_col = max(range(1, ncol), key=lambda k: lens[k]) if ncol > 1 else 0
    names = ["ID"] + [f"열{k + 1}" for k in range(1, ncol)]
    names[text_col] = "요구사항"
    b.grid = [[{"t": n, "rs": 1, "cs": 1} for n in names]] + b.grid


def _parse_raw(path: Path) -> list[Block]:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        from .parse_docx import parse_docx
        return parse_docx(path)
    if suffix == ".pdf":
        from .parse_pdf import parse_pdf
        return parse_pdf(path)
    if suffix in (".doc", ".rtf", ".odt", ".docm", ".dotx", ".dot"):
        with tempfile.TemporaryDirectory() as td:
            out = convert_with_soffice(path, "docx:MS Word 2007 XML", Path(td))
            if not out:
                raise RuntimeError(f"{path.name}: LibreOffice(soffice)로 DOCX 변환 실패")
            from .parse_docx import parse_docx
            return parse_docx(out)
    if suffix in (".md", ".txt"):
        return _parse_text(path.read_text(encoding="utf-8"))
    raise RuntimeError(f"지원하지 않는 형식: {suffix} (docx, pdf, doc, rtf, odt, md, txt)")


def _parse_text(src: str) -> list[Block]:
    blocks, buf = [], []
    for i, line in enumerate(src.splitlines()):
        m = re.match(r"^(#{1,6})\s+(?:(\d+(?:\.\d+)*)\.?\s+)?(.*)", line)
        if m:
            if buf:
                blocks.append(Block(kind="para", text=" ".join(buf), loc=f"line {i}")); buf = []
            lvl = len(m.group(1))
            blocks.append(Block(kind="heading", text=m.group(3), number=m.group(2) or "", level=lvl, loc=f"line {i + 1}"))
        elif not line.strip():
            if buf:
                blocks.append(Block(kind="para", text=" ".join(buf), loc=f"line {i}")); buf = []
        else:
            buf.append(line.strip())
    if buf:
        blocks.append(Block(kind="para", text=" ".join(buf), loc="end"))
    return blocks


# ---------------------------------------------------------------- helpers
def normalize(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[\s ]+", " ", s)
    s = re.sub(r"[^\w가-힣%.°µμ ]", "", s)
    return s.strip()


def fingerprint(s: str) -> str:
    return hashlib.sha1(normalize(s).encode("utf-8")).hexdigest()[:16]


def bigrams(s: str) -> set:
    s = normalize(s).replace(" ", "")
    return {s[i:i + 2] for i in range(len(s) - 1)} or {s}


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, normalize(a), normalize(b), autojunk=False).ratio()


def _header_row(grid) -> list[str]:
    return [c["t"].strip().lower() for c in grid[0]] if grid else []


def _col_index(headers: list[str], words: list[str]) -> int:
    for i, h in enumerate(headers):
        hc = h.replace("\n", " ")
        for w in words:
            if hc == w or hc.startswith(w + " ") or w in hc.split() or (len(w) > 2 and w in hc):
                return i
    return -1


def table_kind(grid, cfg, an: "Analyzer | None" = None) -> str:
    if len(grid) < 2:
        return "plain"
    headers = _header_row(grid)
    ci = _col_index(headers, cfg["req_table_headers"])
    if ci >= 0:
        # a requirement table only when most rows of that column read like requirements
        rows = [r[ci]["t"] for r in grid[1:] if ci < len(r) and r[ci]["t"].strip()]
        if an is None or (rows and sum(1 for t in rows if an.is_requirement(t)) >= max(1, len(rows) * 0.5)):
            return "requirements"
    pins = sum(1 for h in headers if any(w in h for w in cfg["pin_table_headers"]))
    if pins >= 2:
        return "pinmap"
    return "plain"


def table_text(grid) -> str:
    return "\n".join(" | ".join(c["t"] for c in row) for row in grid)


# ---------------------------------------------------------------- candidates
def build_candidates(blocks: list[Block], cfg: dict, mode: str, repo: Repo, doc: str) -> list[dict]:
    an = Analyzer(cfg)
    cands: list[dict] = []
    path: list[tuple[int, str]] = []   # heading stack (level, "3.2 Title")

    def section() -> str:
        return path[-1][1] if path else ""

    def section_path() -> str:
        return " > ".join(p[1] for p in path)

    def req_item(text: str, loc: str, extra_attrs: dict | None = None, forced_type: str | None = None) -> dict:
        nid = an.native_id(text)
        body = an.strip_native_id(text, nid)
        if forced_type:
            typ, conf = forced_type, 1.0
        elif mode == "crs":
            typ, conf = "CRS", 1.0
        elif mode in ("sys2", "swe1"):
            typ, conf = mode.upper(), 1.0
        else:
            typ, conf = an.level(body, section_path())
        attrs = {"level_confidence": conf, "quantities": quantities(body)}
        if nid:
            attrs["native_id"] = nid
        if extra_attrs:
            attrs.update(extra_attrs)
        dom = "HSI" if typ == "HSI" else an.domain(body, section(), nid)
        return {"kind": "req", "type": typ, "domain": dom, "title": body[:80], "text": body,
                "attrs": attrs, "lint": an.lint(body, typ), "section": section_path(), "source_loc": loc}

    for b in blocks:
        if b.kind == "heading":
            while path and path[-1][0] >= b.level:
                path.pop()
            label = f"{b.number} {b.text}".strip()
            path.append((b.level, label))
            cands.append({"kind": "hdg", "type": "HDG", "domain": "GEN", "title": b.text, "text": label,
                          "attrs": {"level": b.level, "number": b.number}, "section": section_path(),
                          "source_loc": b.loc})
        elif b.kind == "para":
            meta = META_RE.match(b.text) if mode != "info" else None
            last_req = next((c for c in reversed(cands[-3:]) if c["kind"] == "req"), None)
            if meta and last_req is not None:
                # "ASIL B · 검증: HIL · 근거: REQ-PWR-009" style line right after a requirement
                a = last_req["attrs"]
                for key, val in re.findall(r"(ASIL|검증|근거|비고)\s*[:：]?\s*([^·]+)", b.text):
                    val = val.strip()
                    if key == "ASIL":
                        a["asil"] = val.split()[0]
                    elif key == "검증":
                        a["verification_method"] = val
                    elif key == "근거":
                        a["rationale"] = val
                    else:
                        a["note"] = val
                refs = [r for r in an.native_re.findall(b.text) if r != a.get("native_id")]
                if refs:
                    a["refs"] = sorted(set(a.get("refs", []) + refs))
                cands.append({"kind": "info", "type": "INFO", "domain": "GEN", "title": b.text[:80], "text": b.text,
                              "attrs": {"meta_of": True}, "section": section_path(), "source_loc": b.loc})
                continue
            if mode != "info" and an.is_requirement(b.text):
                for part in an.split_atomic(b.text):
                    if an.is_requirement(part):
                        cands.append(req_item(part, b.loc))
                    else:
                        cands.append({"kind": "info", "type": "INFO", "domain": "GEN", "title": part[:80],
                                      "text": part, "attrs": {}, "section": section_path(), "source_loc": b.loc})
            else:
                cands.append({"kind": "info", "type": "INFO", "domain": "GEN", "title": b.text[:80], "text": b.text,
                              "attrs": {"list_level": b.list_level} if b.list_level >= 0 else {},
                              "section": section_path(), "source_loc": b.loc})
        elif b.kind == "table":
            kind = table_kind(b.grid, cfg, an) if mode != "info" else "plain"
            headers_raw = [c["t"] for c in b.grid[0]] if b.grid else []
            if kind == "requirements":
                headers = _header_row(b.grid)
                ci_text = _col_index(headers, cfg["req_table_headers"])
                ci_id = _col_index(headers, cfg["id_table_headers"])
                for r_i, row in enumerate(b.grid[1:], start=2):
                    vals = [c["t"] for c in row]
                    text = vals[ci_text].strip() if ci_text < len(vals) else ""
                    if not text or all(c.get("skip") for c in row) or not an.is_requirement(text):
                        continue
                    fields = {headers_raw[k]: v for k, v in enumerate(vals) if k not in (ci_text, ci_id) and v and k < len(headers_raw)}
                    extra = {"fields": fields, "table_caption": b.caption, "table_row": r_i}
                    it = req_item(text, f"{b.loc} row {r_i}", extra)
                    if ci_id >= 0 and vals[ci_id].strip():
                        it["attrs"]["native_id"] = vals[ci_id].strip()
                    cands.append(it)
            else:
                tid = {"kind": "tbl", "type": "TBL", "domain": "GEN", "title": b.caption or "표",
                       "text": table_text(b.grid), "attrs": {"grid": b.grid, "caption": b.caption, "table_kind": kind},
                       "section": section_path(), "source_loc": b.loc}
                cands.append(tid)
                if kind == "pinmap":
                    for r_i, row in enumerate(b.grid[1:], start=2):
                        vals = [c["t"] for c in row]
                        if not any(vals):
                            continue
                        fields = {headers_raw[k]: v for k, v in enumerate(vals) if v and k < len(headers_raw)}
                        text = " / ".join(f"{k}: {v}" for k, v in fields.items())
                        it = req_item(text, f"{b.loc} row {r_i}",
                                      {"fields": fields, "table_caption": b.caption, "table_row": r_i}, forced_type="HSI")
                        it["lint"] = []
                        it["attrs"].pop("native_id", None)
                        cands.append(it)
        elif b.kind == "figure":
            attrs = {"caption": b.caption, "labels": b.text, "render": b.style}
            if b.image:
                attrs.update(save_asset(repo.assets, b.image, b.image_ext))
                fp_src = attrs["sha"]
            else:
                attrs["missing_image"] = True
                fp_src = b.text or b.caption
            cands.append({"kind": "fig", "type": "FIG", "domain": "GEN", "title": b.caption or "그림",
                          "text": b.caption or "", "attrs": attrs, "section": section_path(),
                          "source_loc": b.loc, "fp_src": fp_src})
    for i, c in enumerate(cands):
        c["ord"] = (i + 1) * 10
        c["doc"] = doc
        c["fingerprint"] = fingerprint(c.pop("fp_src", None) or c["text"])
    return cands


# ---------------------------------------------------------------- matching
def match(cands: list[dict], olds: list[dict], threshold: float) -> dict[int, str]:
    """Map candidate index -> existing item id. Matching never crosses kinds."""
    kind_of = {"HDG": "hdg", "INFO": "info", "TBL": "tbl", "FIG": "fig"}
    result: dict[int, str] = {}
    used: set[str] = set()
    by_kind: dict[str, list[dict]] = {}
    for o in olds:
        by_kind.setdefault(kind_of.get(o["type"], "req"), []).append(o)

    # 1) native IDs from the customer document
    for i, c in enumerate(cands):
        nid = c["attrs"].get("native_id")
        if not nid:
            continue
        for o in by_kind.get(c["kind"], []):
            if o["id"] not in used and o["attrs"].get("native_id") == nid and o["status"] != "deleted":
                result[i] = o["id"]; used.add(o["id"]); break
    # 2) identical content (also restores items deleted in an earlier revision)
    for i, c in enumerate(cands):
        if i in result:
            continue
        for o in sorted(by_kind.get(c["kind"], []), key=lambda o: o["status"] == "deleted"):
            if o["id"] not in used and o["fingerprint"] == c["fingerprint"]:
                result[i] = o["id"]; used.add(o["id"]); break
    # 3) similar content: score all pairs on bigram Jaccard, verify top candidates with difflib
    pairs = []
    for i, c in enumerate(cands):
        if i in result or c["kind"] in ("fig",):
            continue
        cb = bigrams(c["text"])
        scored = []
        for o in by_kind.get(c["kind"], []):
            if o["id"] in used or o["status"] == "deleted":
                continue
            ob = bigrams(o["text"])
            j = len(cb & ob) / max(1, len(cb | ob))
            if j > 0.3:
                scored.append((j, o))
        scored.sort(key=lambda x: -x[0])
        for _, o in scored[:3]:
            s = similarity(c["text"], o["text"])
            if c["section"] and c["section"] == o["section"]:
                s += 0.05
            if s >= threshold:
                pairs.append((s, i, o["id"]))
    for s, i, oid in sorted(pairs, key=lambda p: -p[0]):
        if i not in result and oid not in used:
            result[i] = oid; used.add(oid)
    # 4) figures: same caption in the same section counts as the same figure with a new image
    for i, c in enumerate(cands):
        if i in result or c["kind"] != "fig" or not c["attrs"].get("caption"):
            continue
        for o in by_kind.get("fig", []):
            if o["id"] not in used and o["status"] != "deleted" and o["attrs"].get("caption") == c["attrs"]["caption"]:
                result[i] = o["id"]; used.add(o["id"]); break
    return result


# ---------------------------------------------------------------- main entry
def import_document(repo: Repo, cfg: dict, path: str | Path, doc: str | None = None, rev: str = "",
                    mode: str = "srs", dry_run: bool = False, ai: bool = False, user: str = "import") -> dict:
    path = Path(path)
    doc = doc or path.stem
    rev = rev or time.strftime("%Y%m%d-%H%M")
    import_id = uuid.uuid4().hex[:12]
    blocks = parse_any(path)
    cands = build_candidates(blocks, cfg, mode, repo, doc)

    if ai:
        from .llm import refine_candidates, describe_figures
        cands = refine_candidates(cands, cfg)
        describe_figures(cands, cfg, repo.assets)

    # items added by hand (tests, architecture, notes) live in the doc view but are never matched/deleted by an import
    olds = [o for o in repo.items(doc=doc, include_deleted=True)
            if o["source_loc"] != "manual" and not o["source_loc"].startswith("derived:")]
    matches = match(cands, olds, cfg["match_threshold"])
    old_by_id = {o["id"]: o for o in olds}
    id_fmt = cfg["id_format"]
    summary = {"doc": doc, "rev": rev, "import_id": import_id, "file": path.name, "blocks": len(blocks),
               "new": [], "modified": [], "unchanged": 0, "deleted": [], "restored": [], "by_type": {}, "details": []}
    det = summary["details"]

    for i, c in enumerate(cands):
        typ = c["type"]
        summary["by_type"][typ] = summary["by_type"].get(typ, 0) + 1
        base = {"title": c["title"], "text": c["text"], "attrs": c["attrs"], "lint": c["lint"] if "lint" in c else [],
                "section": c["section"], "source_loc": c["source_loc"], "ord": c["ord"], "doc_rev": rev,
                "fingerprint": c["fingerprint"]}
        if i in matches:
            oid = matches[i]
            o = old_by_id[oid]
            # keep manual decisions: type/domain/status of the existing item stay, fields merge
            merged_attrs = {**o["attrs"], **c["attrs"]}
            for keep in ("custom",):
                if keep in o["attrs"]:
                    merged_attrs[keep] = o["attrs"][keep]
            if o["status"] == "deleted":
                repo.update(oid, {**base, "attrs": merged_attrs, "status": "draft"}, change="restored", import_id=import_id, by=user)
                summary["restored"].append(oid)
                det.append({"id": oid, "change": "restored", "type": o["type"], "text": c["text"], "section": c["section"]})
            elif o["fingerprint"] == c["fingerprint"] and o["text"] == c["text"]:
                repo.update(oid, {"ord": c["ord"], "section": c["section"], "source_loc": c["source_loc"],
                                  "doc_rev": rev, "attrs": merged_attrs, "lint": base["lint"]},
                            bump_version=False)
                summary["unchanged"] += 1
            else:
                status = "draft" if o["status"] == "approved" else o["status"]
                prev = {"prev_text": o["text"]}
                if c["kind"] == "fig" and o["attrs"].get("file") != c["attrs"].get("file"):
                    prev["prev_file"] = o["attrs"].get("file")
                changes = {**base, "attrs": {**merged_attrs, **prev}, "status": status}
                repo.update(oid, changes, change="modified", import_id=import_id, by=user)
                summary["modified"].append(oid)
                det.append({"id": oid, "change": "modified", "type": o["type"], "text": c["text"], "prev_text": o["text"],
                            "section": c["section"], "was_approved": o["status"] == "approved",
                            "dependents": [l["src"] for l in repo.links(oid) if l["dst"] == oid]})
        else:
            tdef = cfg["types"][typ]
            fmt = id_fmt if ((typ in REQ_TYPES or typ.endswith("_TC")) and c["domain"] != typ) else cfg["id_format_no_domain"]
            new_id = repo.next_id(fmt, tdef["prefix"], c["domain"], cfg)
            repo.insert({"id": new_id, "type": typ, "domain": c["domain"], "doc": doc, **base},
                        import_id=import_id, by=user)
            summary["new"].append(new_id)
            if typ not in ("HDG", "INFO"):
                det.append({"id": new_id, "change": "new", "type": typ, "text": c["text"], "section": c["section"]})

    # references the author wrote ("근거: REQ-PWR-009") become trace links inside this document
    ref_links = 0
    from .audit import allowed_roles
    by_native = {}
    for it in repo.items(doc=doc):
        if it["attrs"].get("native_id") and it["type"] in REQ_TYPES:
            by_native.setdefault(it["attrs"]["native_id"], it)
    for it in repo.items(doc=doc):
        for ref in it["attrs"].get("refs", []):
            tgt = by_native.get(ref)
            if not tgt or tgt["id"] == it["id"]:
                continue
            roles = [r for r in allowed_roles(cfg, it["type"], tgt["type"]) if r != "relates"]
            if roles:
                repo.add_link(it["id"], roles[0], tgt["id"], state="confirmed", note="원문 참조"); ref_links += 1
            elif it["type"] == tgt["type"]:
                repo.add_link(it["id"], "relates", tgt["id"], state="confirmed", note="원문 참조"); ref_links += 1
    summary["ref_links"] = ref_links

    matched_ids = set(matches.values())
    for o in olds:
        if o["id"] not in matched_ids and o["status"] != "deleted":
            repo.update(o["id"], {"status": "deleted", "doc_rev": rev}, change="deleted", import_id=import_id, by=user)
            summary["deleted"].append(o["id"])
            det.append({"id": o["id"], "change": "deleted", "type": o["type"], "prev_text": o["text"], "section": o["section"]})

    summary["suspect_links"] = repo.con.execute("SELECT COUNT(*) FROM links WHERE suspect=1").fetchone()[0]
    if dry_run:
        repo.con.rollback()
        summary["dry_run"] = True
    else:
        repo.record_import(import_id, doc, rev, path, {k: (len(v) if isinstance(v, list) else v)
                                                      for k, v in summary.items() if k != "details"})
        repo.commit()
    return summary
