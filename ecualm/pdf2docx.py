"""PDF -> Word (.docx) that can be edited: real headings, paragraphs, tables and pictures.

Built on the same PDF analysis as the importer (headings by numbering and font, tables with merged cells,
figures rendered from the page), so the result is a clean, restructured document — not a pixel copy of the PDF
layout. Page headers/footers, columns and exact fonts are not reproduced.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

NUM = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s+\S")


def convert(pdf: Path, out: Path) -> dict:
    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt
    import pymupdf
    from .importer import parse_any

    pdf = Path(pdf)
    try:
        src = pymupdf.open(pdf)
    except Exception as e:
        raise ValueError(f"PDF 를 열 수 없습니다 ({e})")
    if src.needs_pass:
        raise ValueError("암호가 걸린 PDF 는 변환할 수 없습니다 — 암호를 푼 뒤 다시 시도하세요")
    pages = len(src)
    chars = sum(len(p.get_text("text").strip()) for p in src)
    src.close()
    if chars < 20 * max(1, pages) and chars < 200:
        raise ValueError("글자가 들어 있지 않은 PDF 입니다 (스캔 이미지). 문자 인식(OCR)을 거친 PDF 만 변환할 수 있습니다")

    blocks = parse_any(pdf)
    d = Document()
    for name in ("Normal", "Heading 1", "Heading 2", "Heading 3", "Heading 4", "Title"):
        st = d.styles[name]
        st.font.name = "Malgun Gothic"
        st.element.rPr.rFonts.set(qn("w:eastAsia"), "Malgun Gothic")
    d.styles["Normal"].font.size = Pt(10.5)
    sec = d.sections[0]
    sec.left_margin = sec.right_margin = Cm(2.2)
    width = sec.page_width - sec.left_margin - sec.right_margin
    stats = {"pages": pages, "headings": 0, "paragraphs": 0, "tables": 0, "figures": 0, "skipped_images": 0}

    def caption(text):
        if text:
            p = d.add_paragraph(text)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for r in p.runs:
                r.font.size = Pt(9.5); r.bold = True

    for b in blocks:
        if b.kind == "heading":
            lvl = b.level or (NUM.match(b.text).group(1).count(".") + 1 if NUM.match(b.text) else 1)
            text = b.text if not b.number or b.text.lstrip().startswith(b.number) else f"{b.number} {b.text}"
            d.add_heading(text, max(1, min(4, int(lvl))))
            stats["headings"] += 1
        elif b.kind == "para":
            if not b.text.strip():
                continue
            if b.list_level >= 0:
                p = d.add_paragraph(re.sub(r"^\s*[•·▪■◦\-–*]\s+", "", b.text), style="List Bullet")
                if b.list_level > 0:
                    p.paragraph_format.left_indent = Cm(0.63 * (b.list_level + 1))
            else:
                for line in b.text.split("\n"):
                    if line.strip():
                        d.add_paragraph(line)
            stats["paragraphs"] += 1
        elif b.kind == "table" and b.grid:
            caption(b.caption)
            rows, cols = len(b.grid), max(len(r) for r in b.grid)
            t = d.add_table(rows=rows, cols=cols)
            t.style = "Table Grid"
            t.alignment = WD_TABLE_ALIGNMENT.CENTER
            for ri, row in enumerate(b.grid):
                for ci, c in enumerate(row):
                    if c.get("skip"):
                        continue
                    cell = t.cell(ri, ci)
                    rs, cs = int(c.get("rs") or 1), int(c.get("cs") or 1)
                    if rs > 1 or cs > 1:
                        cell = cell.merge(t.cell(min(rows - 1, ri + rs - 1), min(cols - 1, ci + cs - 1)))
                    cell.text = c.get("t", "")
                    for p in cell.paragraphs:
                        for r in p.runs:
                            r.font.size = Pt(9.5)
                            r.bold = ri == 0
            # column widths follow the content (a requirement column gets more room than an ID column)
            wt = [min(60, max(4, max((sum(2 if ord(ch) > 0x2E80 else 1 for ch in (r[ci].get("t", "") if ci < len(r) else ""))
                                      for r in b.grid if not (ci < len(r) and int(r[ci].get("cs") or 1) > 1)), default=4)))
                  for ci in range(cols)]
            t.autofit = False
            for ci, wgt in enumerate(wt):
                for cell in t.columns[ci].cells:
                    cell.width = int(width * wgt / sum(wt))
            d.add_paragraph()
            stats["tables"] += 1
        elif b.kind == "figure":
            done = False
            if b.image:
                try:
                    from PIL import Image
                    im = Image.open(io.BytesIO(b.image))
                    w_emu = int(im.width / (im.info.get("dpi", (96, 96))[0] or 96) * 914400)
                    buf = io.BytesIO()
                    (im.convert("RGB") if im.mode in ("P", "CMYK") else im).save(buf, "PNG")
                    buf.seek(0)
                    d.add_picture(buf, width=min(width, max(Cm(4), w_emu)))
                    d.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
                    done = True
                except Exception:
                    stats["skipped_images"] += 1
            if not done and b.text:
                d.add_paragraph(f"[그림 — 글자만 추출됨] {b.text}")
            caption(b.caption)
            stats["figures"] += 1
    d.core_properties.title = pdf.stem
    d.core_properties.comments = f"Converted from {pdf.name} by ECU-ALM"
    d.save(out)
    return stats
