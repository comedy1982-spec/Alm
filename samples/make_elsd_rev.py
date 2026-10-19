"""Make rev 1.1 of the eLSD customer spec from rev 1.0 with typical customer changes (for the change-analysis demo).

  python samples/make_elsd_rev.py   ->  samples/CRS_eLSD_ECU_rev1.1.docx (+ .pdf with LibreOffice)

Changes: a limit tightened, a detection threshold changed, a limit relaxed, an ASIL raised, a mandatory requirement
softened to a recommendation, a prohibition added, scope extended, an editorial-only edit, a requirement withdrawn
and a new requirement added. The revision history table says what changed, as a customer document would.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

from docx import Document

OUT = Path(__file__).parent
SRC = OUT / "CRS_eLSD_ECU_rev1.0.docx"

# (text that identifies the requirement, old fragment, new fragment)
TEXT_EDITS = [
    ("120ms 이내에 90%에 도달해야 한다", "120ms 이내에", "100ms 이내에"),                                   # tightened limit
    ("ESC 협조 메시지가 30ms 이상 수신되지 않거나", "30ms 이상", "20ms 이상"),                               # detection threshold
    ("SLEEP 상태 암전류는", "80µA 이하", "100µA 이하"),                                                     # relaxed limit
    ("런치 대기 중 eLSD 제어기는 잠금 토크를 600 N·m로 프리로드해야 한다", "프리로드해야 한다", "프리로드하는 것이 바람직하다"),  # must -> should
    ("OFF-ROAD 모드는 차속 40 km/h를 초과하면", "40 km/h를 초과하면", "40 km/h를 초과하거나 클러치 추정 온도가 140°C를 넘으면"),  # scope
    ("0x2F 서비스로 볼램프 위치를 강제 구동하는", "차속 0 km/h에서만 허용해야 한다.", "차속 0 km/h에서만 허용해야 하며, TRACK 모드에서는 허용하지 않아야 한다."),  # prohibition
    ("주변 온도 -40°C ~ +105°C에서 모든 기능을", "수행해야 한다.", "수행하여야 한다."),                       # editorial only
]
ASIL_EDITS = {"REQ-THERM-003": "C"}           # table ASIL column
DELETE_ROWS = ["REQ-LOCK-012"]                 # launch preload release after 10 s (withdrawn)
NEW_ROW_AFTER = ("REQ-SEC-006", "REQ-SEC-007",
                 "SecOC 신선도 값 동기화가 1초 이상 실패하면 eLSD 제어기는 DTC U1102를 저장하고 잠금 토크를 200 N·m 이하로 제한해야 한다.",
                 "QM", "CANoe (신선도 오류 주입)")


def _set_text(par_or_cell, old, new) -> bool:
    paras = par_or_cell.paragraphs if hasattr(par_or_cell, "paragraphs") else [par_or_cell]
    for p in paras:
        if old in p.text:
            full = p.text.replace(old, new, 1)
            for r in p.runs[1:]:
                r.text = ""
            if p.runs:
                p.runs[0].text = full
            else:
                p.add_run(full)
            return True
    return False


def build() -> Path:
    d = Document(SRC)
    done = []
    for key, old, new in TEXT_EDITS:
        hit = False
        for p in d.paragraphs:
            if key in p.text and _set_text(p, old, new):
                hit = True; break
        if not hit:
            for t in d.tables:
                for row in t.rows:
                    for c in row.cells:
                        if key in c.text and _set_text(c, old, new):
                            hit = True; break
                    if hit: break
                if hit: break
        if not hit:
            sys.exit(f"edit target not found: {key}")
        done.append(key)
    for t in d.tables:
        for row in list(t.rows):
            first = row.cells[0].text.strip()
            if first in ASIL_EDITS and len(row.cells) >= 3:
                c = row.cells[2]; c.paragraphs[0].runs[0].text = ASIL_EDITS[first]
                for r in c.paragraphs[0].runs[1:]:
                    r.text = ""
            if first in DELETE_ROWS and len(row.cells) == 4:
                row._tr.getparent().remove(row._tr)
            if first == NEW_ROW_AFTER[0] and len(row.cells) == 4:
                tr = copy.deepcopy(row._tr)
                row._tr.addnext(tr)
                from docx.table import _Row
                nr = _Row(tr, t)
                for c, v in zip(nr.cells, NEW_ROW_AFTER[1:]):
                    for p in c.paragraphs[1:]:
                        p._p.getparent().remove(p._p)
                    p = c.paragraphs[0]
                    for r in p.runs[1:]:
                        r.text = ""
                    p.runs[0].text = v
    # revision history + document number on the cover
    for p in d.paragraphs:
        if "개정 1.0" in p.text:
            _set_text(p, "개정 1.0", "개정 1.1")
    hist = d.tables[0]
    tr = copy.deepcopy(hist.rows[-1]._tr)
    hist.rows[-1]._tr.addnext(tr)
    from docx.table import _Row
    nr = _Row(tr, hist)
    for c, v in zip(nr.cells, ["1.1", "2026-11-20", "서구동", "B 샘플 피드백 반영: 액추에이터 응답 100ms, ESC 협조 타임아웃 20ms, 열 제한 ASIL C, "
                                                         "런치 프리로드 권고로 변경·해제 조건 삭제, OFF-ROAD 전환 조건 추가, SecOC 동기화 요구 추가"]):
        p = c.paragraphs[0]
        for r in p.runs[1:]:
            r.text = ""
        p.runs[0].text = v
    for s in d.sections:
        for p in s.header.paragraphs:
            if "CRS-LSD" in p.text:
                pass
    out = OUT / "CRS_eLSD_ECU_rev1.1.docx"
    d.save(out)
    print(f"{len(done)} text edits, ASIL {len(ASIL_EDITS)}, deleted {len(DELETE_ROWS)}, added 1")
    return out


if __name__ == "__main__":
    o = build()
    print(o)
    sys.path.insert(0, str(OUT))
    from make_eps_crs import to_pdf
    pdf = to_pdf(o)
    if pdf:
        print(pdf)
