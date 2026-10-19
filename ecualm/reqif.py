"""ReqIF 1.2 (OMG, the DOORS / DOORS Next / Polarion / Codebeamer / PTC exchange format) import and export.

Import  .reqif / .reqifz  ->  Blocks for the normal import pipeline. Every SPEC-OBJECT keeps its IDENTIFIER
        (attrs.reqif_id) and its foreign ID (attrs.native_id), so a later revision of the same exchange file is
        matched object by object, and all other attributes land in attrs.fields.
Export  * reply      the customer's own file with the supplier attributes (compliance / comment / reference)
                     filled in; everything else (types, IDs, hierarchy, embedded files, tool extensions) stays as
                     the customer sent it, so it can be merged back into DOORS / Polarion.
        * generic    any ALM document or stage as a fresh ReqIF (headings, requirements, tables, figures,
                     trace links as SPEC-RELATIONs).
"""
from __future__ import annotations

import io
import re
import time
import uuid
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath

from .blocks import Block

NS = "http://www.omg.org/spec/ReqIF/20110401/reqif.xsd"
XH = "http://www.w3.org/1999/xhtml"
SUFFIXES = (".reqif", ".reqifz")
MAX_UNZIP = 500 * 1024 * 1024
IMG_TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg", "image/gif": "gif", "image/bmp": "bmp",
             "image/x-emf": "emf", "image/emf": "emf", "image/x-wmf": "wmf", "image/wmf": "wmf", "image/svg+xml": "svg"}

# attribute names used by the common tools
TEXT_ATTRS = ["ReqIF.Text", "Object Text", "Primary Text", "Text", "ReqIF.Description", "Description", "본문", "요구사항"]
HEAD_ATTRS = ["ReqIF.ChapterName", "Object Heading", "Heading", "ReqIF.Name", "Title", "Name", "제목"]
ID_ATTRS = ["ReqIF.ForeignID", "Req ID", "Requirement ID", "ID", "Identifier", "Object Identifier", "Absolute Number",
            "요구사항 ID", "요구사항ID"]
CAT_ATTRS = ["ReqIF.Category", "Category", "Object Type", "Requirement Type", "Type", "Kind", "Artifact Type", "분류", "유형"]
SKIP_ATTRS = {"ReqIF.ForeignCreatedBy", "ReqIF.ForeignCreatedOn", "ReqIF.ForeignModifiedBy", "ReqIF.ForeignModifiedOn",
              "ReqIF.ForeignCreatedThru", "ReqIF.ForeignModifiedThru", "ReqIF.ForeignDeleted", "ReqIF.Prefix",
              "Created By", "Created On", "Last Modified By", "Last Modified On", "Created Thru", "Last Modified Thru",
              "Object Number", "Object Level", "Absolute Number", "Object Short Text", "ALM.ID", "ALM.Type", "ALM.Status"}
SUPPLIER_STATUS = re.compile(r"(supplier|contractor|vendor|공급).*(status|complian|accept|agree|answer|response|회신|상태)|"
                             r"complian|준수|합의\s*여부|acceptance", re.I)
SUPPLIER_COMMENT = re.compile(r"(supplier|contractor|vendor|공급).*(comment|remark|note|의견|비고|설명)", re.I)
SUPPLIER_REF = re.compile(r"(supplier|contractor|vendor|공급).*(ref|link|trace|req.*id|추적|참조)", re.I)
HEADING_CAT = re.compile(r"head|chapter|section|title|제목", re.I)
INFO_CAT = re.compile(r"info|comment|note|descr|explan|prose|text only|정보|설명|참고|비고", re.I)
REQ_CAT = re.compile(r"req|requirement|shall|요구", re.I)

COMPLIANCE_ALM = ["C (준수)", "PC (부분 준수)", "NC (미준수)", "검토중"]
# ALM value -> words that identify the matching enum literal in a customer's own datatype
COMPLIANCE_MATCH = {
    "C": re.compile(r"^\s*(c|ok|yes|accept(ed)?|agree[d]?|compliant|fully|full|fulfil|준수|수용|합의)\b", re.I),
    "PC": re.compile(r"partly|partial|part|pc\b|부분|조건", re.I),
    "NC": re.compile(r"not|non|nc\b|reject|no\b|deviat|미준수|불가|거부", re.I),
    "검토중": re.compile(r"open|tbd|review|clarif|pending|new|검토|확인", re.I),
}


