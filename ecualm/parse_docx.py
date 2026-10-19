"""DOCX parser: walks the document body in order and emits headings, paragraphs, tables
(with merged cells resolved) and figures (embedded images, including legacy EMF/WMF)."""
from __future__ import annotations

import re
from pathlib import Path

import docx
from docx.oxml.ns import qn

from .blocks import Block, HEADING_NUM, norm_text

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "v": "urn:schemas-microsoft-com:vml",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
    "dgm": "http://schemas.openxmlformats.org/drawingml/2006/diagram",
}
M_T = "{%s}t" % NS["m"]
M_MATH = "{%s}oMath" % NS["m"]
R_EMBED = "{%s}embed" % NS["r"]
R_ID = "{%s}id" % NS["r"]

HEADING_STYLE = re.compile(r"^(heading|제목|머리글|title\s*)\s*(\d)", re.I)
EXT_BY_CT = {
    "image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/bmp": "bmp", "image/tiff": "tif",
    "image/x-emf": "emf", "image/emf": "emf", "image/x-wmf": "wmf", "image/wmf": "wmf", "image/svg+xml": "svg",
}


def _style_outline_level(style) -> int | None:
    """Outline level defined on the paragraph style or one of its base styles."""
    seen = 0
    while style is not None and seen < 10:
        name = style.name or ""
        m = HEADING_STYLE.match(name)
        if m:
            return int(m.group(2))
        el = style.element.find(qn("w:pPr"))
        if el is not None:
            ol = el.find(qn("w:outlineLvl"))
            if ol is not None:
                v = int(ol.get(qn("w:val")))
                if v < 9:
                    return v + 1
        style = style.base_style
        seen += 1
    return None


def _omml(el) -> str:
    """Office Math -> linear text: fractions (a)/(b), sub/superscripts a_b a^b, roots √(x), delimiters (x)."""
    def m(t):
        return "{%s}%s" % (NS["m"], t)

    def kid(e, t):
        return e.find(m(t))

    def lin(e) -> str:
        if e is None:
            return ""
        tag = e.tag
        if tag == m("t"):
            return e.text or ""
        if tag == m("f"):
            num, den = lin(kid(e, "num")), lin(kid(e, "den"))
            wrap = lambda x: x if re.fullmatch(r"[\w.]+", x) else f"({x})"
            return f"{wrap(num)}/{wrap(den)}"
        if tag == m("sSub"):
            return f"{lin(kid(e, 'e'))}_{lin(kid(e, 'sub'))}"
        if tag == m("sSup"):
            return f"{lin(kid(e, 'e'))}^{lin(kid(e, 'sup'))}"
        if tag == m("sSubSup"):
            return f"{lin(kid(e, 'e'))}_{lin(kid(e, 'sub'))}^{lin(kid(e, 'sup'))}"
        if tag == m("rad"):
            deg = lin(kid(e, "deg"))
            return f"{'' if not deg else deg}√({lin(kid(e, 'e'))})"
        if tag == m("d"):
            pr = kid(e, "dPr")
            beg = pr.find(m("begChr")).get(m("val")) if pr is not None and pr.find(m("begChr")) is not None else "("
            end = pr.find(m("endChr")).get(m("val")) if pr is not None and pr.find(m("endChr")) is not None else ")"
            return beg + ", ".join(lin(x) for x in e.findall(m("e"))) + end
        if tag == m("nary"):
            pr = kid(e, "naryPr")
            ch = pr.find(m("chr")).get(m("val")) if pr is not None and pr.find(m("chr")) is not None else "∫"
            sub, sup = lin(kid(e, "sub")), lin(kid(e, "sup"))
            return f"{ch}{'_' + sub if sub else ''}{'^' + sup if sup else ''} {lin(kid(e, 'e'))}"
        if tag in (m("rPr"), m("ctrlPr"), m("fPr"), m("sSubPr"), m("sSupPr"), m("radPr"), m("dPr"), m("naryPr")):
            return ""
        return "".join(lin(c) for c in e)
    return lin(el)


def _para_text(p_el) -> str:
    parts = []
    skip = set()
    for node in p_el.iter():
        tag = node.tag
        if node in skip:
            continue
        if tag == M_MATH:                        # an equation (OMML), kept inline as linear text
            parts.append(_omml(node))
            skip.update(node.iter())
        elif tag == qn("w:t"):
            parts.append(node.text or "")
        elif tag == qn("w:tab"):
            parts.append("\t")
        elif tag in (qn("w:br"), qn("w:cr")):
            parts.append("\n")
        elif tag == qn("w:delText"):
            continue  # deleted text under track changes is ignored
    return norm_text("".join(parts))


