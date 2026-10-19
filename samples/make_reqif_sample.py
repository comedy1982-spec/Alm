"""Customer-style ReqIF exchange files of the eLSD spec, as an OEM would send them out of DOORS.

  python samples/make_reqif_sample.py  ->  samples/CRS_eLSD_ECU_rev1.0.reqifz, samples/CRS_eLSD_ECU_rev1.1.reqifz

The content comes from the Word revisions (make_elsd_crs.py / make_elsd_rev.py), written with DOORS-style
attributes (Absolute Number, Object Heading, Object Text, Object Type, ASIL, Verification, Supplier Status,
Supplier Comment) so the importer is exercised on a structure it did not write itself. SPEC-OBJECT
IDENTIFIERs stay the same between revisions, as in a real DOORS baseline export.
"""
from __future__ import annotations

import hashlib
import io
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from ecualm.config import DEFAULT_CONFIG  # noqa: E402
from ecualm.importer import build_candidates, parse_any  # noqa: E402

T = "2026-11-20T09:00:00+09:00"


def _uid(*parts) -> str:
    return "_" + hashlib.sha1("|".join(parts).encode()).hexdigest()[:24].upper()


class _R:      # build_candidates needs a repo only for figure assets
    def __init__(self, d):
        self.assets = d


KNOWN: dict = {}     # foreign ID -> object key, so a requirement softened to "should" stays the same DOORS object


def objects(docx: Path, tmp: Path) -> list[dict]:
    import copy
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    blocks = parse_any(docx)
    tmp.mkdir(parents=True, exist_ok=True)
    cands = build_candidates(blocks, cfg, "crs", _R(tmp), "CRS")
    out, depth, sec_n = [], 0, {}
    for c in cands:
        a = c["attrs"]
        if c["type"] == "HDG":
            depth = int(a.get("level") or 1)
            out.append({"kind": "Heading", "key": "H" + (a.get("number") or c["title"]), "heading": c["title"],
                        "depth": depth})
            continue
        if a.get("meta_of"):
            continue
        sec = c["section"]
        sec_n[sec] = sec_n.get(sec, 0) + 1
        o = {"depth": depth + 1}
        if c["type"] == "CRS":
            f = a.get("fields") or {}
            o.update(kind="Requirement", key=a.get("native_id") or c["text"][:40], fid=a.get("native_id", ""),
                     text=c["text"], asil=a.get("asil") or f.get("ASIL", ""),
                     ver=a.get("verification_method") or next((v for k, v in f.items() if "검증" in k), ""))
        elif c["type"] == "TBL":
            o.update(kind="Information", key=f"T|{sec}|{sec_n[sec]}", text=a.get("caption") or "", grid=a.get("grid"))
        elif c["type"] == "FIG":
            p = tmp / a.get("file", "")
            o.update(kind="Information", key=f"F|{sec}|{a.get('caption')}", text=a.get("caption") or "",
                     image=(p.name, p.read_bytes()) if a.get("file") and p.exists() else None)
        else:
            known = next((n for n in KNOWN if n in c["text"]), None)
            if known:      # same object, the customer only changed its wording
                o.update(kind="Requirement", key=known, fid=known, text=c["text"].replace(f"[{known}]", "").strip())
            else:
                o.update(kind="Information", key=f"I|{sec}|{sec_n[sec]}", text=c["text"])
        if o.get("fid"):
            KNOWN.setdefault(o["fid"], o["key"])
        out.append(o)
    # a table row the parser no longer reads as a requirement ("shall" -> "should") is still the same DOORS object
    have = {o.get("fid") for o in out}
    order = list(KNOWN)
    for b in blocks:
        for r in (b.grid or [])[1:]:
            cells = [x.get("t", "").strip() for x in r]
            if cells and cells[0] in KNOWN and cells[0] not in have and len(cells) >= 2:
                fid = cells[0]
                prev = order[order.index(fid) - 1] if order.index(fid) else None
                at = next((k for k, o in enumerate(out) if o.get("fid") == prev), len(out) - 1)
                out.insert(at + 1, {**out[at], "kind": "Requirement", "key": fid, "fid": fid, "text": cells[1],
                                    "asil": cells[2] if len(cells) > 2 else "", "ver": cells[3] if len(cells) > 3 else ""})
                have.add(fid)
    return out


def _xhtml(text: str, grid=None, image=None) -> str:
    s = "".join(f"<xhtml:p>{escape(line)}</xhtml:p>" for line in (text or "").split("\n") if line.strip())
    if grid:
        rows = []
        for r in grid:
            cells = "".join(f"<xhtml:td>{escape(c.get('t', ''))}</xhtml:td>" for c in r if not c.get("skip"))
            rows.append(f"<xhtml:tr>{cells}</xhtml:tr>")
        s += f"<xhtml:table border=\"1\">{''.join(rows)}</xhtml:table>"
    if image:
        ext = Path(image).suffix.lower().lstrip(".")
        s += f'<xhtml:object data={quoteattr("files/" + image)} type="image/{"jpeg" if ext == "jpg" else ext}"/>'
    return f"<xhtml:div>{s}</xhtml:div>"


