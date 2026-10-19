"""Small spec with non-text content, in two revisions (for the figure / table / chart linking demo and tests).

  python samples/make_media_sample.py  ->  samples/CRS_media_demo_rev1.docx, samples/CRS_media_demo_rev2.docx

Contains: a native Word line chart and bar chart (data only, no picture — Word draws them), a captioned table,
an equation (OMML), a picture anchored inside a requirement paragraph, a picture inside a requirement-table row,
and requirements that refer to "그림 1" / "표 1". Rev 2 moves one point of the torque curve, changes one table
value and redraws the connector picture.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from docx.oxml import parse_xml
from docx.shared import Cm

OUT = Path(__file__).parent
CT_CHART = "application/vnd.openxmlformats-officedocument.drawingml.chart+xml"
NSD = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
       'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
       'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
       'xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" '
       'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')


def _chart_xml(kind: str, title: str, cats: list, series: list, xt: str, yt: str) -> bytes:
    def strcache(vals):
        return f'<c:strLit><c:ptCount val="{len(vals)}"/>' + "".join(
            f'<c:pt idx="{i}"><c:v>{v}</c:v></c:pt>' for i, v in enumerate(vals)) + "</c:strLit>"

    def numcache(vals):
        return f'<c:numLit><c:formatCode>General</c:formatCode><c:ptCount val="{len(vals)}"/>' + "".join(
            f'<c:pt idx="{i}"><c:v>{v}</c:v></c:pt>' for i, v in enumerate(vals)) + "</c:numLit>"

    def tx(t):
        return f'<c:tx><c:rich><a:bodyPr/><a:p><a:r><a:t>{t}</a:t></a:r></a:p></c:rich></c:tx>'
    sers = "".join(f'<c:ser><c:idx val="{k}"/><c:order val="{k}"/><c:tx><c:v>{n}</c:v></c:tx>'
                   f'<c:cat>{strcache(cats)}</c:cat><c:val>{numcache(v)}</c:val></c:ser>'
                   for k, (n, v) in enumerate(series))
    extra = '<c:barDir val="col"/><c:grouping val="clustered"/>' if kind == "barChart" else '<c:grouping val="standard"/>'
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<c:chartSpace {NSD}><c:chart><c:title>{tx(title)}<c:overlay val="0"/></c:title><c:plotArea><c:layout/>'
            f'<c:{kind}>{extra}{sers}<c:axId val="1"/><c:axId val="2"/></c:{kind}>'
            f'<c:catAx><c:axId val="1"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:delete val="0"/>'
            f'<c:axPos val="b"/><c:title>{tx(xt)}</c:title><c:crossAx val="2"/></c:catAx>'
            f'<c:valAx><c:axId val="2"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:delete val="0"/>'
            f'<c:axPos val="l"/><c:title>{tx(yt)}</c:title><c:crossAx val="1"/></c:valAx>'
            f'</c:plotArea><c:plotVisOnly val="1"/></c:chart></c:chartSpace>').encode("utf-8")


def add_chart(doc, n: int, xml: bytes) -> None:
    part = Part(PackURI(f"/word/charts/chart{n}.xml"), CT_CHART, xml, doc.part.package)
    rid = doc.part.relate_to(part, RT.CHART)
    p = doc.add_paragraph()
    p._p.append(parse_xml(
        f'<w:r {NSD}><w:drawing><wp:inline><wp:extent cx="5400000" cy="3000000"/><wp:docPr id="{100 + n}" name="Chart {n}"/>'
        f'<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/chart">'
        f'<c:chart r:id="{rid}"/></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>'))


def omml(p, text_before: str) -> None:
    """Paragraph text followed by the equation  I_ref = T_req / K_t  (Office Math)."""
    p.add_run(text_before)
    p._p.append(parse_xml(
        '<m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">'
        '<m:sSub><m:e><m:r><m:t>I</m:t></m:r></m:e><m:sub><m:r><m:t>ref</m:t></m:r></m:sub></m:sSub>'
        '<m:r><m:t>=</m:t></m:r><m:f><m:num><m:sSub><m:e><m:r><m:t>T</m:t></m:r></m:e><m:sub><m:r><m:t>req</m:t></m:r></m:sub></m:sSub></m:num>'
        '<m:den><m:sSub><m:e><m:r><m:t>K</m:t></m:r></m:e><m:sub><m:r><m:t>t</m:t></m:r></m:sub></m:sSub></m:den></m:f></m:oMath>'))


def picture(color: str, label: str) -> io.BytesIO:
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (360, 160), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([10, 10, 350, 150], outline="#333333", width=3)
    for i in range(6):
        d.rectangle([30 + i * 52, 60, 66 + i * 52, 110], fill=color)
        d.text((40 + i * 52, 118), str(i + 1), fill="#111111")
    d.text((20, 20), label, fill="#111111")
    b = io.BytesIO(); im.save(b, "PNG"); b.seek(0)
    return b


def build(rev: int) -> Path:
    d = Document()
    d.add_heading("모터 제어기 고객 요구사양서 (그림·표 예제)", level=0)
    d.add_paragraph(f"개정 {rev}.0 · 그림·차트·표·수식이 들어간 요구사항 예제 문서")
    d.add_heading("1 토크 특성", level=1)
    d.add_paragraph("[REQ-TRQ-001] 제어기는 그림 1의 토크-속도 한계 곡선을 넘지 않도록 출력 토크를 제한해야 한다.")
    curve = [12.0, 12.0, 11.5, 9.0, 6.5, 4.0] if rev == 1 else [12.0, 12.0, 11.0, 8.5, 6.5, 4.0]
    add_chart(d, 1, _chart_xml("lineChart", "토크 한계 곡선", ["0", "1000", "2000", "3000", "4000", "5000"],
                               [("최대 토크", curve), ("연속 토크", [8.0, 8.0, 7.5, 6.0, 4.5, 3.0])], "속도 (rpm)", "토크 (N·m)"))
    d.add_paragraph("그림 1 토크-속도 한계 곡선")
    d.add_paragraph("[REQ-TRQ-002] 인버터 온도 구간별 토크 디레이팅은 표 1에 따라야 한다.")
    d.add_paragraph("표 1 온도별 토크 디레이팅")
    t = d.add_table(rows=1, cols=2); t.style = "Table Grid"
    t.rows[0].cells[0].text, t.rows[0].cells[1].text = "인버터 온도", "허용 토크 (%)"
    for a, b in [("≤ 90°C", "100"), ("90 ~ 110°C", "80" if rev == 1 else "70"), ("> 110°C", "0")]:
        r = t.add_row().cells; r[0].text, r[1].text = a, b
    p = d.add_paragraph()
    omml(p, "[REQ-TRQ-003] 목표 전류는 요구 토크와 토크 상수로부터 다음 식으로 계산해야 한다: ")
    p = d.add_paragraph("[REQ-TRQ-004] 모터 커넥터 핀 배치는 아래 도면과 같아야 한다. ")
    p.add_run().add_picture(picture("#2F6FB2" if rev == 1 else "#B4466A", "CONNECTOR X1"), width=Cm(7))
    d.add_heading("2 인터페이스", level=1)
    t = d.add_table(rows=1, cols=3); t.style = "Table Grid"
    for c, h in zip(t.rows[0].cells, ["ID", "요구사항", "형상"]):
        c.text = h
    r = t.add_row().cells
    r[0].text, r[1].text = "REQ-IF-001", "센서 커넥터는 6핀 방수 커넥터를 사용해야 한다."
    r[2].paragraphs[0].add_run().add_picture(picture("#3A9A5B", "SENSOR X2"), width=Cm(4))
    r = t.add_row().cells
    r[0].text, r[1].text, r[2].text = "REQ-IF-002", "CAN 종단 저항은 120Ω이어야 한다.", "—"
    d.add_heading("3 시험 조건", level=1)
    add_chart(d, 2, _chart_xml("barChart", "시험 온도별 사이클 수", ["-40°C", "25°C", "85°C", "105°C"],
                               [("사이클", [200, 1000, 500, 300])], "온도", "사이클"))
    d.add_paragraph("그림 2 시험 온도 분포")
    out = OUT / f"CRS_media_demo_rev{rev}.docx"
    d.save(out)
    return out


if __name__ == "__main__":
    for r in (1, 2):
        print(build(r))
    if len(sys.argv) > 1 and sys.argv[1] == "--pdf":
        sys.path.insert(0, str(OUT))
        from make_eps_crs import to_pdf
        for r in (1, 2):
            print(to_pdf(OUT / f"CRS_media_demo_rev{r}.docx"))