def _para_text_main(p_el) -> str:
    """Paragraph text without text-box content (text boxes are captured separately)."""
    parts = []
    skip = set()
    for node in p_el.iter():
        if node in skip:
            continue
        if node.tag == M_MATH:
            parts.append(_omml(node))
            skip.update(node.iter())
        elif node.tag == qn("w:t"):
            # skip runs living inside drawings/text boxes
            anc = node.getparent()
            inside_box = False
            while anc is not None and anc is not p_el:
                if anc.tag in (qn("w:txbxContent"),):
                    inside_box = True
                    break
                anc = anc.getparent()
            if not inside_box:
                parts.append(node.text or "")
        elif node.tag == qn("w:tab"):
            parts.append("\t")
        elif node.tag in (qn("w:br"), qn("w:cr")):
            parts.append("\n")
    return norm_text("".join(parts))


def _images_in(el, part) -> list[tuple[bytes, str]]:
    out, seen = [], set()
    rids = [b.get(R_EMBED) for b in el.iter("{%s}blip" % NS["a"])]
    rids += [i.get(R_ID) for i in el.iter("{%s}imagedata" % NS["v"])]
    for rid in rids:
        if not rid or rid in seen:
            continue
        seen.add(rid)
        try:
            ipart = part.related_parts[rid]
        except KeyError:
            continue
        ct = getattr(ipart, "content_type", "")
        ext = EXT_BY_CT.get(ct) or Path(str(ipart.partname)).suffix.lstrip(".").lower() or "bin"
        out.append((ipart.blob, ext))
    return out


def _charts_in(el, part) -> list[dict]:
    """Native Word charts (c:chart) and SmartArt (dgm:relIds) inside an element -> [{"chart"| "smartart": ...}]."""
    from .charts import parse_chart
    out = []
    for c in el.iter("{%s}chart" % NS["c"]):
        rid = c.get(R_ID)
        try:
            ch = parse_chart(part.related_parts[rid].blob)
        except (KeyError, AttributeError):
            ch = None
        if ch:
            out.append({"chart": ch})
    for d in el.iter("{%s}relIds" % NS["dgm"]):
        rid = d.get("{%s}dm" % NS["r"])
        try:
            from lxml import etree
            data = etree.fromstring(part.related_parts[rid].blob)
        except Exception:
            continue
        labels = []
        for t in data.iter("{%s}t" % NS["a"]):
            if t.text and t.text.strip() and t.text.strip() not in labels:
                labels.append(t.text.strip())
        out.append({"smartart": labels})
    return out


def _media_blocks(el, part, loc: str, style: str = "") -> list[Block]:
    """Pictures, charts and SmartArt inside an element as figure blocks."""
    out = [Block(kind="figure", image=blob, image_ext=ext, style=style, loc=loc) for blob, ext in _images_in(el, part)]
    from .charts import svg
    for m in _charts_in(el, part):
        if "chart" in m:
            out.append(Block(kind="figure", image=svg(m["chart"]), image_ext="svg", style="chart", loc=loc,
                             caption=m["chart"].get("title", ""), meta={"chart": m["chart"]}))
        else:
            out.append(Block(kind="figure", text=" | ".join(m["smartart"]), style="smartart", loc=loc))
    return out


def _table_grid(tbl_el) -> list[list[dict]]:
    rows: list[list[dict | None]] = []
    owners: dict[int, tuple[int, int]] = {}   # column -> (row, col) of the cell that started a vertical merge
    for ri, tr in enumerate(tbl_el.findall(qn("w:tr"))):
        row: list[dict | None] = []
        col = 0
        trpr = tr.find(qn("w:trPr"))
        if trpr is not None:
            gb = trpr.find(qn("w:gridBefore"))
            if gb is not None:
                for _ in range(int(gb.get(qn("w:val"), "0"))):
                    row.append({"t": "", "rs": 1, "cs": 1, "skip": False}); col += 1
        tcs = tr.findall(qn("w:tc")) + [tc for sdt in tr.findall(qn("w:sdt"))
                                         for tc in sdt.iter(qn("w:tc"))]
        for tc in tcs:
            tcpr = tc.find(qn("w:tcPr"))
            span, vmerge = 1, None
            if tcpr is not None:
                gs = tcpr.find(qn("w:gridSpan"))
                if gs is not None:
                    span = int(gs.get(qn("w:val"), "1"))
                vm = tcpr.find(qn("w:vMerge"))
                if vm is not None:
                    vmerge = vm.get(qn("w:val")) or "continue"
            text = "\n".join(t for t in (_para_text(p) for p in tc.iter(qn("w:p"))) if t)
            if vmerge == "continue" and col in owners:
                orow, ocol = owners[col]
                owner = rows[orow][ocol]
                owner["rs"] += 1
                cell = {"t": owner["t"], "skip": True}
            else:
                cell = {"t": text, "rs": 1, "cs": span, "skip": False}
                if vmerge == "restart":
                    owners[col] = (ri, col)
                else:
                    owners.pop(col, None)
            row.append(cell)
            for k in range(1, span):
                row.append({"t": cell["t"], "skip": True})
            col += span
        rows.append(row)
    ncol = max((len(r) for r in rows), default=0)
    for r in rows:
        while len(r) < ncol:
            r.append({"t": "", "rs": 1, "cs": 1, "skip": False})
    return rows