def _ln(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _kids(e, name):
    return [c for c in e if _ln(c.tag) == name]


def _kid(e, name):
    for c in e:
        if _ln(c.tag) == name:
            return c
    return None


def _find(e, *path):
    cur = e
    for p in path:
        if cur is None:
            return None
        cur = _kid(cur, p)
    return cur


def _iter(e, name):
    return (x for x in e.iter() if _ln(x.tag) == name)


# ================================================================ reading
def _read(path: Path) -> tuple[bytes, dict, str]:
    """-> (reqif xml, embedded files {posix path: bytes}, name of the .reqif inside the archive)."""
    path = Path(path)
    if path.suffix.lower() == ".reqifz" or zipfile.is_zipfile(path):
        files, xml, xml_name, total = {}, None, "", 0
        with zipfile.ZipFile(path) as z:
            for inf in z.infolist():
                if inf.is_dir():
                    continue
                total += inf.file_size
                if total > MAX_UNZIP:
                    raise ValueError("ReqIFZ 압축 해제 크기가 너무 큽니다 (500MB 초과)")
                name = PurePosixPath(inf.filename.replace("\\", "/")).as_posix()
                if ".." in PurePosixPath(name).parts:
                    continue
                data = z.read(inf)
                if name.lower().endswith(".reqif") and xml is None:
                    xml, xml_name = data, name
                else:
                    files[name] = data
        if xml is None:
            raise ValueError("ReqIFZ 안에 .reqif 파일이 없습니다")
        return xml, files, xml_name
    return path.read_bytes(), {}, path.name


def _parse_xml(xml: bytes):
    head = xml[:4096].decode("utf-8", "ignore")
    if "<!DOCTYPE" in head or "<!ENTITY" in xml[:65536].decode("utf-8", "ignore"):
        raise ValueError("DOCTYPE/ENTITY 가 포함된 ReqIF 는 보안상 읽지 않습니다")
    nss = []
    for ev, (pfx, uri) in ET.iterparse(io.BytesIO(xml), events=("start-ns",)):
        nss.append((pfx, uri))
    root = ET.fromstring(xml)
    if _ln(root.tag) != "REQ-IF":
        raise ValueError("ReqIF 문서가 아닙니다 (루트 REQ-IF 없음)")
    return root, nss


def _xhtml_parts(el, files: dict, base: str = "") -> dict:
    """XHTML attribute value -> {"text", "tables": [grid], "images": [(bytes, ext, name)]}."""
    out = {"lines": [], "tables": [], "images": []}
    cur = []

    def flush():
        s = re.sub(r"[ \t ]+", " ", "".join(cur)).strip()
        if s:
            out["lines"].append(s)
        cur.clear()

    def obj(o):
        data, typ = o.get("data", ""), (o.get("type") or "").lower()
        inner = [x for x in o if _ln(x.tag) == "object"]
        if typ not in IMG_TYPES and inner:      # DOORS: OLE object with a PNG preview inside
            for x in inner:
                obj(x)
            return
        ext = IMG_TYPES.get(typ) or Path(data).suffix.lower().lstrip(".")
        if ext in ("jpeg",):
            ext = "jpg"
        key = data.replace("\\", "/").lstrip("./")
        blob = files.get(key) or files.get(f"{base}/{key}".lstrip("/")) or next(
            (v for k, v in files.items() if k.endswith("/" + key) or Path(k).name == Path(key).name), None)
        if ext in IMG_TYPES.values():
            out["images"].append((blob, ext, o.get("name") or Path(key).name))
        txt = "".join(o.itertext()).strip()
        if txt and not blob:
            cur.append(txt)

    def table(t):
        grid = []
        for tr in t.iter():
            if _ln(tr.tag) != "tr":
                continue
            row = []
            for td in tr:
                if _ln(td.tag) not in ("td", "th"):
                    continue
                cs, rs = int(td.get("colspan") or 1), int(td.get("rowspan") or 1)
                row.append({"t": re.sub(r"\s+", " ", " ".join(td.itertext())).strip(), "rs": rs, "cs": cs})
                for _ in range(cs - 1):
                    row.append({"t": row[-1]["t"], "skip": True})
            grid.append(row)
        if grid:
            w = max(len(r) for r in grid)
            for r in grid:
                r.extend({"t": ""} for _ in range(w - len(r)))
            out["tables"].append(grid)

    def walk(e):
        n = _ln(e.tag)
        if n == "table":
            flush(); table(e)
            if e.tail:
                cur.append(e.tail)
            return
        if n == "object":
            obj(e)
            if e.tail:
                cur.append(e.tail)
            return
        block = n in ("p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "blockquote", "pre", "dd", "dt")
        if n == "br":
            flush()
        elif block:
            flush()
        if e.text and n != "THE-VALUE":
            cur.append(e.text)
        for c in e:
            walk(c)
        if block:
            flush()
        if e.tail:
            cur.append(e.tail)

    walk(el)
    flush()
    out["text"] = "\n".join(out["lines"])
    return out


def parse(path: Path) -> dict:
    """Read a .reqif/.reqifz into a tool-neutral dict."""
    xml, files, xml_name = _read(path)
    root, _ = _parse_xml(xml)
    base = str(PurePosixPath(xml_name).parent) if "/" in xml_name else ""
    hdr = _find(root, "THE-HEADER", "REQ-IF-HEADER")
    content = _find(root, "CORE-CONTENT", "REQ-IF-CONTENT")
    if content is None:
        raise ValueError("REQ-IF-CONTENT 가 없습니다")
    header = dict(hdr.attrib) if hdr is not None else {}
    if hdr is not None:
        for c in hdr:
            header[_ln(c.tag)] = (c.text or "").strip()

    enum_name, dtypes = {}, {}
    for dt in list(_find(content, "DATATYPES") or []):
        dtypes[dt.get("IDENTIFIER")] = {"kind": _ln(dt.tag).replace("DATATYPE-DEFINITION-", "").lower(),
                                        "name": dt.get("LONG-NAME", "")}
        for ev in _iter(dt, "ENUM-VALUE"):
            enum_name[ev.get("IDENTIFIER")] = ev.get("LONG-NAME") or ev.get("IDENTIFIER")

    attr_def, types = {}, {}
    for st in list(_find(content, "SPEC-TYPES") or []):
        tid = st.get("IDENTIFIER")
        types[tid] = {"kind": _ln(st.tag), "name": st.get("LONG-NAME", ""), "attrs": []}
        for ad in list(_kid(st, "SPEC-ATTRIBUTES") or []):
            kind = _ln(ad.tag).replace("ATTRIBUTE-DEFINITION-", "").lower()
            d = {"id": ad.get("IDENTIFIER"), "name": ad.get("LONG-NAME") or ad.get("IDENTIFIER"), "kind": kind,
                 "type": tid, "default": None}
            dv = _kid(ad, "DEFAULT-VALUE")
            if dv is not None and len(dv):
                d["default"] = _value(dv[0], enum_name, files, base)
            attr_def[d["id"]] = d
            types[tid]["attrs"].append(d["id"])

    objects = {}
    for so in list(_find(content, "SPEC-OBJECTS") or []):
        oid = so.get("IDENTIFIER")
        tref = _find(so, "TYPE")
        tid = (tref[0].text or "").strip() if tref is not None and len(tref) else ""
        vals, xh = {}, {}
        for ad_id in types.get(tid, {}).get("attrs", []):
            d = attr_def[ad_id]
            if d["default"] is not None:
                vals[d["name"]] = d["default"] if d["kind"] != "xhtml" else d["default"]["text"]
        for av in list(_kid(so, "VALUES") or []):
            dref = _find(av, "DEFINITION")
            if dref is None or not len(dref):
                continue
            d = attr_def.get((dref[0].text or "").strip())
            if not d:
                continue
            v = _value(av, enum_name, files, base)
            if d["kind"] == "xhtml":
                xh[d["name"]] = v
                vals[d["name"]] = v["text"]
            else:
                vals[d["name"]] = v
        objects[oid] = {"id": oid, "type": types.get(tid, {}).get("name", ""), "values": vals, "xhtml": xh,
                        "long_name": so.get("LONG-NAME", ""), "last_change": so.get("LAST-CHANGE", "")}

    relations = []
    for sr in list(_find(content, "SPEC-RELATIONS") or []):
        s, t, ty = _find(sr, "SOURCE"), _find(sr, "TARGET"), _find(sr, "TYPE")
        if s is None or t is None or not len(s) or not len(t):
            continue
        tid = (ty[0].text or "").strip() if ty is not None and len(ty) else ""
        relations.append({"src": (s[0].text or "").strip(), "dst": (t[0].text or "").strip(),
                          "type": types.get(tid, {}).get("name", "") or sr.get("LONG-NAME", "")})

    specs = []
    for sp in list(_find(content, "SPECIFICATIONS") or []):
        order = []

        def walk(h, depth):
            for sh in _kids(h, "SPEC-HIERARCHY"):
                ob = _find(sh, "OBJECT")
                if ob is not None and len(ob):
                    order.append((depth, (ob[0].text or "").strip(), sh.get("IS-TABLE-INTERNAL") == "true"))
                ch = _kid(sh, "CHILDREN")
                if ch is not None:
                    walk(ch, depth + 1)
        ch = _kid(sp, "CHILDREN")
        if ch is not None:
            walk(ch, 1)
        specs.append({"id": sp.get("IDENTIFIER"), "title": sp.get("LONG-NAME", ""), "order": order})
    if not specs:   # no hierarchy: object order
        specs.append({"id": "", "title": header.get("TITLE", ""), "order": [(1, o, False) for o in objects]})
    return {"header": header, "types": types, "objects": objects, "relations": relations, "specs": specs,
            "files": files, "datatypes": dtypes}


def _value(av, enum_name, files, base):
    kind = _ln(av.tag)
    if kind.endswith("ENUMERATION"):
        vs = _kid(av, "VALUES")
        refs = [enum_name.get((r.text or "").strip(), (r.text or "").strip()) for r in (vs if vs is not None else [])]
        return ", ".join(refs)
    if kind.endswith("XHTML"):
        tv = _kid(av, "THE-VALUE")
        return _xhtml_parts(tv, files, base) if tv is not None else {"text": "", "tables": [], "images": []}
    v = av.get("THE-VALUE", "")
    if kind.endswith("BOOLEAN"):
        return "true" if v.lower() == "true" else "false"
    return v


def _pick(values: dict, names: list[str]) -> tuple[str, str]:
    low = {k.lower(): k for k in values}
    for n in names:
        k = low.get(n.lower())
        if k is not None and str(values[k]).strip():
            return k, str(values[k]).strip()
    return "", ""


def _asil(v: str) -> str:
    m = re.search(r"\b(QM|[A-D])\b", v.upper().replace("ASIL", " "))
    return m.group(1) if m else v


def to_blocks(path: Path) -> list[Block]:
    """ReqIF -> Blocks. Each block carries meta with the object's ReqIF identity and attributes."""
    data = parse(path)
    objs, blocks = data["objects"], []
    multi = len([s for s in data["specs"] if s["order"]]) > 1
    seen = set()
    n = 0
    for sp in data["specs"]:
        if not sp["order"]:
            continue
        counters = [0] * 8
        if multi:
            n += 1
            blocks.append(Block("heading", text=sp["title"] or f"Specification {n}", level=1, number="", loc=f"spec {n}",
                                meta={"reqif_id": sp["id"], "reqif_spec": True}))
        heading_depths: list[int] = []
        for depth, oid, internal in sp["order"]:
            o = objs.get(oid)
            if not o or oid in seen:
                continue
            seen.add(oid)
            n += 1
            loc = f"obj {n}"
            v = o["values"]
            _, cat = _pick(v, CAT_ATTRS)
            cat = cat or o["type"]
            tk, tval = _pick(v, TEXT_ATTRS)
            if not tk:   # any other XHTML attribute is the text
                tk = next((k for k in o["xhtml"] if k not in HEAD_ATTRS and o["xhtml"][k]["text"]), "")
                tval = o["values"].get(tk, "") if tk else ""
            hk, hval = _pick(v, HEAD_ATTRS)
            idk, nid = _pick(v, ID_ATTRS)
            _, pfx = _pick(v, ["ReqIF.Prefix", "Prefix"])
            if nid and pfx and not nid.startswith(pfx):
                nid = f"{pfx}{nid}"
            is_heading = bool(hval) and (not tval or HEADING_CAT.search(cat or "") and not REQ_CAT.search(cat or ""))
            if hk in ("ReqIF.Name", "Title", "Name") and tval and not HEADING_CAT.search(cat or ""):
                is_heading = False
            if is_heading and REQ_CAT.search(cat or "") and not HEADING_CAT.search(cat or ""):
                is_heading, tval = False, hval    # a requirement that only has a title
            fields = {}
            supplier = {}
            meta = {"reqif_id": oid, "reqif_type": o["type"]}
            for k, val in v.items():
                if k in SKIP_ATTRS or k in (tk, idk) or (is_heading and k == hk) or not str(val).strip():
                    continue
                if SUPPLIER_STATUS.search(k) or SUPPLIER_COMMENT.search(k) or SUPPLIER_REF.search(k):
                    supplier[k] = val
                    continue
                if k in CAT_ATTRS:
                    meta["reqif_category"] = val
                    continue
                if k == hk and k in ("ReqIF.Name", "Title", "Name"):
                    meta["reqif_name"] = val
                    continue
                fields[k] = val
            if supplier:
                meta["reqif_supplier"] = supplier
            if nid:
                meta["native_id"] = nid
            if is_heading:
                while heading_depths and heading_depths[-1] >= depth:
                    heading_depths.pop()
                heading_depths.append(depth)
                lvl = min(6, len(heading_depths) + (1 if multi else 0))
                _, onum = _pick(v, ["Object Number", "ReqIF.ChapterNumber", "Number"])
                counters[lvl - 1] += 1
                for i in range(lvl, len(counters)):
                    counters[i] = 0
                num = onum or ".".join(str(c) for c in counters[(1 if multi else 0):lvl] if c)
                blocks.append(Block("heading", text=hval, level=lvl, number=num, loc=loc, meta=meta))
                if not tval:
                    continue
                meta = {"reqif_parent": oid}
            parts = o["xhtml"].get(tk) if tk in o["xhtml"] else {"text": tval, "tables": [], "images": []}
            if REQ_CAT.search(cat or "") and not INFO_CAT.search(cat or ""):
                meta["reqif_kind"] = "req"
            elif INFO_CAT.search(cat or "") or HEADING_CAT.search(cat or ""):
                meta["reqif_kind"] = "info"
            meta["fields"] = fields
            for k, val in fields.items():
                kl = k.lower()
                if "asil" in kl or "integrity" in kl or "safety level" in kl:
                    meta["asil"] = _asil(str(val))
                elif "verif" in kl or "검증" in kl or "test method" in kl:
                    meta["verification_method"] = str(val)
            text = parts["text"]
            caption = meta.get("reqif_name") or ("" if is_heading else hval)
            if (parts["tables"] or parts["images"]) and meta.get("reqif_kind") != "req" and len(text) <= 200 \
                    and "\n" not in text:
                caption, text = text or caption, ""      # a table / figure object: its text is the caption
            if text:
                blocks.append(Block("para", text=text, loc=loc, meta={**meta, "reqif": True}))
                meta = {"reqif_parent": oid}
            for g in parts["tables"]:
                blocks.append(Block("table", grid=g, caption=caption, loc=loc, meta=meta))
                meta = {"reqif_parent": oid}
            for blob, ext, name in parts["images"]:
                blocks.append(Block("figure", caption=caption or name or "그림", image=blob, image_ext=ext,
                                    loc=loc, meta=meta))
                meta = {"reqif_parent": oid}
    # relations become refs between foreign IDs (resolved into ALM trace links after the import)
    nid_of = {}
    for b in blocks:
        if b.meta.get("reqif_id") and b.meta.get("native_id"):
            nid_of[b.meta["reqif_id"]] = b.meta["native_id"]
    rel = {}
    for r in data["relations"]:
        if r["src"] in nid_of and r["dst"] in nid_of:
            rel.setdefault(r["src"], []).append(nid_of[r["dst"]])
    for b in blocks:
        if b.meta.get("reqif") and b.meta.get("reqif_id") in rel:
            b.meta["refs"] = sorted(set(rel[b.meta["reqif_id"]]))
    return blocks


def summary(path: Path) -> dict:
    d = parse(path)
    return {"title": d["header"].get("TITLE", ""), "tool": d["header"].get("SOURCE-TOOL-ID", ""),
            "objects": len(d["objects"]), "relations": len(d["relations"]), "files": len(d["files"]),
            "specifications": [s["title"] for s in d["specs"]],
            "types": sorted({t["name"] for t in d["types"].values() if t["kind"] == "SPEC-OBJECT-TYPE"}),
            "attributes": sorted({n for o in d["objects"].values() for n in o["values"]})}


# ================================================================ export helpers
def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()) + _tz()


def _tz() -> str:
    off = -time.timezone if not time.localtime().tm_isdst else -time.altzone
    return "%s%02d:%02d" % ("+" if off >= 0 else "-", abs(off) // 3600, abs(off) % 3600 // 60)


def _id(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_.-]", "_", s)
    return s if re.match(r"[A-Za-z_]", s) else "_" + s


def _q(tag):
    return f"{{{NS}}}{tag}"


def _x(tag):
    return f"{{{XH}}}{tag}"


def _sub(parent, tag, **attrs):
    e = ET.SubElement(parent, _q(tag))
    for k, v in attrs.items():
        if v is not None:
            e.set(k.replace("_", "-"), str(v))
    return e


def _ref(parent, tag, ref_tag, target):
    e = _sub(parent, tag)
    r = _sub(e, ref_tag)
    r.text = target
    return e


def _xhtml_div(parent, text: str = "", grid=None, image: tuple | None = None):
    div = ET.SubElement(parent, _x("div"))
    for line in (text or "").split("\n"):
        if line.strip():
            p = ET.SubElement(div, _x("p"))
            p.text = line
    if grid:
        t = ET.SubElement(div, _x("table"), {"border": "1"})
        for row in grid:
            tr = ET.SubElement(t, _x("tr"))
            for c in row:
                if c.get("skip"):
                    continue
                td = ET.SubElement(tr, _x("td"))
                if c.get("cs", 1) > 1:
                    td.set("colspan", str(c["cs"]))
                if c.get("rs", 1) > 1:
                    td.set("rowspan", str(c["rs"]))
                td.text = c.get("t", "")
    if image:
        ET.SubElement(div, _x("object"), {"data": image[0], "type": image[1]})
        if not text:
            div.text = None
    if not len(div) and not div.text:
        div.text = ""
    return div


def _serialize(root, nss=()) -> bytes:
    ET.register_namespace("", NS)
    ET.register_namespace("xhtml", XH)
    for pfx, uri in nss:
        if uri not in (NS, XH) and pfx:
            try:
                ET.register_namespace(pfx, uri)
            except ValueError:
                pass
    body = ET.tostring(root, encoding="utf-8")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + body


def _zip(xml_name: str, xml: bytes, files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(xml_name, xml)
        for k, v in files.items():
            z.writestr(k, v)
    return buf.getvalue()


def compliance_code(v: str) -> str:
    v = (v or "").strip()
    for code in ("NC", "PC", "C"):
        if v.upper().startswith(code + " ") or v.upper() == code or v.upper().startswith(code + "("):
            return code
    return "검토중" if v else ""


def _reference(repo, it) -> str:
    down = sorted(l["src"] for l in repo.links(it["id"]) if l["dst"] == it["id"] and l.get("role") != "relates")
    return " ".join([it["id"]] + [f"→ {', '.join(down)}" if down else ""]).strip()


# ================================================================ export: reply into the customer's file
def reqif_source(repo, doc: str):
    """Latest import of this document that came from a ReqIF file -> (import row, source path)."""
    from .sources import source_file
    for imp in reversed(repo.imports()):
        if imp["doc"] != doc:
            continue
        src = source_file(repo, imp["import_id"])
        if src and src.suffix.lower() in SUFFIXES:
            return imp, src
        return imp, None
    return None, None


def reply(repo, cfg, doc: str) -> tuple[bytes, str, dict]:
    """Fill the supplier attributes into the customer's own ReqIF and return it (.reqifz if it came zipped)."""
    imp, src = reqif_source(repo, doc)
    if not src:
        raise ValueError(f"{doc} 은(는) ReqIF 로 가져온 문서가 아닙니다 — 일반 ReqIF 내보내기를 사용하세요")
    xml, files, xml_name = _read(src)
    root, nss = _parse_xml(xml)
    content = _find(root, "CORE-CONTENT", "REQ-IF-CONTENT")
    dts = _find(content, "DATATYPES")
    now = _now()
    report = {"doc": doc, "rev": imp["rev"], "file": src.name, "objects": 0, "answered": 0, "open": 0,
              "not_in_alm": 0, "by_code": {}, "warnings": [], "added_attributes": []}

    enum_vals = {}     # datatype id -> [(enum id, long name)]
    for dt in list(dts):
        if _ln(dt.tag) == "DATATYPE-DEFINITION-ENUMERATION":
            enum_vals[dt.get("IDENTIFIER")] = [(e.get("IDENTIFIER"), e.get("LONG-NAME") or "") for e in _iter(dt, "ENUM-VALUE")]
    str_dt = next((dt.get("IDENTIFIER") for dt in dts if _ln(dt.tag) == "DATATYPE-DEFINITION-STRING"), None)
    if not str_dt:
        str_dt = "_ECUALM_DT_STRING"
        _sub(dts, "DATATYPE-DEFINITION-STRING", IDENTIFIER=str_dt, LAST_CHANGE=now, LONG_NAME="ECU-ALM String",
             MAX_LENGTH=32000)

    # per object type: definitions for status / comment / reference (customer's own when present)
    defs = {}
    for st in list(_find(content, "SPEC-TYPES")):
        if _ln(st.tag) != "SPEC-OBJECT-TYPE":
            continue
        sa = _kid(st, "SPEC-ATTRIBUTES")
        if sa is None:
            sa = _sub(st, "SPEC-ATTRIBUTES")
        found = {}
        for ad in list(sa):
            nm = ad.get("LONG-NAME") or ""
            kind = _ln(ad.tag).replace("ATTRIBUTE-DEFINITION-", "")
            tref = _find(ad, "TYPE")
            dt_id = (tref[0].text or "").strip() if tref is not None and len(tref) else ""
            for role, rx in (("status", SUPPLIER_STATUS), ("comment", SUPPLIER_COMMENT), ("ref", SUPPLIER_REF)):
                if role not in found and rx.search(nm) and not (role == "status" and SUPPLIER_COMMENT.search(nm)):
                    found[role] = {"id": ad.get("IDENTIFIER"), "kind": kind, "dt": dt_id, "name": nm}
                    break
        names = {"status": "Supplier Status", "comment": "Supplier Comment", "ref": "Supplier Reference"}
        for role in ("status", "comment", "ref"):
            if role in found:
                continue
            aid = _id(f"_ECUALM_{role.upper()}_{st.get('IDENTIFIER')}")
            ad = _sub(sa, "ATTRIBUTE-DEFINITION-STRING", IDENTIFIER=aid, LAST_CHANGE=now, LONG_NAME=names[role],
                      IS_EDITABLE="true")
            _ref(ad, "TYPE", "DATATYPE-DEFINITION-STRING-REF", str_dt)
            found[role] = {"id": aid, "kind": "STRING", "dt": str_dt, "name": names[role]}
            report["added_attributes"].append(f"{st.get('LONG-NAME') or st.get('IDENTIFIER')}: {names[role]}")
        defs[st.get("IDENTIFIER")] = found

    items = {it["attrs"]["reqif_id"]: it for it in repo.items(doc=doc) if it["attrs"].get("reqif_id")}
    req_types = {"CRS", "SYS2", "SWE1", "HSI", "HWE1"}
    for so in list(_find(content, "SPEC-OBJECTS")):
        oid = so.get("IDENTIFIER")
        it = items.get(oid)
        if not it:
            report["not_in_alm"] += 1
            continue
        if it["type"] not in req_types:
            continue
        report["objects"] += 1
        tref = _find(so, "TYPE")
        tid = (tref[0].text or "").strip() if tref is not None and len(tref) else ""
        d = defs.get(tid)
        if not d:
            continue
        a = it["attrs"]
        comp = a.get("compliance") or ""
        code = compliance_code(comp)
        report["by_code"][code or "미회신"] = report["by_code"].get(code or "미회신", 0) + 1
        if code in ("C", "PC", "NC"):
            report["answered"] += 1
        else:
            report["open"] += 1
        vals = _kid(so, "VALUES")
        if vals is None:
            vals = ET.Element(_q("VALUES"))
            so.insert(list(so).index(tref) if tref is not None else len(so), vals)
        changed = False
        for role, value in (("status", comp), ("comment", a.get("comment") or ""), ("ref", _reference(repo, it))):
            if not value:
                continue
            df = d[role]
            for av in list(vals):
                dr = _find(av, "DEFINITION")
                if dr is not None and len(dr) and (dr[0].text or "").strip() == df["id"]:
                    vals.remove(av)
            if df["kind"] == "ENUMERATION":
                lits = enum_vals.get(df["dt"], [])
                rx = COMPLIANCE_MATCH.get(code or "검토중")
                hit = next((e for e in lits if e[1].strip().lower() == value.strip().lower()), None) or \
                    next((e for e in lits if rx and rx.search(e[1])), None)
                if not hit:
                    w = f"'{df['name']}' 열거값에 '{value}' 에 해당하는 값이 없습니다 ({', '.join(e[1] for e in lits)})"
                    if w not in report["warnings"]:
                        report["warnings"].append(w)
                    continue
                av = _sub(vals, "ATTRIBUTE-VALUE-ENUMERATION")
                _ref(av, "DEFINITION", "ATTRIBUTE-DEFINITION-ENUMERATION-REF", df["id"])
                _ref(av, "VALUES", "ENUM-VALUE-REF", hit[0])
            elif df["kind"] not in ("XHTML", "STRING"):
                w = f"'{df['name']}' 은 {df['kind']} 형식이라 회신 값을 쓸 수 없습니다"
                if w not in report["warnings"]:
                    report["warnings"].append(w)
                continue
            elif df["kind"] == "XHTML":
                av = _sub(vals, "ATTRIBUTE-VALUE-XHTML")
                _ref(av, "DEFINITION", "ATTRIBUTE-DEFINITION-XHTML-REF", df["id"])
                _xhtml_div(_sub(av, "THE-VALUE"), value)
            else:
                av = _sub(vals, "ATTRIBUTE-VALUE-STRING", THE_VALUE=value)
                _ref(av, "DEFINITION", "ATTRIBUTE-DEFINITION-STRING-REF", df["id"])
            changed = True
        if changed:
            so.set("LAST-CHANGE", now)

    hdr = _find(root, "THE-HEADER", "REQ-IF-HEADER")
    if hdr is not None:
        hdr.set("IDENTIFIER", "_" + uuid.uuid4().hex)
        for c in hdr:
            n = _ln(c.tag)
            if n == "CREATION-TIME":
                c.text = now
            elif n == "COMMENT":
                c.text = f"Supplier reply to {(c.text or '').strip()[:200]} (ECU-ALM)"
            elif n == "SOURCE-TOOL-ID":
                c.text = "ECU-ALM"
    out = _serialize(root, nss)
    stem = Path(src.name).stem
    if src.suffix.lower() == ".reqifz":
        return _zip(Path(xml_name).name if "/" not in xml_name else xml_name, out, files), f"{stem}_reply.reqifz", report
    return out, f"{stem}_reply.reqif", report


# ================================================================ export: generic
STATUS_VALUES = ["draft", "review", "approved", "rejected"]
CATEGORIES = ["Heading", "Requirement", "Information", "Table", "Figure"]


def export(repo, cfg, doc: str | None = None, stage: str | None = None) -> tuple[bytes, str, dict]:
    """Any ALM document (or the items of one V-model stage) as a new ReqIF archive (.reqifz)."""
    if doc:      # the document as imported (items derived from it are exported per stage)
        items = [i for i in repo.items(doc=doc) if not i["source_loc"].startswith("derived:")]
        title = doc
    elif stage:
        st = next((s for s in cfg["stages"] if s["id"] == stage), None)
        if not st:
            raise KeyError(f"단계 {stage} 없음")
        items = [i for i in repo.items() if i["type"] in st["types"]]
        title = f"{stage} {st.get('name', '')}".strip()
    else:
        raise ValueError("doc 또는 stage 를 지정하세요")
    if not items:
        raise ValueError("내보낼 항목이 없습니다")
    now = _now()
    root = ET.Element(_q("REQ-IF"))
    hdr = _sub(_sub(root, "THE-HEADER"), "REQ-IF-HEADER", IDENTIFIER="_" + uuid.uuid4().hex)
    for tag, val in (("COMMENT", f"Exported from ECU-ALM ({title})"), ("CREATION-TIME", now),
                     ("REPOSITORY-ID", cfg.get("project", {}).get("name", "ECU-ALM") if isinstance(cfg.get("project"), dict) else "ECU-ALM"),
                     ("REQ-IF-TOOL-ID", "ECU-ALM"), ("REQ-IF-VERSION", "1.0"), ("SOURCE-TOOL-ID", "ECU-ALM"),
                     ("TITLE", title)):
        _sub(hdr, tag).text = val
    content = _sub(_sub(root, "CORE-CONTENT"), "REQ-IF-CONTENT")
    dts = _sub(content, "DATATYPES")
    _sub(dts, "DATATYPE-DEFINITION-STRING", IDENTIFIER="_DT_STRING", LAST_CHANGE=now, LONG_NAME="String", MAX_LENGTH=32000)
    _sub(dts, "DATATYPE-DEFINITION-XHTML", IDENTIFIER="_DT_XHTML", LAST_CHANGE=now, LONG_NAME="XHTML")

    def enum(dt_id, name, values):
        e = _sub(dts, "DATATYPE-DEFINITION-ENUMERATION", IDENTIFIER=dt_id, LAST_CHANGE=now, LONG_NAME=name)
        sv = _sub(e, "SPECIFIED-VALUES")
        ids = {}
        for k, v in enumerate(values):
            vid = _id(f"{dt_id}_{k}")
            ev = _sub(sv, "ENUM-VALUE", IDENTIFIER=vid, LAST_CHANGE=now, LONG_NAME=v)
            _sub(_sub(ev, "PROPERTIES"), "EMBEDDED-VALUE", KEY=k, OTHER_CONTENT=v)
            ids[v] = vid
        return ids
    e_cat = enum("_DT_CATEGORY", "Category", CATEGORIES)
    e_asil = enum("_DT_ASIL", "ASIL", ["QM", "A", "B", "C", "D"])
    e_stat = enum("_DT_STATUS", "Status", STATUS_VALUES)
    e_comp = enum("_DT_COMPLIANCE", "Compliance", COMPLIANCE_ALM)

    extra = []
    for it in items:
        for k in (it["attrs"].get("fields") or {}):
            if k not in extra and k.lower() != "asil" and "asil" not in k.lower():
                extra.append(k)
    types = _sub(content, "SPEC-TYPES")
    ot = _sub(types, "SPEC-OBJECT-TYPE", IDENTIFIER="_T_OBJECT", LAST_CHANGE=now, LONG_NAME="ECU-ALM Object")
    sa = _sub(ot, "SPEC-ATTRIBUTES")
    adefs = {}

    def adef(key, name, kind, dt):
        aid = _id(f"_A_{key}")
        ad = _sub(sa, f"ATTRIBUTE-DEFINITION-{kind}", IDENTIFIER=aid, LAST_CHANGE=now, LONG_NAME=name, IS_EDITABLE="true")
        if kind == "ENUMERATION":
            ad.set("MULTI-VALUED", "false")
        _ref(ad, "TYPE", f"DATATYPE-DEFINITION-{kind}-REF", dt)
        adefs[key] = (aid, kind)
    for key, name, kind, dt in (("fid", "ReqIF.ForeignID", "STRING", "_DT_STRING"),
                                ("chap", "ReqIF.ChapterName", "STRING", "_DT_STRING"),
                                ("text", "ReqIF.Text", "XHTML", "_DT_XHTML"),
                                ("cat", "ReqIF.Category", "ENUMERATION", "_DT_CATEGORY"),
                                ("almid", "ALM.ID", "STRING", "_DT_STRING"),
                                ("almtype", "ALM.Type", "STRING", "_DT_STRING"),
                                ("status", "ALM.Status", "ENUMERATION", "_DT_STATUS"),
                                ("asil", "ASIL", "ENUMERATION", "_DT_ASIL"),
                                ("ver", "Verification Method", "STRING", "_DT_STRING"),
                                ("comp", "Supplier Status", "ENUMERATION", "_DT_COMPLIANCE"),
                                ("comment", "Supplier Comment", "STRING", "_DT_STRING"),
                                ("ref", "Supplier Reference", "STRING", "_DT_STRING")):
        adef(key, name, kind, dt)
    for k, name in enumerate(extra):
        adef(f"f{k}", name, "STRING", "_DT_STRING")
    rt = _sub(types, "SPEC-RELATION-TYPE", IDENTIFIER="_T_LINK", LAST_CHANGE=now, LONG_NAME="ECU-ALM Trace")
    _ref(_sub(_sub(rt, "SPEC-ATTRIBUTES"), "ATTRIBUTE-DEFINITION-STRING", IDENTIFIER="_A_ROLE", LAST_CHANGE=now,
              LONG_NAME="Role"), "TYPE", "DATATYPE-DEFINITION-STRING-REF", "_DT_STRING")
    _sub(types, "SPECIFICATION-TYPE", IDENTIFIER="_T_SPEC", LAST_CHANGE=now, LONG_NAME="ECU-ALM Specification")

    objs = _sub(content, "SPEC-OBJECTS")
    files, oid_of, used = {}, {}, set()
    for it in items:
        a = it["attrs"]
        oid = a.get("reqif_id") or _id(f"_ALM_{it['id']}")
        if oid in used:
            oid = _id(f"_ALM_{it['id']}")
        used.add(oid)
        oid_of[it["id"]] = oid
        so = _sub(objs, "SPEC-OBJECT", IDENTIFIER=oid, LAST_CHANGE=now, LONG_NAME=it["id"])
        vals = _sub(so, "VALUES")
        cat = {"HDG": "Heading", "INFO": "Information", "TBL": "Table", "FIG": "Figure"}.get(it["type"], "Requirement")

        def sval(key, v):
            if v in (None, ""):
                return
            aid, kind = adefs[key]
            if kind == "STRING":
                av = _sub(vals, "ATTRIBUTE-VALUE-STRING", THE_VALUE=v)
                _ref(av, "DEFINITION", "ATTRIBUTE-DEFINITION-STRING-REF", aid)

        def evals(key, ids, v):
            if v not in ids:
                return
            av = _sub(vals, "ATTRIBUTE-VALUE-ENUMERATION")
            _ref(av, "DEFINITION", "ATTRIBUTE-DEFINITION-ENUMERATION-REF", adefs[key][0])
            _ref(av, "VALUES", "ENUM-VALUE-REF", ids[v])
        sval("fid", a.get("native_id") or (it["id"] if cat == "Requirement" else ""))
        evals("cat", e_cat, cat)
        sval("almid", it["id"])
        sval("almtype", it["type"])
        if cat == "Heading":
            sval("chap", it["title"])
        else:
            img = None
            if it["type"] == "FIG" and a.get("file"):
                p = Path(repo.assets) / a["file"]
                if p.exists():
                    fn = f"files/{a['file']}"
                    files[fn] = p.read_bytes()
                    ext = p.suffix.lower().lstrip(".")
                    img = (fn, next((k for k, v in IMG_TYPES.items() if v == ext), "image/png"))
            av = _sub(vals, "ATTRIBUTE-VALUE-XHTML")
            _ref(av, "DEFINITION", "ATTRIBUTE-DEFINITION-XHTML-REF", adefs["text"][0])
            text = a.get("caption") if it["type"] in ("TBL", "FIG") else it["text"]
            _xhtml_div(_sub(av, "THE-VALUE"), text or "", a.get("grid") if it["type"] == "TBL" else None, img)
        if cat == "Requirement":
            evals("status", e_stat, it.get("status"))
            evals("asil", e_asil, _asil(str(a.get("asil") or "")) if a.get("asil") else "")
            sval("ver", a.get("verification_method"))
            evals("comp", e_comp, a.get("compliance"))
            sval("comment", a.get("comment"))
            sval("ref", _reference(repo, it))
            for k, name in enumerate(extra):
                sval(f"f{k}", str((a.get("fields") or {}).get(name, "")))
        _ref(so, "TYPE", "SPEC-OBJECT-TYPE-REF", "_T_OBJECT")

    rels = _sub(content, "SPEC-RELATIONS")
    nrel = 0
    for l in repo.links():
        if l["src"] in oid_of and l["dst"] in oid_of:
            nrel += 1
            sr = _sub(rels, "SPEC-RELATION", IDENTIFIER=_id(f"_L_{l['src']}_{l['role']}_{l['dst']}"), LAST_CHANGE=now,
                      LONG_NAME=l["role"])
            vals = _sub(sr, "VALUES")
            av = _sub(vals, "ATTRIBUTE-VALUE-STRING", THE_VALUE=l["role"])
            _ref(av, "DEFINITION", "ATTRIBUTE-DEFINITION-STRING-REF", "_A_ROLE")
            _ref(sr, "SOURCE", "SPEC-OBJECT-REF", oid_of[l["src"]])
            _ref(sr, "TARGET", "SPEC-OBJECT-REF", oid_of[l["dst"]])
            _ref(sr, "TYPE", "SPEC-RELATION-TYPE-REF", "_T_LINK")

    specs = _sub(content, "SPECIFICATIONS")
    sp = _sub(specs, "SPECIFICATION", IDENTIFIER=_id("_S_" + uuid.uuid4().hex[:12]), LAST_CHANGE=now, LONG_NAME=title)
    top = _sub(sp, "CHILDREN")
    _ref(sp, "TYPE", "SPECIFICATION-TYPE-REF", "_T_SPEC")    # XSD order: CHILDREN before TYPE
    stack: list[tuple[int, object]] = [(0, top)]     # (heading level, CHILDREN element)
    for it in items:
        if it["type"] == "HDG":
            lvl = int(it["attrs"].get("level") or 1)
            while len(stack) > 1 and stack[-1][0] >= lvl:
                stack.pop()
        sh = _sub(stack[-1][1], "SPEC-HIERARCHY", IDENTIFIER=_id(f"_H_{it['id']}"), LAST_CHANGE=now)
        if it["type"] == "HDG":     # XSD order: CHILDREN before OBJECT
            stack.append((int(it["attrs"].get("level") or 1), _sub(sh, "CHILDREN")))
        _ref(sh, "OBJECT", "SPEC-OBJECT-REF", oid_of[it["id"]])
    # empty CHILDREN elements are not schema-valid
    for e in list(root.iter()):
        for c in list(e):
            if _ln(c.tag) == "CHILDREN" and not len(c):
                e.remove(c)
    xml = _serialize(root)
    name = re.sub(r"[^\w.-]+", "_", title).strip("_") or "export"
    report = {"objects": len(items), "relations": nrel, "files": len(files), "attributes": 12 + len(extra)}
    return _zip(f"{name}.reqif", xml, files), f"{name}.reqifz", report