def write(objs: list[dict], numbers: dict, title: str, rev: str, out: Path) -> None:
    E = lambda k: f"_EV_{k}"
    enum = {"OT": ["Heading", "Requirement", "Information"], "AS": ["QM", "A", "B", "C", "D"],
            "SS": ["Open", "Accepted", "Partly accepted", "Not accepted"]}
    dts = ['<DATATYPE-DEFINITION-STRING IDENTIFIER="_DT_S" LAST-CHANGE="%s" LONG-NAME="String" MAX-LENGTH="8192"/>' % T,
           '<DATATYPE-DEFINITION-XHTML IDENTIFIER="_DT_X" LAST-CHANGE="%s" LONG-NAME="XHTML"/>' % T,
           '<DATATYPE-DEFINITION-INTEGER IDENTIFIER="_DT_I" LAST-CHANGE="%s" LONG-NAME="Integer" MAX="2147483647" MIN="0"/>' % T]
    for k, vals in enum.items():
        evs = "".join(f'<ENUM-VALUE IDENTIFIER="{E(k + str(i))}" LAST-CHANGE="{T}" LONG-NAME={quoteattr(v)}>'
                      f'<PROPERTIES><EMBEDDED-VALUE KEY="{i}" OTHER-CONTENT=""/></PROPERTIES></ENUM-VALUE>'
                      for i, v in enumerate(vals))
        dts.append(f'<DATATYPE-DEFINITION-ENUMERATION IDENTIFIER="_DT_{k}" LAST-CHANGE="{T}" LONG-NAME="{k}">'
                   f'<SPECIFIED-VALUES>{evs}</SPECIFIED-VALUES></DATATYPE-DEFINITION-ENUMERATION>')
    A = [("AN", "Absolute Number", "INTEGER", "_DT_I"), ("OH", "Object Heading", "STRING", "_DT_S"),
         ("OX", "Object Text", "XHTML", "_DT_X"), ("FI", "ReqIF.ForeignID", "STRING", "_DT_S"),
         ("OT", "Object Type", "ENUMERATION", "_DT_OT"), ("AS", "ASIL", "ENUMERATION", "_DT_AS"),
         ("VM", "Verification", "STRING", "_DT_S"), ("SS", "Supplier Status", "ENUMERATION", "_DT_SS"),
         ("SC", "Supplier Comment", "XHTML", "_DT_X")]
    ads = "".join(f'<ATTRIBUTE-DEFINITION-{k} IDENTIFIER="_AD_{a}" LAST-CHANGE="{T}" LONG-NAME="{n}"'
                  f'{" MULTI-VALUED=" + chr(34) + "false" + chr(34) if k == "ENUMERATION" else ""}>'
                  f'<TYPE><DATATYPE-DEFINITION-{k}-REF>{d}</DATATYPE-DEFINITION-{k}-REF></TYPE></ATTRIBUTE-DEFINITION-{k}>'
                  for a, n, k, d in A)
    files, so, hier = {}, [], []

    def sv(a, v):
        return (f'<ATTRIBUTE-VALUE-STRING THE-VALUE={quoteattr(v)}><DEFINITION><ATTRIBUTE-DEFINITION-STRING-REF>_AD_{a}'
                f'</ATTRIBUTE-DEFINITION-STRING-REF></DEFINITION></ATTRIBUTE-VALUE-STRING>')

    def ev(a, k, v):
        i = enum[k].index(v)
        return (f'<ATTRIBUTE-VALUE-ENUMERATION><DEFINITION><ATTRIBUTE-DEFINITION-ENUMERATION-REF>_AD_{a}'
                f'</ATTRIBUTE-DEFINITION-ENUMERATION-REF></DEFINITION><VALUES><ENUM-VALUE-REF>{E(k + str(i))}'
                f'</ENUM-VALUE-REF></VALUES></ATTRIBUTE-VALUE-ENUMERATION>')

    stack = [(0, [])]
    for o in objs:
        oid = _uid(o["key"])
        v = [f'<ATTRIBUTE-VALUE-INTEGER THE-VALUE="{numbers[o["key"]]}"><DEFINITION><ATTRIBUTE-DEFINITION-INTEGER-REF>_AD_AN'
             f'</ATTRIBUTE-DEFINITION-INTEGER-REF></DEFINITION></ATTRIBUTE-VALUE-INTEGER>', ev("OT", "OT", o["kind"])]
        if o["kind"] == "Heading":
            v.append(sv("OH", o["heading"]))
        else:
            img = None
            if o.get("image"):
                files["files/" + o["image"][0]] = o["image"][1]
                img = o["image"][0]
            v.append(f'<ATTRIBUTE-VALUE-XHTML><DEFINITION><ATTRIBUTE-DEFINITION-XHTML-REF>_AD_OX</ATTRIBUTE-DEFINITION-XHTML-REF>'
                     f'</DEFINITION><THE-VALUE>{_xhtml(o["text"], o.get("grid"), img)}</THE-VALUE></ATTRIBUTE-VALUE-XHTML>')
        if o["kind"] == "Requirement":
            if o.get("fid"):
                v.append(sv("FI", o["fid"]))
            if o.get("asil") in enum["AS"]:
                v.append(ev("AS", "AS", o["asil"]))
            if o.get("ver"):
                v.append(sv("VM", o["ver"]))
            v.append(ev("SS", "SS", "Open"))
        so.append(f'<SPEC-OBJECT IDENTIFIER="{oid}" LAST-CHANGE="{T}"><VALUES>{"".join(v)}</VALUES>'
                  f'<TYPE><SPEC-OBJECT-TYPE-REF>_OT_ELSD</SPEC-OBJECT-TYPE-REF></TYPE></SPEC-OBJECT>')
        # DOORS hierarchy: objects below the heading they follow
        d = o["depth"]
        while len(stack) > 1 and stack[-1][0] >= d:
            stack.pop()
        node = [oid, []]
        stack[-1][1].append(node)
        if o["kind"] == "Heading":
            stack.append((d, node[1]))
    tree = stack[0][1]

    def render(nodes):
        out = []
        for oid, kids in nodes:
            ch = f"<CHILDREN>{render(kids)}</CHILDREN>" if kids else ""
            out.append(f'<SPEC-HIERARCHY IDENTIFIER="_SH{oid}" LAST-CHANGE="{T}">{ch}'
                       f'<OBJECT><SPEC-OBJECT-REF>{oid}</SPEC-OBJECT-REF></OBJECT></SPEC-HIERARCHY>')
        return "".join(out)

    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<REQ-IF xmlns="http://www.omg.org/spec/ReqIF/20110401/reqif.xsd" xmlns:xhtml="http://www.w3.org/1999/xhtml">