def parse_docx(path: str | Path) -> list[Block]:
    d = docx.Document(str(path))
    part = d.part
    blocks: list[Block] = []
    counters = [0] * 7
    pidx = 0

    def walk(container):
        nonlocal pidx
        for el in container.iterchildren():
            tag = el.tag
            if tag == qn("w:sdt"):
                content = el.find(qn("w:sdtContent"))
                if content is not None:
                    walk(content)
                continue
            if tag == qn("w:tbl"):
                grid = _table_grid(el)
                if grid:
                    blocks.append(Block(kind="table", grid=grid, loc=f"para {pidx}"))
                    # pictures / charts inside table cells become figures right after the table; the row is kept in
                    # the location so a picture in a requirement row is linked to that requirement
                    for ri, tr in enumerate(el.findall(qn("w:tr"))):
                        blocks.extend(_media_blocks(tr, part, f"para {pidx} row {ri + 1}"))
                continue
            if tag != qn("w:p"):
                continue
            pidx += 1
            p = docx.text.paragraph.Paragraph(el, d._body)
            text = _para_text_main(el)
            style = p.style.name if p.style is not None else ""
            level = None
            ppr = el.find(qn("w:pPr"))
            if ppr is not None and ppr.find(qn("w:outlineLvl")) is not None:
                v = int(ppr.find(qn("w:outlineLvl")).get(qn("w:val")))
                level = v + 1 if v < 9 else None
            if level is None and p.style is not None:
                level = _style_outline_level(p.style)
            if style.lower() == "title":
                level = None
            list_level = -1
            if ppr is not None and ppr.find(qn("w:numPr")) is not None:
                il = ppr.find(qn("w:numPr")).find(qn("w:ilvl"))
                list_level = int(il.get(qn("w:val"))) if il is not None else 0

            if level and text:
                m = HEADING_NUM.match(text)
                if m:
                    number, title = m.group(1), m.group(2)
                    level = number.count(".") + 1
                    parts = [int(x) for x in number.split(".")]
                    for i in range(1, 7):
                        counters[i] = parts[i - 1] if i <= len(parts) else 0
                else:
                    counters[level] += 1
                    for i in range(level + 1, 7):
                        counters[i] = 0
                    number = ".".join(str(counters[i] or 1) for i in range(1, level + 1))
                    title = text
                blocks.append(Block(kind="heading", text=title, level=level, number=number, style=style,
                                    loc=f"para {pidx}"))
            elif text:
                blocks.append(Block(kind="para", text=text, style=style, loc=f"para {pidx}", list_level=list_level))
            media = _media_blocks(el, part, f"para {pidx}", style)
            imgs = [b for b in media if b.image is not None or b.style == "smartart"]
            blocks.extend(media)
            # Diagrams drawn with Word shapes have no bitmap: keep them as a figure carrying the shape labels
            if not imgs and (any(True for _ in el.iter("{http://schemas.microsoft.com/office/word/2010/wordprocessingShape}wsp"))
                             or any(True for _ in el.iter("{http://schemas.microsoft.com/office/word/2010/wordprocessingGroup}wgp"))):
                labels = []
                for box in el.iter(qn("w:txbxContent")):
                    bt = " ".join(t for t in (_para_text(pp) for pp in box.iter(qn("w:p"))) if t)
                    if bt and bt not in labels:
                        labels.append(bt)
                blocks.append(Block(kind="figure", text=" | ".join(labels), style="vector-shapes", loc=f"para {pidx}"))

    walk(d.element.body)
    return attach_captions(blocks)


def attach_captions(blocks: list[Block]) -> list[Block]:
    """Move '그림 N ...' / '표 N ...' paragraphs into the figure/table they describe."""
    from .blocks import CAPTION_FIG, CAPTION_TBL
    used = set()
    for i, b in enumerate(blocks):
        if b.kind not in ("figure", "table"):
            continue
        pat = CAPTION_FIG if b.kind == "figure" else CAPTION_TBL
        # tables: caption usually above; figures: caption usually below
        order = [i - 1, i + 1] if b.kind == "table" else [i + 1, i - 1]
        for j in order:
            if 0 <= j < len(blocks) and j not in used and blocks[j].kind == "para" and pat.match(blocks[j].text):
                b.caption = blocks[j].text
                used.add(j)
                break
    # several consecutive figures sharing one caption below: give it to all of them
    return [b for k, b in enumerate(blocks) if k not in used]