<THE-HEADER><REQ-IF-HEADER IDENTIFIER="{_uid('hdr', rev)}"><COMMENT>{escape(title)} rev {rev} — exchange to supplier</COMMENT>
<CREATION-TIME>{T}</CREATION-TIME><REQ-IF-TOOL-ID>DOORS-like sample</REQ-IF-TOOL-ID><REQ-IF-VERSION>1.0</REQ-IF-VERSION>
<SOURCE-TOOL-ID>ACME Motors RM (sample)</SOURCE-TOOL-ID><TITLE>{escape(title)}</TITLE></REQ-IF-HEADER></THE-HEADER>
<CORE-CONTENT><REQ-IF-CONTENT>
<DATATYPES>{"".join(dts)}</DATATYPES>
<SPEC-TYPES><SPEC-OBJECT-TYPE IDENTIFIER="_OT_ELSD" LAST-CHANGE="{T}" LONG-NAME="eLSD Object Type"><SPEC-ATTRIBUTES>{ads}</SPEC-ATTRIBUTES></SPEC-OBJECT-TYPE>
<SPECIFICATION-TYPE IDENTIFIER="_ST" LAST-CHANGE="{T}" LONG-NAME="Module"/></SPEC-TYPES>
<SPEC-OBJECTS>{"".join(so)}</SPEC-OBJECTS>
<SPECIFICATIONS><SPECIFICATION IDENTIFIER="_SPEC_ELSD" LAST-CHANGE="{T}" LONG-NAME={quoteattr(title)}><CHILDREN>{render(tree)}</CHILDREN>
<TYPE><SPECIFICATION-TYPE-REF>_ST</SPECIFICATION-TYPE-REF></TYPE></SPECIFICATION></SPECIFICATIONS>
</REQ-IF-CONTENT></CORE-CONTENT></REQ-IF>
'''
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(out.stem + ".reqif", xml)
        for k, b in files.items():
            z.writestr(k, b)
    out.write_bytes(buf.getvalue())


def main() -> list[Path]:
    import tempfile
    revs = [("1.0", HERE / "CRS_eLSD_ECU_rev1.0.docx"), ("1.1", HERE / "CRS_eLSD_ECU_rev1.1.docx")]
    if not revs[1][1].exists():
        import subprocess
        subprocess.run([sys.executable, str(HERE / "make_elsd_rev.py")], check=True)
    numbers: dict = {}
    outs = []
    with tempfile.TemporaryDirectory() as td:
        for rev, src in revs:
            objs = objects(src, Path(td) / rev)
            for o in objs:      # Absolute Number: stable per object, new objects get the next free number
                numbers.setdefault(o["key"], len(numbers) + 1)
            out = HERE / f"CRS_eLSD_ECU_rev{rev}.reqifz"
            write(objs, numbers, "eLSD ECU Customer Requirements (CRS-LSD-001)", rev, out)
            print(out, len(objs), "objects")
            outs.append(out)
    return outs


if __name__ == "__main__":
    main()
