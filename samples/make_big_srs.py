"""Generate a realistic, 30+ page integrated SRS for a BLDC position-control ECU.

python samples/make_big_srs.py  ->  samples/SRS_BLDC_Full_revA.docx  (+ revB with ~20 changes)

The document mixes system-level (HW / mechanical / environment) and software-level requirements the
way a real supplier SRS does, with revision history, glossary, block/state/timing figures, DBC and
UDS tables, a TC364 pin map, and explanatory text between requirements.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from matplotlib.patches import FancyBboxPatch

plt.rcParams["font.family"] = ["Noto Sans CJK KR", "Noto Sans CJK SC", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

OUT = Path(__file__).parent
_FIG = {}


# ----------------------------------------------------------------------------- figures
def fig_block() -> bytes:
    fig, ax = plt.subplots(figsize=(7.4, 3.4), dpi=140); ax.axis("off")
    boxes = {"Vehicle\nCAN": (0.03, 0.55), "CAN XCVR\nTJA1043": (0.2, 0.55), "TC364\nMCU": (0.4, 0.55), "Gate Driver\nDRV8305": (0.6, 0.55),
             "3-phase\nInverter": (0.78, 0.55), "BLDC Motor\n+ Hall x3": (0.78, 0.12), "PMIC\nTLF35584": (0.4, 0.12), "Position\nSensor (AS5047)": (0.6, 0.12)}
    for t, (x, y) in boxes.items():
        ax.add_patch(FancyBboxPatch((x, y), 0.15, 0.3, boxstyle="round,pad=0.015", fc="#EEF3FC", ec="#1F5FBF", lw=1.4))
        ax.text(x + 0.075, y + 0.15, t, ha="center", va="center", fontsize=8.5)
    def arrow(a, b, two=True, dy=0):
        (x0, y0), (x1, y1) = boxes[a], boxes[b]
        ax.annotate("", xy=(x1 - 0.005, y1 + 0.15 + dy), xytext=(x0 + 0.155, y0 + 0.15 + dy), arrowprops=dict(arrowstyle="<->" if two else "->", color="#333"))
    arrow("Vehicle\nCAN", "CAN XCVR\nTJA1043"); arrow("CAN XCVR\nTJA1043", "TC364\nMCU"); arrow("TC364\nMCU", "Gate Driver\nDRV8305", False); arrow("Gate Driver\nDRV8305", "3-phase\nInverter", False)
    ax.annotate("", xy=(0.855, 0.43), xytext=(0.855, 0.55), arrowprops=dict(arrowstyle="->", color="#333")); ax.text(0.87, 0.49, "U/V/W", fontsize=7)
    ax.annotate("", xy=(0.475, 0.55), xytext=(0.475, 0.43), arrowprops=dict(arrowstyle="->", color="#333")); ax.text(0.49, 0.47, "5V/3.3V", fontsize=7)
    ax.annotate("", xy=(0.55, 0.62), xytext=(0.675, 0.42), arrowprops=dict(arrowstyle="->", color="#1E7A3A")); ax.text(0.56, 0.44, "SPI angle", fontsize=7, color="#1E7A3A")
    ax.annotate("", xy=(0.56, 0.6), xytext=(0.78, 0.3), arrowprops=dict(arrowstyle="->", color="#1E7A3A")); ax.text(0.63, 0.35, "Hall A/B/C", fontsize=7, color="#1E7A3A")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    b = BytesIO(); fig.savefig(b, format="png", bbox_inches="tight"); plt.close(fig); return b.getvalue()


def fig_states() -> bytes:
    fig, ax = plt.subplots(figsize=(7.4, 3.2), dpi=140); ax.axis("off")
    st = {"INIT": (0.06, 0.55), "NORMAL": (0.36, 0.55), "DEGRADED": (0.66, 0.78), "FAILSAFE": (0.66, 0.32), "SLEEP": (0.36, 0.08)}
    col = {"INIT": "#EEF3FC", "NORMAL": "#E3F4E7", "DEGRADED": "#FFF3DC", "FAILSAFE": "#FCEEED", "SLEEP": "#EEF1F5"}
    for n, (x, y) in st.items():
        ax.add_patch(FancyBboxPatch((x, y), 0.18, 0.17, boxstyle="round,pad=0.015", fc=col[n], ec="#333", lw=1.2)); ax.text(x + 0.09, y + 0.085, n, ha="center", va="center", fontsize=9, weight="bold")
    def ar(a, b, label, off=(0, 0.04), rad=0.0):
        (x0, y0), (x1, y1) = st[a], st[b]
        ax.annotate("", xy=(x1 + 0.09, y1 + 0.085), xytext=(x0 + 0.09, y0 + 0.085), arrowprops=dict(arrowstyle="->", color="#333", shrinkA=18, shrinkB=18, connectionstyle=f"arc3,rad={rad}"))
        ax.text((x0 + x1) / 2 + 0.09 + off[0], (y0 + y1) / 2 + 0.085 + off[1], label, ha="center", fontsize=7)
    ar("INIT", "NORMAL", "SelfTest OK (<200ms)"); ar("NORMAL", "DEGRADED", "Warning level fault", (-0.02, 0.05)); ar("DEGRADED", "NORMAL", "Fault healed 3 cycles", (0.04, -0.06), 0.3)
    ar("NORMAL", "FAILSAFE", "Critical fault", (0.0, -0.06)); ar("DEGRADED", "FAILSAFE", "Escalation", (0.06, 0)); ar("NORMAL", "SLEEP", "IG OFF & idle 3s", (-0.1, 0)); ar("SLEEP", "INIT", "CAN wake-up / IG ON", (-0.2, 0.02), 0.4)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    b = BytesIO(); fig.savefig(b, format="png", bbox_inches="tight"); plt.close(fig); return b.getvalue()


def fig_profile() -> bytes:
    t = np.linspace(0, 0.6, 400)
    pos = np.where(t < 0.1, 0, np.where(t < 0.35, 45 * (1 - np.cos(np.pi * (t - 0.1) / 0.25)) / 2, 45))
    vel = np.gradient(pos, t)
    fig, ax = plt.subplots(figsize=(7.4, 3.0), dpi=140)
    ax.plot(t * 1000, pos, color="#1F5FBF", lw=1.8, label="위치 [deg]"); ax2 = ax.twinx(); ax2.plot(t * 1000, vel, color="#B4530A", lw=1.2, ls="--", label="속도 [deg/s]")
    ax.axhline(45, color="#999", lw=.8, ls=":"); ax.axvspan(100, 350, color="#1F5FBF", alpha=.06); ax.axvline(400, color="#B3261E", lw=.8, ls=":"); ax.text(405, 2, "t_settle ≤ 300ms", fontsize=7, color="#B3261E")
    ax.set_xlabel("time [ms]"); ax.set_ylabel("position [deg]"); ax2.set_ylabel("velocity [deg/s]"); ax.grid(alpha=.3)
    ax.legend(loc="upper left", fontsize=7); ax2.legend(loc="lower right", fontsize=7)
    b = BytesIO(); fig.savefig(b, format="png", bbox_inches="tight"); plt.close(fig); return b.getvalue()


def fig_timing() -> bytes:
    fig, ax = plt.subplots(figsize=(7.4, 2.6), dpi=140); ax.axis("off")
    rows = [("100 µs  ISR  (EVADC → FOC 전류 루프)", 0.8, "#B3261E", [i * 0.03 for i in range(31)], 0.006),
            ("1 ms   Task (위치/속도 루프, Hall 처리)", 0.58, "#1F5FBF", [i * 0.1 for i in range(10)], 0.02),
            ("10 ms  Task (CAN Rx/Tx, 진단, 고장 디바운스)", 0.36, "#1E7A3A", [0, 0.5], 0.1),
            ("100 ms Task (NvM, 온도 감시, 통계)", 0.14, "#8A5A00", [0], 0.3)]
    for name, y, c, starts, w in rows:
        ax.text(0, y + 0.07, name, fontsize=7.5)
        for s in starts:
            ax.add_patch(plt.Rectangle((0.02 + s * 0.95, y - 0.02), w * 0.95, 0.06, color=c))
    ax.text(0.02, -0.02, "0", fontsize=7); ax.text(0.95, -0.02, "1 ms", fontsize=7); ax.set_xlim(0, 1); ax.set_ylim(-0.05, 1)
    b = BytesIO(); fig.savefig(b, format="png", bbox_inches="tight"); plt.close(fig); return b.getvalue()


def fig_lv() -> bytes:
    t = np.linspace(0, 1.2, 600); v = 13.5 - 5 * np.exp(-((t - 0.5) ** 2) / 0.01)
    fig, ax = plt.subplots(figsize=(7.4, 2.6), dpi=140); ax.plot(t * 1000, v, color="#1F5FBF"); ax.axhline(9, color="#B3261E", ls="--", lw=.9); ax.axhline(6, color="#B4530A", ls="--", lw=.9)
    ax.text(10, 9.2, "UV 경고 9.0V (300ms 디바운스)", fontsize=7, color="#B3261E"); ax.text(10, 6.2, "UV 리셋 6.0V", fontsize=7, color="#B4530A")
    ax.set_xlabel("time [ms]"); ax.set_ylabel("KL30 [V]"); ax.grid(alpha=.3)
    b = BytesIO(); fig.savefig(b, format="png", bbox_inches="tight"); plt.close(fig); return b.getvalue()


def F(name):
    if name not in _FIG:
        _FIG[name] = {"block": fig_block, "states": fig_states, "profile": fig_profile, "timing": fig_timing, "lv": fig_lv}[name]()
    return _FIG[name]


# ----------------------------------------------------------------------------- doc helpers
class Doc:
    def __init__(self, rev: str):
        self.rev = rev
        self.d = Document()
        st = self.d.styles["Normal"]; st.font.name = "Malgun Gothic"; st.element.rPr.rFonts.set(qn("w:eastAsia"), "Malgun Gothic"); st.font.size = Pt(10.5)
        st.paragraph_format.line_spacing = 1.3; st.paragraph_format.space_after = Pt(4)
        for s in ("Heading 1", "Heading 2", "Heading 3"):
            self.d.styles[s].font.name = "Malgun Gothic"; self.d.styles[s].element.rPr.rFonts.set(qn("w:eastAsia"), "Malgun Gothic")
        sec = self.d.sections[0]; sec.left_margin = sec.right_margin = Cm(2.2); sec.top_margin = sec.bottom_margin = Cm(2.0)
        sec.header.paragraphs[0].text = "SRS-BLDC-ACT-001   |   BLDC Position Actuator ECU   |   사내 대외비"
        sec.footer.paragraphs[0].text = f"ACME Mobility Co.  ·  Rev {rev}  ·  본 문서는 ASPICE PAM 4.0 SYS.2 / SWE.1 산출물의 원천 자료이다."
        self.n = {"fig": 0, "tbl": 0}; self.req = {}

    def h(self, t, l=1): self.d.add_heading(t, l)
    def p(self, t, italic=False):
        para = self.d.add_paragraph(); r = para.add_run(t); r.italic = italic; return para
    def note(self, t):
        para = self.d.add_paragraph(); r = para.add_run("참고: " + t); r.font.size = Pt(9); r.font.color.rgb = RGBColor(0x55, 0x60, 0x6E)
    def bullets(self, items):
        for i in items: self.d.add_paragraph(i, style="List Bullet")
    def R(self, dom, text, rationale=None, verify=None, asil=None):
        """Numbered requirement with native ID, optional rationale / verification line."""
        self.req[dom] = self.req.get(dom, 0) + 1
        rid = f"REQ-{dom}-{self.req[dom]:03d}"
        para = self.d.add_paragraph(); r = para.add_run(f"[{rid}] "); r.bold = True; r.font.color.rgb = RGBColor(0x1F, 0x5F, 0xBF); para.add_run(text)
        meta = []
        if asil: meta.append(f"ASIL {asil}")
        if verify: meta.append(f"검증: {verify}")
        if rationale: meta.append(f"근거: {rationale}")
        if meta:
            q = self.d.add_paragraph(); q.paragraph_format.left_indent = Cm(1.0); rr = q.add_run(" · ".join(meta)); rr.font.size = Pt(8.5); rr.font.color.rgb = RGBColor(0x55, 0x60, 0x6E)
        return rid
    def fig(self, name, caption, width=15.5):
        self.n["fig"] += 1
        self.d.add_picture(BytesIO(F(name)), width=Cm(width)); self.d.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        c = self.d.add_paragraph(f"그림 {self.n['fig']} {caption}"); c.alignment = WD_ALIGN_PARAGRAPH.CENTER
    def table(self, caption, rows, widths=None, merges=()):
        self.n["tbl"] += 1
        self.d.add_paragraph(f"표 {self.n['tbl']} {caption}")
        t = self.d.add_table(rows=len(rows), cols=len(rows[0])); t.style = "Table Grid"; t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for i, r in enumerate(rows):
            for j, v in enumerate(r):
                if v is None: continue
                cell = t.cell(i, j); cell.text = str(v)
                for pp in cell.paragraphs:
                    for run in pp.runs:
                        run.font.size = Pt(8.5)
                        if i == 0: run.bold = True
                if i == 0:
                    sh = OxmlElement("w:shd"); sh.set(qn("w:fill"), "E8EFFA"); cell._tc.get_or_add_tcPr().append(sh)
        for (r0, c0, r1, c1) in merges:
            t.cell(r0, c0).merge(t.cell(r1, c1))
        if widths:
            for j, w in enumerate(widths):
                for row in t.rows: row.cells[j].width = Cm(w)
        self.d.add_paragraph()
        return t


# ----------------------------------------------------------------------------- content
def build(rev: str) -> Path:
    B = rev == "B"
    D = Doc(rev)
    d = D.d
    d.add_paragraph("BLDC 위치제어 액추에이터 ECU", style="Title")
    d.add_paragraph("통합 요구사항 명세서 (Integrated System / Software Requirements Specification)").alignment = WD_ALIGN_PARAGRAPH.CENTER
    d.add_paragraph(f"문서번호 SRS-BLDC-ACT-001   ·   개정 {rev}   ·   프로젝트 ACT-GEN3 (현대자동차 ES 96xxx 계열 적용)").alignment = WD_ALIGN_PARAGRAPH.CENTER
    d.add_paragraph()
    D.table("개정 이력", [["개정", "일자", "작성", "변경 내용"],
                         ["A", "2026-08-12", "김연구", "최초 배포. CRS 2.3 및 ES 전원규격 반영"],
                         *( [["B", "2026-10-10", "김연구", "CAN Timeout 500ms로 변경, 과온 보호 추가, IP 등급 요구 삭제(기구팀 이관), 위치 정확도 강화"]] if B else [])], widths=[1.5, 2.5, 2, 10])
    D.table("승인", [["역할", "이름", "부서", "서명/일자"], ["작성", "김연구", "SW 플랫폼", ""], ["검토", "이설계", "시스템 공학", ""], ["검토", "박품질", "품질보증(SQA)", ""], ["승인", "최PM", "프로젝트 관리", ""]])
    d.add_page_break()

    # 1 -----------------------------------------------------------------------
    D.h("1 개요")
    D.h("1.1 목적", 2)
    D.p("본 문서는 ACT-GEN3 프로젝트에서 개발하는 BLDC 위치제어 액추에이터 ECU(이하 제어기)의 시스템 요구사항과 소프트웨어 요구사항을 정의한다. 제어기는 차량 CAN을 통해 수신한 목표 위치 지령에 따라 BLDC 모터를 구동하여 밸브/플랩 액추에이터를 지정된 각도로 이동시키고, 그 상태를 차량에 보고한다.")
    D.p("본 문서는 Automotive SPICE PAM 4.0의 SYS.2(시스템 요구사항 분석) 및 SWE.1(소프트웨어 요구사항 분석) 프로세스 산출물의 원천이 된다. 각 요구사항은 고유 ID(REQ-<도메인>-<번호>)를 가지며, ALM 도구로 가져올 때 시스템/소프트웨어 레벨로 분리되고 검증 케이스와 추적된다.")
    D.h("1.2 적용 범위", 2)
    D.p("적용 범위는 제어기 하드웨어(PCB, 커넥터, 하우징 인터페이스), 임베디드 소프트웨어(AUTOSAR Classic 4.4 기반 ASW/CDD/BSW), 모터·센서 인터페이스, 차량 CAN 인터페이스, 진단 및 기능 안전 요구사항을 포함한다. 기구 액추에이터 본체의 상세 설계와 차량 측 제어 전략은 범위에서 제외한다.")
    D.h("1.3 참조 문서", 2)
    D.table("참조 문서", [["번호", "문서", "개정", "비고"], ["[1]", "고객 요구사항 명세 CRS-ACT-GEN3", "2.3", "OEM 발행"], ["[2]", "ES 96100-xx 전장 부품 전원 규격", "2024", "OEM 표준"],
                            ["[3]", "ES 95400-xx EMC 시험 규격", "2023", "OEM 표준"], ["[4]", "ISO 14229-1 UDS", "2020", "진단"], ["[5]", "ISO 26262-6", "2018", "기능 안전"],
                            ["[6]", "AUTOSAR Classic Platform R4.4", "4.4.0", "SW 플랫폼"], ["[7]", "ACT_GEN3_CAN.dbc", "1.4", "CAN 신호 정의"], ["[8]", "ACT_GEN3_Diag.cdd", "1.2", "진단 사양"],
                            ["[9]", "Infineon AURIX TC364 User Manual", "2.0", "MCU"], ["[10]", "TI DRV8305 Datasheet", "C", "게이트 드라이버"]], widths=[1.3, 8, 1.6, 4])
    D.h("1.4 용어 및 약어", 2)
    D.table("용어", [["약어", "의미"], ["ASW", "Application Software (AUTOSAR SWC)"], ["BSW", "Basic Software"], ["CDD", "Complex Device Driver"], ["DTC", "Diagnostic Trouble Code"],
                        ["FOC", "Field Oriented Control (벡터 제어)"], ["HSI", "Hardware-Software Interface"], ["IG", "Ignition (KL15)"], ["KL30", "상시 전원"], ["NvM", "Non-volatile Memory"],
                        ["PMIC", "Power Management IC"], ["RTE", "Runtime Environment"], ["UDS", "Unified Diagnostic Services (ISO 14229)"], ["UV / OV", "저전압 / 과전압"], ["WUP", "Wake-up Pattern"]], widths=[3, 12])
    D.h("1.5 요구사항 표기 규칙", 2)
    D.p("'해야 한다'는 필수 요구사항, '하는 것이 바람직하다'는 권고, '할 수 있다'는 허용을 의미한다. 각 요구사항에는 가능한 한 검증 방법(벤치, HIL, 차량, 환경 챔버, CANoe, 단위시험)과 ASIL 등급을 함께 표기한다. ASIL이 표기되지 않은 요구사항은 QM이다.")
    d.add_page_break()

    # 2 -----------------------------------------------------------------------
    D.h("2 시스템 개요")
    D.h("2.1 시스템 구성", 2)
    D.p("제어기는 Infineon AURIX TC364(TriCore 1.6.2, 300MHz, 2 코어)를 주 MCU로 사용하며, TI DRV8305 게이트 드라이버와 3상 MOSFET 인버터로 BLDC 모터를 구동한다. 모터 축에는 홀 센서 3개와 AS5047 자기식 절대 각도 센서가 장착된다. 전원은 PMIC TLF35584로 생성하며 안전 와치독과 전압 감시를 포함한다.")
    D.fig("block", "시스템 블록 구성")
    D.h("2.2 운용 모드", 2)
    D.p("제어기는 INIT, NORMAL, DEGRADED, FAILSAFE, SLEEP의 다섯 가지 운용 모드를 갖는다. 모드 천이 조건은 그림 2와 같으며 상세 조건은 4.3절에 정의한다.")
    D.fig("states", "전원 및 운용 모드 상태 천이")
    D.table("운용 모드 정의", [["모드", "설명", "모터 구동", "CAN 송신"], ["INIT", "전원 인가 후 자체 진단 및 영점 확인", "불가", "불가"], ["NORMAL", "위치 지령 추종", "가능", "주기 송신"],
                                  ["DEGRADED", "경고 수준 고장: 성능 제한 운전", "제한(토크 50%)", "주기 송신 + 경고 플래그"], ["FAILSAFE", "치명 고장: 안전 상태 유지", "차단(프리휠)", "상태 송신"], ["SLEEP", "IG OFF 저전력", "불가", "불가(WUP 대기)"]], widths=[2.5, 7, 3, 3])
    D.h("2.3 외부 인터페이스 개요", 2)
    D.table("외부 인터페이스", [["인터페이스", "상대", "물리", "프로토콜/규격", "비고"], ["차량 CAN", "VCU, 진단기", "CAN 2.0B 500kbps", "DBC 1.4, UDS, CanNm", "E2E Profile 1"], ["전원", "차량 배터리", "KL30, KL15, GND", "ES 96100", "모터 전원 분리"],
                               ["모터", "BLDC 모터", "3상 U/V/W", "-", "최대 15A 피크"], ["홀 센서", "모터 내장", "5V 오픈 컬렉터 x3", "-", "60° 전기각"], ["절대 각도 센서", "AS5047", "SPI 5MHz", "AS5047 프로토콜", "14bit"],
                               ["게이트 드라이버", "DRV8305", "SPI + PWM x6 + nFAULT", "DRV8305 레지스터 맵", "EN_GATE Shut-off"], ["PMIC", "TLF35584", "SPI + WDI", "TLF35584 프로토콜", "안전 와치독"]], widths=[2.8, 2.6, 3.2, 3.6, 3.3])
    D.h("2.4 동작 시나리오", 2)
    D.p("IG ON 시 제어기는 200ms 이내에 자체 진단을 완료하고 NORMAL 모드로 진입한다. 차량 제어기(VCU)는 10ms 주기로 목표 위치를 송신하며, 제어기는 FOC 전류 제어(100µs)와 위치/속도 제어(1ms)의 캐스케이드 구조로 목표를 추종한다. 그림 3은 0°→45° 스텝 지령에 대한 대표 응답을 나타낸다.")
    D.fig("profile", "45° 스텝 지령 응답 프로파일 (S-curve, t_settle ≤ 300 ms)")
    D.p("DEGRADED 모드는 성능을 제한하되 기능을 유지하는 모드이다. 예를 들어 절대 각도 센서가 고장 나면 홀 센서만으로 제어하되 최대 속도를 절반으로 낮춘다. FAILSAFE 모드는 모터를 프리휠 상태로 두어 기구가 셀프 로킹으로 현재 위치를 유지하도록 한다. 밸브 응용에서 '현재 위치 유지'가 안전 상태로 정의되어 있으므로(HARA 결과), 전원 차단 시에도 기구가 위치를 유지해야 한다(REQ-MOT-010).")
    D.p("IG OFF 후 3초 동안 지령이 없으면 SLEEP으로 진입하며, CAN WUP 또는 IG ON으로 기동한다. SLEEP에서의 암전류는 ES 전원 규격의 요구를 따른다.")
    D.h("2.5 사용 사례", 2)
    D.p("다음 사용 사례는 CRS[1] 3장에서 도출하였으며, 각 사용 사례는 하나 이상의 요구사항으로 구체화된다. 사용 사례 ID는 추적성 분석에서 요구사항의 상위 근거로 사용된다.")
    uc = [("UC-01 정상 위치 추종", "IG ON, NORMAL 모드", "VCU가 10ms 주기로 목표 위치를 갱신한다. 제어기는 S-curve 프로파일로 이동하고 도달 상태를 보고한다.", "위치 ±1°, 45° 이동 300ms 이내", "REQ-CTRL-001~007"),
          ("UC-02 전원 투입 및 초기화", "KL30 인가, IG ON", "자체 진단, 센서 오프셋 보정, 저장된 영점으로 초기 위치 계산 후 NORMAL 진입.", "200ms 이내 CAN 송신 시작", "REQ-MODE-001/002, REQ-CAL-006"),
          ("UC-03 저전압 크랭킹", "시동 중 KL30 6~9V", "모터 구동을 중지하고 통신을 유지한다. 회복 후 자동 재개.", "DTC B1601, 9.5V 회복 300ms 후 재개", "REQ-PWR-009/010, REQ-MODE-008/009"),
          ("UC-04 CAN 통신 상실", "ACT_CMD 미수신", "현재 위치 유지, DTC U0101 저장, 3 주기 정상 수신 시 복귀.", "Timeout 판정 시간 준수", "REQ-COM-002/003"),
          ("UC-05 기계적 구속", "이물질로 액추에이터 구속", "토크 제한 후 구속 판정, FAILSAFE 진입, 고장 로그 기록.", "500ms 이내 FAILSAFE, DTC B1720", "REQ-CTRL-012/013, REQ-FDET-009"),
          ("UC-06 영점 학습 (서비스)", "확장 세션, 보안 레벨 1, 정차", "진단기가 0x31 0xF010 요청. 양 스토퍼 검출 후 오프셋 저장.", "스토퍼 거리 96±2°", "REQ-CAL-001~004"),
          ("UC-07 SLEEP / 웨이크업", "IG OFF 후 3초", "NvM 쓰기 완료 후 SLEEP. WUP 또는 IG ON으로 기동.", "암전류 100µA 이하, 기동 100ms", "REQ-PWR-006/013/014, REQ-MODE-006/007"),
          ("UC-08 SW 재프로그래밍", "프로그래밍 세션, 정차", "부트로더로 전환하여 애플리케이션 다운로드, 서명 검증 후 활성화.", "전원 차단 복원성", "REQ-UPD-001~003, REQ-SEC-001/002")]
    for name, pre, flow, crit, reqs in uc:
        D.h(name, 3)
        D.table(name, [["항목", "내용"], ["전제 조건", pre], ["주 흐름", flow], ["성공 기준", crit], ["관련 요구사항", reqs]], widths=[3, 12.5])
    d.add_page_break()

    # 3 시스템 요구사항 ---------------------------------------------------------
    D.h("3 시스템 요구사항")
    D.p("본 장은 제어기 전체(하드웨어, 기구 인터페이스, 환경, 성능)에 대한 시스템 레벨 요구사항을 정의한다. 소프트웨어가 단독으로 충족하는 항목은 4장에 둔다.")
    D.h("3.1 전원", 2)
    D.p("전원 관련 요구사항은 ES 96100 전장 부품 전원 규격[2]을 기준으로 한다. 그림 4는 저전압 이벤트 시 전압 임계값의 정의를 보여준다.")
    D.fig("lv", "저전압 이벤트와 UV 임계값 정의")
    D.R("PWR", "제어기는 KL30 9V ~ 16V 작동 전압 범위에서 모든 기능을 정상 수행해야 한다.", "ES 96100 작동 전압 범위", "벤치(전원 공급기 스윕)")
    D.R("PWR", "제어기는 KL30 6V ~ 9V 범위에서 통신 및 진단 기능을 유지해야 하며 모터 구동은 제한할 수 있다.", "크랭킹 전압 구간", "벤치")
    D.R("PWR", "제어기는 KL30 16V ~ 18V 범위에서 1시간 동안 손상 없이 동작해야 한다.", "과전압 내성", "벤치")
    D.R("PWR", "제어기는 KL30 26V 점프 스타트 전압을 60초 동안 손상 없이 견뎌야 한다. 이 기간 동안 모터 구동은 차단될 수 있다.", "ES 96100 점프 스타트", "벤치")
    D.R("PWR", "제어기는 역극성 연결(-16V)에서 손상되지 않아야 한다.", None, "벤치")
    D.R("PWR", "IG OFF 상태(SLEEP)에서 제어기의 암전류는 KL30 12.6V, 25°C 조건에서 100uA 이하여야 한다.", "ES 96100 암전류", "벤치(정밀 전류계)")
    D.R("PWR", "NORMAL 모드 대기 상태(모터 정지)에서 제어기의 소비 전류는 60mA 이하여야 한다.", None, "벤치")
    D.R("PWR", "제어기는 모터 구동 중 최대 8A(피크 15A, 500ms)의 전류를 공급할 수 있어야 한다.", "모터 사양", "벤치(부하 다이나모)")
    D.R("PWR", "제어기는 KL30 전압이 9V 미만으로 300ms 이상 지속되면 저전압 상태로 판단하고 모터 구동을 중지해야 한다. 이때 DTC B1601을 저장해야 한다.", "그림 4", "HIL(전압 프로파일)")
    D.R("PWR", "제어기는 KL30 전압이 6V 미만으로 떨어지면 리셋될 수 있으며, 복귀 후 500ms 이내에 NORMAL 모드로 재진입해야 한다.", None, "HIL")
    D.R("PWR", "제어기는 ES 96100 전원 과도 펄스(Test pulse 1, 2a, 2b, 3a, 3b, 4)에 대해 기능 상태 등급 C 이상을 만족해야 한다.", "ES 96100", "EMC 시험소")
    D.R("PWR", "제어기는 IG ON 후 200ms 이내에 CAN 송신을 시작해야 한다.", "VCU 요구 (CRS 4.2)", "CANoe 타이밍 측정")
    D.R("PWR", "제어기는 IG OFF 후 3초 동안 CAN 메시지가 없으면 SLEEP 모드로 진입해야 한다.", None, "CANoe")
    D.R("PWR", "제어기는 SLEEP 중 CAN WUP(ISO 11898-2:2016 Wake-up Pattern) 또는 IG ON 신호로 기동해야 하며, 기동 후 100ms 이내에 CAN 수신이 가능해야 한다.", None, "CANoe")

    D.h("3.2 환경 및 EMC", 2)
    D.p("환경 요구사항은 제어기가 엔진룸 외부(언더바디 근접)에 장착된다는 가정에 기반한다. 장착 위치 변경 시 온도·진동 등급을 재검토한다.")
    D.R("ENV", "제어기는 작동 온도 -40°C ~ 85°C 범위에서 모든 기능을 정상 수행해야 한다.", "장착 위치 등급", "환경 챔버")
    D.R("ENV", "제어기는 보관 온도 -40°C ~ 105°C 범위에서 손상되지 않아야 한다.", None, "환경 챔버")
    D.R("ENV", "제어기는 85°C, 85% RH, 1000시간 고온고습 시험 후 기능을 만족해야 한다.", None, "환경 챔버")
    D.R("ENV", "제어기는 -40°C ↔ 85°C 열충격 1000 사이클 후 기능을 만족해야 한다.", None, "환경 챔버")
    D.R("ENV", "제어기는 ES 95400 랜덤 진동 등급 B(10~2000Hz, 27.8 m/s² RMS, 축당 8시간)를 만족해야 한다.", None, "진동 시험기")
    D.R("ENV", "제어기는 기계적 충격 50g, 11ms, 축당 10회에 대해 손상되지 않아야 한다.", None, "충격 시험기")
    D.R("ENV", "제어기는 ES 95400 방사 방출(RE) 및 전도 방출(CE) 한계를 만족해야 한다.", None, "EMC 시험소")
    D.R("ENV", "제어기는 BCI 100mA, ALSE 100V/m 방사 내성 시험에서 기능 상태 등급 A를 만족해야 한다.", None, "EMC 시험소")
    D.R("ENV", "제어기는 ISO 10605 ESD ±8kV 접촉, ±15kV 기중(비작동 시 ±25kV)에 대해 손상되지 않아야 한다.", None, "EMC 시험소")
    D.R("ENV", "제어기는 염수 분무 96시간 후 커넥터 접촉 저항 증가가 10% 이내여야 한다.", None, "환경 시험")

    D.h("3.3 기구 및 인터페이스", 2)
    D.R("MECH", "제어기 PCB는 액추에이터 하우징 내부 85 x 60 mm 공간에 장착되어야 하며 최대 높이는 18 mm여야 한다.", "기구 패키지", "치수 검사")
    if not B:
        D.R("MECH", "제어기 하우징 조립체는 IP6K9K 방수 등급을 만족해야 한다.", None, "방수 시험")
    D.R("MECH", "차량 커넥터는 12핀 방수 커넥터(KET MG64xxxx 계열)를 사용해야 하며 핀 배열은 표 6을 따라야 한다.", "CRS 5.1", "검사")
    D.R("MECH", "모터 커넥터는 3상 전력 핀 3개와 센서 핀 8개로 구성되어야 한다.", None, "검사")
    D.R("MECH", "제어기 조립체 중량은 PCB 기준 45 g 이하여야 한다.", None, "계측")
    D.R("MECH", "PCB는 4층 FR-4, 1.6 mm, 외층 2oz 동박으로 제작되어야 한다.", "열/전류 설계", "검사")
    D.R("MECH", "MOSFET 및 게이트 드라이버의 접합 온도는 최악 조건(85°C 주변, 8A 연속)에서 125°C 이하여야 한다.", "부품 디레이팅", "열 시뮬레이션 + 열전대 측정")
    D.table("차량 커넥터 핀 배열", [["핀", "신호", "방향", "설명"], ["1", "KL30", "IN", "상시 전원"], ["2", "GND", "-", "접지"], ["3", "KL15", "IN", "IG 신호"], ["4", "CAN_H", "I/O", "차량 CAN"], ["5", "CAN_L", "I/O", "차량 CAN"],
                                    ["6", "WAKE", "IN", "외부 웨이크업(예비)"], ["7", "N.C.", "-", ""], ["8", "N.C.", "-", ""], ["9", "DIAG_K", "I/O", "예비(미사용)"], ["10", "GND_PWR", "-", "전력 접지"], ["11", "KL30_PWR", "IN", "모터 전원"], ["12", "SHIELD", "-", "실드"]], widths=[1.3, 3.5, 2, 8])

    D.h("3.4 액추에이터 성능", 2)
    D.p("성능 요구사항은 밸브 액추에이터의 기구 사양(기어비 1:48, 출력 스트로크 0~90°)을 기준으로 출력축 기준 값으로 정의한다.")
    D.R("MOT", "액추에이터 출력축 스트로크는 0° ~ 90° 범위를 가져야 하며, 기계적 스토퍼는 양 끝단 +3°에 위치해야 한다.", "기구 사양", "치수 검사")
    D.R("MOT", f"액추에이터는 45° 스텝 지령에 대해 {'250' if B else '300'}ms 이내에 목표 위치 ±1° 범위에 도달하고 유지해야 한다 (정격 부하 0.8 N·m, 13.5V, 25°C).", "그림 3, CRS 4.5", "벤치(다이나모)")
    D.R("MOT", "액추에이터는 정상 작동 조건에서 출력축 위치 정확도 ±0.5°를 만족해야 한다.", None, "벤치(각도 측정기)")
    D.R("MOT", "액추에이터는 출력축 기준 최대 토크 2.0 N·m를 1초 동안 발생시킬 수 있어야 한다.", None, "벤치(다이나모)")
    D.R("MOT", "액추에이터는 정격 부하에서 최대 각속도 200°/s로 이동할 수 있어야 한다.", None, "벤치")
    D.R("MOT", "액추에이터는 9V 저전압 조건에서도 45° 이동을 600ms 이내에 완료해야 한다.", None, "벤치")
    D.R("MOT", "액추에이터는 -40°C 저온 조건에서 45° 이동을 800ms 이내에 완료해야 한다.", "그리스 점도", "환경 챔버 + 벤치")
    D.R("MOT", "액추에이터의 작동 소음은 차량 장착 상태에서 1m 거리 기준 45 dB(A) 이하여야 한다.", "CRS 4.7", "무향실")
    D.R("MOT", "액추에이터는 전체 수명 동안 1,000,000 사이클(0°↔90°)의 내구를 만족해야 한다.", None, "내구 시험")
    D.R("MOT", "액추에이터는 전원 차단 상태에서 외력 1.5 N·m 이하에서는 위치를 유지해야 한다 (셀프 로킹).", "기구 웜기어", "벤치")
    D.R("MOT", "홀 센서 또는 절대 각도 센서 중 하나가 고장 나도 나머지 센서로 위치 제어를 계속할 수 있어야 한다 (성능 저하 허용).", "센서 이중화", "고장 주입", "B")

    D.h("3.5 전기 인터페이스 사양", 2)
    D.p("표의 값은 커넥터 핀 기준 전기 사양이다. 모든 입력은 ISO 7637 과도 펄스에 대해 보호되어야 한다.")
    D.table("전기 인터페이스 사양", [["신호", "유형", "전압 범위", "전류/임피던스", "보호", "비고"], ["KL30", "전원 입력", "6~18V (26V 60s)", "최대 8A (15A 500ms)", "역극성, TVS", "로직 전원"], ["KL30_PWR", "전원 입력", "6~18V", "최대 15A", "TVS, 퓨즈 20A", "모터 전원"],
                                     ["KL15", "디지털 입력", "0~18V", "풀다운 10kΩ", "직렬 저항, TVS", "High ≥ 6V, Low ≤ 2V"], ["CAN_H/L", "버스", "ISO 11898-2", "120Ω 미종단", "ESD, CMC", "TJA1043"], ["WAKE", "디지털 입력", "0~18V", "풀다운 10kΩ", "TVS", "예비"],
                                     ["U/V/W", "전력 출력", "0~KL30", "15A 피크", "과전류 비교기 20A", "20kHz PWM"], ["HALL_A/B/C", "디지털 입력", "0~5V", "풀업 4.7kΩ", "직렬 저항", "오픈 컬렉터"], ["ENC 5V", "센서 전원", "5V ±5%", "최대 50mA", "단락 보호", "AS5047"]], widths=[2.2, 2.2, 2.8, 3, 2.8, 2.5])
    D.R("ELEC", "KL15 입력은 6V 이상을 High, 2V 이하를 Low로 판정해야 하며 2~6V 구간은 이전 상태를 유지해야 한다 (히스테리시스).", None, "벤치")
    D.R("ELEC", "KL30 감시 회로는 0~25.5V 범위를 ±0.2V 정확도로 측정할 수 있어야 한다.", "REQ-MODE-008 임계 정확도", "벤치(교정)")
    D.R("ELEC", "상 전류 측정 회로는 ±20A 범위를 ±2% 정확도, 100µs 이내 응답으로 측정할 수 있어야 한다.", "FOC 제어", "벤치(교정)")
    D.R("ELEC", "모터 전원 라인에는 20A 퓨즈 또는 동등한 보호 소자가 장착되어야 한다.", None, "검사")
    D.R("ELEC", "모든 커넥터 입력은 ISO 7637-2 펄스 1~4 및 ISO 7637-3 결합 펄스에 대해 손상되지 않아야 한다.", None, "EMC 시험소")

    D.h("3.6 제조 및 품질", 2)
    D.R("MFG", "제어기는 IPC-A-610 Class 3 기준으로 조립되어야 한다.", None, "검사")
    D.R("MFG", "제어기는 EOL에서 100% 기능 시험(전원, CAN, 모터 구동, 센서, 영점 학습)을 거쳐야 하며 시험 결과는 일련번호와 함께 보관되어야 한다.", "추적성", "EOL 기록")
    D.R("MFG", "제어기 PCB에는 2D 바코드(DMC)로 일련번호가 마킹되어야 하며, SW가 읽을 수 있도록 NvM에도 저장되어야 한다.", None, "검사")
    D.R("MFG", "제어기는 컨포멀 코팅(아크릴계, 25~75µm)이 적용되어야 하며 커넥터 및 테스트 포인트는 마스킹되어야 한다.", "습기/염수", "검사")
    D.R("MFG", "제어기의 현장 불량률 목표는 100 ppm 이하여야 한다.", "품질 목표", "통계")

    D.h("3.7 기능 안전 (시스템 레벨)", 2)
    D.p("HARA 결과 '의도하지 않은 액추에이터 이동'과 '명령 불이행'이 ASIL B로 평가되었다. 시스템 레벨 안전 목표를 만족하기 위한 안전 메커니즘을 아래에 정의한다.")
    D.R("SAFE", "제어기는 의도하지 않은 액추에이터 이동(지령 없이 5° 이상 이동)을 100ms 이내에 검출하고 FAILSAFE 모드로 천이해야 한다.", "SG-01", "고장 주입(HIL)", "B")
    D.R("SAFE", "FAILSAFE 모드에서 제어기는 모든 상단/하단 MOSFET을 차단(프리휠)하고 하드웨어 Shut-off Path(DRV8305 EN_GATE)를 비활성화해야 한다.", "안전 상태 정의", "고장 주입", "B")
    D.R("SAFE", "제어기는 상 전류 20A 이상을 하드웨어 비교기로 검출하여 10µs 이내에 게이트를 차단해야 한다 (SW 개입 없음).", "MOSFET 보호", "벤치(전류 주입)", "B")
    D.R("SAFE", "제어기는 PMIC 안전 와치독(윈도우 와치독, 주기 10ms)을 구현해야 하며, 와치독 실패 시 PMIC가 Shut-off Path를 차단해야 한다.", "TLF35584", "고장 주입", "B")
    D.R("SAFE", "제어기는 두 코어 중 하나에서 1ms 위치 제어 결과를 다른 코어가 10ms 주기로 교차 검증해야 한다 (위치 편차 2° 초과 시 DEGRADED).", "ISO 26262-6", "고장 주입", "B")
    D.R("SAFE", "제어기는 모든 안전 관련 고장을 DTC로 기록하고 FAILSAFE 진입 사유를 NvM 고장 로그에 10건까지 보관해야 한다.", None, "UDS 0x19", "B")
    d.add_page_break()

    # 4 소프트웨어 요구사항 -----------------------------------------------------
    D.h("4 소프트웨어 요구사항")
    D.p("본 장은 AUTOSAR Classic 기반 임베디드 소프트웨어 요구사항을 정의한다. 요구사항은 입력 신호, 조건, 처리/타이밍, 출력의 구조로 기술되어 SWE.1 템플릿으로 바로 변환될 수 있도록 작성한다.")
    D.h("4.1 소프트웨어 아키텍처 제약", 2)
    D.p("소프트웨어는 ASW(SWC), CDD(모터 제어), BSW(AUTOSAR 표준 모듈)로 구성된다. 100µs FOC 전류 루프는 RTE 오버헤드를 피하기 위해 CDD에 구현한다. 그림 5는 태스크 스케줄 구조이다.")
    D.fig("timing", "OS 태스크 및 ISR 스케줄")
    D.R("ARCH", "SW는 AUTOSAR Classic Platform R4.4 BSW(Com, PduR, CanIf, Can, Dcm, Dem, NvM, EcuM, BswM, WdgM, Os)를 사용해야 한다.", "플랫폼 표준", "아키텍처 검토")
    D.R("ARCH", "SW는 100µs 주기 EVADC 인터럽트에서 FOC 전류 제어를 CDD로 수행해야 한다.", "제어 대역폭", "TRACE32 타이밍 측정")
    D.R("ARCH", "SW는 1ms 주기 OS 태스크에서 위치/속도 제어 및 홀 센서 처리를 수행해야 한다.", None, "TRACE32")
    D.R("ARCH", "SW는 10ms 주기 OS 태스크에서 CAN 송수신 처리, 진단, 고장 디바운스를 수행해야 한다.", None, "TRACE32")
    D.R("ARCH", "SW는 100ms 주기 OS 태스크에서 NvM 처리, 온도 감시, 통계 갱신을 수행해야 한다.", None, "TRACE32")
    D.R("ARCH", "각 코어의 CPU 부하는 최악 조건에서 70% 이하여야 하며, 스택 사용량은 할당량의 80% 이하여야 한다.", "자원 목표", "TRACE32 + 스택 측정")
    D.R("ARCH", "SW는 MISRA C:2012 필수(Required) 규칙을 100% 준수해야 하며, 권고(Advisory) 규칙 위반은 문서화된 승인 하에 허용된다.", None, "정적 분석")

    D.h("4.2 위치 제어", 2)
    D.p("위치 제어기는 S-curve 프로파일 생성기, 위치 PI 제어기, 속도 PI 제어기, FOC 전류 제어기의 캐스케이드로 구성된다. 제어 이득은 NvM 캘리브레이션 파라미터로 관리한다.")
    D.R("CTRL", "SW는 CAN 신호 PosCmd_Tgt(0~90°, 분해능 0.1°)를 수신하면 현재 위치에서 목표 위치까지 S-curve 속도 프로파일을 생성해야 한다 (최대 속도 200°/s, 최대 가속도 2000°/s²).", "그림 3", "SIL")
    D.R("CTRL", "SW는 1ms 주기로 위치 PI 제어기를 실행하여 속도 지령을 산출해야 하며, 출력은 ±200°/s로 제한해야 한다.", None, "SIL/HIL")
    D.R("CTRL", "SW는 1ms 주기로 속도 PI 제어기를 실행하여 q축 전류 지령을 산출해야 하며, 출력은 ±8A(피크 모드 ±15A)로 제한해야 한다.", None, "SIL/HIL")
    D.R("CTRL", "SW는 100µs 주기로 FOC(Clarke/Park 변환, d/q 전류 PI, SVPWM)를 수행하여 3상 PWM 듀티를 갱신해야 한다. PWM 주파수는 20kHz여야 한다.", None, "오실로스코프")
    D.R("CTRL", f"SW는 정격 조건에서 45° 스텝 지령에 대해 {'250' if B else '300'}ms 이내에 ±1° 범위에 수렴하도록 제어해야 하며 오버슈트는 2° 이하여야 한다.", "REQ-MOT-002", "HIL(다이나모)")
    D.R("CTRL", "SW는 목표 위치 도달 후 위치 편차가 ±0.3° 이내로 500ms 유지되면 ActPos_Status = REACHED(2)를 송신해야 한다.", None, "CANoe")
    D.R("CTRL", "SW는 이동 중 ActPos_Status = MOVING(1), 정지 대기 중 IDLE(0), 고장 시 FAULT(3)를 송신해야 한다.", None, "CANoe")
    D.R("CTRL", "SW는 목표 위치가 기계적 스토퍼 범위(-3°~93°)를 벗어나면 가장 가까운 유효 값으로 클램핑하고 DTC B1710(지령 범위 초과)을 설정해야 한다.", None, "CANoe + UDS")
    D.R("CTRL", "SW는 출력축 위치를 홀 센서(전기각 60° 분해능, 기어비 보정)와 AS5047 절대 각도(14bit)를 융합하여 0.05° 분해능으로 추정해야 한다.", "센서 융합", "벤치")
    D.R("CTRL", "SW는 홀 센서 위치와 절대 각도 센서 위치의 편차가 3° 이상 200ms 지속되면 센서 불일치 고장으로 판단해야 한다.", "REQ-MOT-011", "고장 주입", "B")
    D.R("CTRL", "SW는 센서 불일치 고장 시 절대 각도 센서를 기준으로 제어를 계속하되 최대 속도를 100°/s로 제한하고 DEGRADED 모드로 천이해야 한다.", None, "고장 주입", "B")
    D.R("CTRL", "SW는 모터 상 전류 15A 이상이 500ms 이상 지속되면 구속(Stall) 상태로 판단하고 FAILSAFE 모드로 천이해야 하며 DTC B1720을 저장해야 한다.", "MOSFET 열 보호", "고장 주입(기계적 구속)", "B")
    D.R("CTRL", "SW는 구속 판단 전 300ms 시점에 토크를 50%로 제한하여 기구 손상을 예방해야 한다.", None, "HIL")
    D.R("CTRL", "SW는 소프트 스톱 기능으로 스토퍼 5° 전부터 감속하여 스토퍼 충돌 속도를 20°/s 이하로 제한해야 한다.", "기구 보호", "벤치")
    D.R("CTRL", "SW는 제어 이득(Kp_pos, Ki_pos, Kp_vel, Ki_vel, Kp_cur, Ki_cur)을 NvM 캘리브레이션 블록에서 읽어야 하며, UDS 0x2E로 쓰기 가능해야 한다.", None, "UDS")
    if B:
        D.R("CTRL", "SW는 MOSFET 온도 125°C 이상(NTC 측정) 검출 시 PWM 출력을 즉시 차단하고 DTC B1730(과온)을 저장해야 한다.", "열 보호 강화", "고장 주입", "B")
        D.R("CTRL", "SW는 MOSFET 온도 110°C 이상에서 전류 제한을 4A로 낮추어 DEGRADED 모드로 운전해야 한다.", None, "HIL")

    D.h("4.3 영점 학습 및 캘리브레이션", 2)
    D.p("출력축 절대 위치는 조립 공차 때문에 EOL(End-of-Line) 및 서비스 시 영점 학습이 필요하다. 영점 학습은 UDS RoutineControl로 기동한다.")
    D.R("CAL", "SW는 UDS 0x31 RoutineControl(routineId 0xF010) 요청 시 영점 학습 루틴을 수행해야 한다. 루틴은 확장 세션 및 보안 접근 레벨 1에서만 허용되어야 한다.", "ISO 14229", "UDS")
    D.R("CAL", "영점 학습 루틴은 하단 스토퍼 방향으로 30°/s로 이동하여 전류 6A 이상 200ms 지속으로 스토퍼 접촉을 검출하고, 그 위치를 -3°로 설정해야 한다.", None, "벤치")
    D.R("CAL", "영점 학습 루틴은 상단 스토퍼도 동일하게 검출하여 두 스토퍼 간 거리가 96° ± 2°인지 검증해야 하며, 범위를 벗어나면 루틴 실패(NRC 0x72)를 응답해야 한다.", None, "벤치")
    D.R("CAL", "SW는 영점 학습 결과(오프셋, 스토퍼 거리, 학습 일시 카운터)를 NvM 블록 NvM_CalibZero에 저장해야 하며, 저장 완료 후 루틴 결과를 응답해야 한다.", None, "UDS + NvM 덤프")
    D.R("CAL", "SW는 영점 학습이 수행되지 않은 상태(NvM 블록 무효)에서는 NORMAL 모드 진입을 금지하고 DTC B1740(영점 미학습)을 설정해야 한다.", None, "HIL")
    D.R("CAL", "SW는 전원 인가 시 절대 각도 센서 값과 저장된 오프셋으로 초기 위치를 계산하여 INIT 모드에서 200ms 이내에 위치 추정을 완료해야 한다.", None, "TRACE32")

    D.h("4.4 운용 모드 및 전원 관리", 2)
    D.R("MODE", "SW는 전원 인가 후 INIT 모드에서 RAM/ROM 테스트, 센서 자체 진단, 게이트 드라이버 자체 진단을 수행하고 200ms 이내에 완료해야 한다.", "그림 2", "TRACE32")
    D.R("MODE", "SW는 INIT 자체 진단이 모두 통과하고 영점 학습이 유효하면 NORMAL 모드로 천이해야 한다.", None, "HIL")
    D.R("MODE", "SW는 경고 수준 고장(센서 불일치, 온도 경고, CAN 신호 품질 저하) 발생 시 DEGRADED 모드로 천이하고 토크를 50%로 제한해야 한다.", None, "고장 주입")
    D.R("MODE", "SW는 DEGRADED 모드에서 고장 조건이 3 주기(30ms) 연속 해소되면 NORMAL 모드로 복귀해야 한다.", None, "고장 주입")
    D.R("MODE", "SW는 치명 고장(구속, 과전류, 와치독, 센서 전체 고장, 의도하지 않은 이동) 발생 시 FAILSAFE 모드로 천이해야 하며, FAILSAFE는 전원 재인가 전까지 유지되어야 한다.", None, "고장 주입", "B")
    D.R("MODE", "SW는 KL15 OFF 후 3초 동안 CAN 수신 메시지가 없으면 NvM 쓰기를 완료한 뒤 SLEEP 모드로 진입해야 한다.", "REQ-PWR-013", "CANoe")
    D.R("MODE", "SW는 SLEEP 진입 전 NvM 쓰기를 최대 500ms 이내에 완료해야 하며, 완료되지 않으면 SLEEP 진입을 최대 2초까지 연장해야 한다.", None, "TRACE32")
    D.R("MODE", "SW는 KL30 전압이 9V 미만으로 300ms 이상 지속되면 저전압 상태로 판단하고 모터 구동을 중지해야 한다. 이때 DTC B1601을 저장해야 한다.", "REQ-PWR-009", "HIL")
    D.R("MODE", "SW는 저전압 상태에서 KL30 전압이 9.5V 이상으로 300ms 이상 회복되면 모터 구동을 재개해야 한다 (히스테리시스 0.5V).", None, "HIL")
    D.R("MODE", "SW는 KL30 전압이 16V 초과 300ms 이상 지속되면 과전압 상태로 판단하고 모터 구동을 중지하며 DTC B1602를 저장해야 한다.", None, "HIL")
    D.R("MODE", "SW는 PMIC 윈도우 와치독을 10ms 주기로 서비스해야 하며, 10ms 태스크의 실행 결과 플래그가 설정된 경우에만 서비스해야 한다.", "REQ-SAFE-004", "고장 주입", "B")

    D.h("4.5 CAN 통신", 2)
    D.p("CAN 통신은 500kbps CAN 2.0B, ACT_GEN3_CAN.dbc[7] 1.4를 따른다. 모든 수신 메시지는 Alive Counter와 CRC(AUTOSAR E2E Profile 1)로 보호된다.")
    D.table("CAN 메시지 정의", [["메시지", "ID", "방향", "주기", "DLC", "주요 신호"], ["ACT_CMD", "0x2A0", "Rx", "10ms", "8", "PosCmd_Tgt, PosCmd_Enable, ACT_CMD_AC, ACT_CMD_CRC"],
                                   ["ACT_STATUS", "0x3A0", "Tx", "10ms", "8", "ActPos_Act, ActPos_Status, ActCur_Act, ACT_STATUS_AC, ACT_STATUS_CRC"],
                                   ["ACT_DIAG", "0x3A1", "Tx", "100ms", "8", "ActTemp_Mosfet, ActVolt_KL30, ActFault_Flags, ActMode"],
                                   ["VCU_STATE", "0x1B0", "Rx", "20ms", "8", "IgnState, VehSpeed, VCU_STATE_AC"], ["NM_ACT", "0x5xx", "Tx/Rx", "이벤트", "8", "AUTOSAR CanNm"]], widths=[2.6, 1.5, 1.4, 1.5, 1, 7])
    D.table("ACT_CMD 신호 정의", [["신호", "비트", "범위", "분해능", "초기값", "설명"], ["PosCmd_Tgt", "0..9", "0~102.3°", "0.1°", "0", "목표 위치"], ["PosCmd_Enable", "10", "0/1", "-", "0", "구동 허용"],
                                   ["PosCmd_SpeedLimit", "11..18", "0~255 °/s", "1°/s", "200", "속도 제한"], ["ACT_CMD_AC", "48..51", "0~15", "-", "0", "Alive Counter"], ["ACT_CMD_CRC", "56..63", "0~255", "-", "-", "E2E CRC8"]], widths=[3.2, 1.4, 2.2, 1.6, 1.4, 5])
    D.R("COM", "SW는 ACT_CMD(0x2A0) 메시지를 10ms 주기로 수신하고 PosCmd_Tgt를 목표 위치로 사용해야 한다.", "DBC 1.4", "CANoe")
    D.R("COM", f"SW는 ACT_CMD 메시지가 {'500' if B else '300'}ms 이상 수신되지 않으면 Timeout으로 판단하고 현재 위치를 유지해야 하며 DTC U0101(VCU 통신 상실)을 저장해야 한다.", "CRS 4.3", "CANoe 고장 주입")
    D.R("COM", "SW는 Timeout 상태에서 ACT_CMD가 3 주기 연속 정상 수신되면 Timeout을 해제하고 정상 제어로 복귀해야 한다.", None, "CANoe")
    D.R("COM", "SW는 ACT_CMD의 Alive Counter가 이전 값 +1(모듈로 16)이 아닌 경우를 오류로 계수하고, 3회 연속 오류 시 해당 메시지를 무효로 처리해야 한다.", "E2E P1", "CANoe 고장 주입")
    D.R("COM", "SW는 ACT_CMD의 CRC8(E2E Profile 1, Data ID 0x2A0) 검증 실패 시 해당 프레임을 폐기하고 오류를 계수해야 한다.", "E2E P1", "CANoe 고장 주입")
    D.R("COM", "SW는 E2E 오류율이 10 프레임 창에서 50%를 초과하면 CAN 신호 품질 저하로 판단하고 DEGRADED 모드로 천이해야 한다.", None, "CANoe 고장 주입")
    D.R("COM", "SW는 ACT_STATUS(0x3A0)를 10ms ± 1ms 주기로 송신해야 하며, 모든 신호를 DBC 정의 스케일로 인코딩해야 한다.", None, "CANoe 타이밍")
    D.R("COM", "SW는 ACT_STATUS 및 ACT_DIAG 송신 메시지에 Alive Counter와 E2E CRC를 부가해야 한다.", None, "CANoe")
    D.R("COM", "SW는 ACT_DIAG(0x3A1)를 100ms 주기로 송신하며 MOSFET 온도(-40~215°C, 1°C), KL30 전압(0~25.5V, 0.1V), 고장 플래그, 운용 모드를 포함해야 한다.", None, "CANoe")
    D.R("COM", "SW는 PosCmd_Enable = 0인 경우 모터를 정지하고 현재 위치를 유지하며 ActPos_Status = IDLE을 송신해야 한다.", None, "CANoe")
    D.R("COM", "SW는 PosCmd_SpeedLimit 값으로 프로파일 최대 속도를 제한해야 하며, 0은 기본값 200°/s로 해석해야 한다.", None, "CANoe")
    D.R("COM", "SW는 VCU_STATE 메시지의 VehSpeed가 5 km/h를 초과하면 영점 학습 루틴 요청을 NRC 0x22(조건 불충족)로 거절해야 한다.", "주행 중 캘리브레이션 금지", "CANoe + UDS")
    D.R("COM", "SW는 Bus-off 발생 시 AUTOSAR CanSM 복구 절차(100ms 후 재시도, 최대 10회)를 수행하고 DTC U0001을 저장해야 한다.", None, "CANoe 고장 주입")
    D.R("COM", "SW는 AUTOSAR CanNm을 지원해야 하며, 네트워크 슬립 표시 후 SLEEP 진입 조건을 만족해야 한다.", None, "CANoe")

    D.h("4.6 진단 (UDS)", 2)
    D.p("진단은 ISO 14229-1[4] 및 ACT_GEN3_Diag.cdd[8]를 따른다. 진단 요청 ID 0x7A0, 응답 ID 0x7A8, 기능 주소 0x7DF를 사용한다.")
    D.table("지원 UDS 서비스", [["서비스", "SID", "세션", "보안", "비고"], ["DiagnosticSessionControl", "0x10", "모두", "-", "기본/확장/프로그래밍"], ["ECUReset", "0x11", "확장", "-", "hardReset, keyOffOnReset"],
                                 ["ReadDTCInformation", "0x19", "모두", "-", "0x01, 0x02, 0x04, 0x06, 0x0A"], ["ReadDataByIdentifier", "0x22", "모두", "-", "표 11"], ["SecurityAccess", "0x27", "확장", "-", "Seed&Key 레벨 1/3"],
                                 ["CommunicationControl", "0x28", "확장", "-", ""], ["WriteDataByIdentifier", "0x2E", "확장", "레벨1", "캘리브레이션 DID"], ["RoutineControl", "0x31", "확장", "레벨1", "영점 학습, 자체 진단"],
                                 ["TesterPresent", "0x3E", "모두", "-", ""], ["ControlDTCSetting", "0x85", "확장", "-", ""]], widths=[5, 1.2, 1.8, 1.6, 5.5])
    D.table("데이터 식별자(DID)", [["DID", "이름", "크기", "접근", "설명"], ["0xF186", "ActiveSession", "1", "R", "현재 세션"], ["0xF187", "SparePartNumber", "10", "R", ""], ["0xF189", "SwVersion", "8", "R", "SW 버전"],
                                   ["0xF190", "VIN", "17", "R/W", "확장 세션, 레벨1"], ["0xF1A0", "CalibZero", "8", "R", "영점 오프셋/스토퍼 거리"], ["0x0100", "ActPos", "2", "R", "현재 위치 0.01°"],
                                   ["0x0101", "MotorCurrent", "2", "R", "상 전류 10mA"], ["0x0102", "MosfetTemp", "1", "R", "°C"], ["0x0103", "KL30Volt", "1", "R", "0.1V"], ["0x0200", "CtrlGains", "24", "R/W", "제어 이득 6 x float"],
                                   ["0x0201", "StallThreshold", "2", "R/W", "구속 전류 임계(10mA)"], ["0x0300", "FaultLog", "80", "R", "FAILSAFE 로그 10건"]], widths=[1.6, 3.2, 1.2, 1.4, 7.5])
    D.R("DIAG", "SW는 표 10의 UDS 서비스를 표기된 세션 및 보안 조건에서 지원해야 하며, 그 외 조건에서는 적절한 NRC(0x7F, 0x33, 0x22)를 응답해야 한다.", "ISO 14229", "진단기(CANoe.DiVa)")
    D.R("DIAG", "SW는 표 11의 모든 DID를 0x22로 읽을 수 있어야 하며, R/W 표기 DID는 확장 세션·보안 레벨 1에서 0x2E로 쓸 수 있어야 한다.", None, "진단기")
    D.R("DIAG", "SW는 DID 0xF190 VIN 쓰기를 확장 세션 및 보안 레벨 1에서만 허용해야 하며, 쓰기 조건은 TBD이다.", None, "진단기")
    D.R("DIAG", "SW는 진단 요청에 대해 P2 = 50ms, P2* = 5000ms 이내에 응답해야 한다.", "ISO 14229 타이밍", "진단기 타이밍")
    D.R("DIAG", "SW는 확장 세션에서 S3 타이머(5000ms) 동안 TesterPresent가 없으면 기본 세션으로 복귀해야 한다.", None, "진단기")
    D.R("DIAG", "SW는 SecurityAccess Seed&Key(레벨 1: 캘리브레이션, 레벨 3: 프로그래밍)를 지원해야 하며, 3회 연속 키 실패 시 10초 지연을 적용해야 한다.", None, "진단기")
    D.R("DIAG", "SW는 표 12의 DTC를 AUTOSAR Dem으로 관리해야 하며, 각 DTC는 디바운스 카운터 기반 확정(Confirmed) 조건을 가져야 한다.", None, "진단기 + 고장 주입")
    D.R("DIAG", "SW는 DTC 확정 시 Freeze Frame(ActPos, MotorCurrent, MosfetTemp, KL30Volt, ActMode, 주행거리 카운터)을 함께 저장해야 한다.", None, "진단기")
    D.R("DIAG", "SW는 0x19 서브펑션 0x01/0x02/0x04/0x06/0x0A를 지원해야 한다.", None, "진단기")
    D.R("DIAG", "SW는 0x14 ClearDiagnosticInformation으로 DTC 및 Freeze Frame을 삭제할 수 있어야 하며, FAILSAFE 고장 로그(DID 0x0300)는 삭제되지 않아야 한다.", "안전 증적", "진단기")
    D.R("DIAG", "SW는 RoutineControl 0xF011(자체 진단)로 센서/게이트 드라이버/전류 센서 자체 진단을 수행하고 결과를 응답해야 한다.", None, "진단기")
    D.R("DIAG", "SW는 프로그래밍 세션 진입 요청 시 VehSpeed = 0, PosCmd_Enable = 0 조건을 확인해야 하며 불충족 시 NRC 0x22를 응답해야 한다.", None, "진단기")
    D.table("DTC 정의", [["DTC", "설명", "검출 조건", "디바운스", "모드 영향"], ["B1601", "KL30 저전압", "< 9.0V", "300ms", "구동 중지"], ["B1602", "KL30 과전압", "> 16.0V", "300ms", "구동 중지"], ["B1710", "위치 지령 범위 초과", "> 93° 또는 < -3°", "즉시", "클램핑"],
                           ["B1720", "모터 구속", "I ≥ 15A", "500ms", "FAILSAFE"], ["B1721", "모터 과전류(HW)", "I ≥ 20A", "10µs", "FAILSAFE"], *([["B1730", "MOSFET 과온", "≥ 125°C", "즉시", "FAILSAFE"]] if B else []),
                           ["B1740", "영점 미학습", "NvM 무효", "즉시", "NORMAL 금지"], ["B1750", "홀 센서 고장", "패턴 오류 3회", "30ms", "DEGRADED"], ["B1751", "절대 각도 센서 고장", "SPI CRC/범위", "30ms", "DEGRADED"],
                           ["B1752", "센서 불일치", "편차 ≥ 3°", "200ms", "DEGRADED"], ["B1760", "의도하지 않은 이동", "≥ 5° 이동(지령 없음)", "100ms", "FAILSAFE"], ["B1770", "게이트 드라이버 고장", "nFAULT", "즉시", "FAILSAFE"],
                           ["U0001", "CAN Bus-off", "Bus-off", "즉시", "-"], ["U0101", "VCU 통신 상실", f"ACT_CMD 미수신", f"{'500' if B else '300'}ms", "위치 유지"], ["U0401", "VCU 데이터 무효", "E2E 오류", "3회", "DEGRADED"]], widths=[1.6, 4, 3.6, 1.8, 2.6])

    D.h("4.7 고장 검출 및 Fail-safe", 2)
    D.R("FDET", "SW는 홀 센서 패턴(3비트)이 유효하지 않은 값(000, 111)을 3회 연속 읽으면 홀 센서 고장(B1750)으로 판단해야 한다.", None, "고장 주입")
    D.R("FDET", "SW는 AS5047 SPI 응답의 패리티 오류 또는 각도 범위 오류가 30ms 동안 지속되면 절대 각도 센서 고장(B1751)으로 판단해야 한다.", None, "고장 주입")
    D.R("FDET", "SW는 두 위치 센서가 모두 고장이면 FAILSAFE 모드로 천이해야 한다.", "REQ-MOT-011", "고장 주입", "B")
    D.R("FDET", "SW는 게이트 드라이버 nFAULT 신호가 활성화되면 즉시 PWM을 차단하고 DTC B1770을 저장해야 하며, 10ms 태스크에서 SPI로 고장 레지스터를 읽어 Freeze Frame에 기록해야 한다.", None, "고장 주입")
    D.R("FDET", "SW는 PosCmd_Enable = 0 또는 목표 위치 도달 상태에서 위치가 5° 이상 변하면 100ms 이내에 의도하지 않은 이동(B1760)으로 판단하고 FAILSAFE로 천이해야 한다.", "REQ-SAFE-001", "고장 주입", "B")
    D.R("FDET", "SW는 상 전류 센서 오프셋을 INIT 모드에서 보정해야 하며, 오프셋이 ±0.5A를 벗어나면 전류 센서 고장으로 판단해야 한다.", None, "벤치")
    D.R("FDET", "SW는 MOSFET NTC 온도가 100°C 이상이면 ACT_DIAG에 온도 경고 플래그를 설정하고 DEGRADED 모드로 천이해야 한다.", None, "HIL")
    D.R("FDET", "SW는 모든 고장 검출에 Dem 디바운스(카운터 기반, 증분 +1/감분 -1, 임계 표 12)를 적용해야 하며 디바운스 전 사전 고장(Pending)을 관리해야 한다.", None, "고장 주입")
    D.R("FDET", "SW는 FAILSAFE 진입 시 진입 사유, 시각 카운터, Freeze Frame을 NvM 고장 로그(순환 10건)에 기록해야 한다.", "REQ-SAFE-006", "UDS 0x22 0x0300", "B")
    D.R("FDET", "SW는 코어 간 교차 검증(1ms 위치 제어 결과 vs 10ms 독립 추정)에서 2° 초과 편차가 3회 연속이면 DEGRADED, 10회 연속이면 FAILSAFE로 천이해야 한다.", "REQ-SAFE-005", "고장 주입", "B")

    D.h("4.8 비휘발성 메모리", 2)
    D.R("NVM", "SW는 AUTOSAR NvM을 사용하여 캘리브레이션(영점, 제어 이득, 구속 임계), DTC/Freeze Frame, 고장 로그, 통계(사이클 카운터, 최대 온도)를 데이터 플래시에 저장해야 한다.", None, "NvM 덤프")
    D.R("NVM", "SW는 모든 NvM 블록에 CRC16을 적용하고, 캘리브레이션 블록은 이중화(Redundant)로 저장해야 한다.", None, "NvM 덤프 + 손상 주입")
    D.R("NVM", "SW는 NvM 블록이 무효하면 ROM 기본값을 사용하고 DTC B1740 또는 해당 블록 무효 DTC를 설정해야 한다.", None, "손상 주입")
    D.R("NVM", "SW는 통계 블록을 100ms 태스크에서 RAM에 갱신하고 SLEEP 진입 시 또는 1시간마다 플래시에 기록해야 한다 (쓰기 수명 보호).", "플래시 내구", "NvM 덤프")
    D.R("NVM", "SW는 데이터 플래시 쓰기 횟수가 사양의 80%에 도달하면 ACT_DIAG에 경고 플래그를 설정해야 한다.", None, "SIL")

    D.h("4.9 SW 업데이트", 2)
    D.R("UPD", "SW는 UDS 프로그래밍 세션에서 OEM 표준 플래시 부트로더 시퀀스(0x27 레벨 3, 0x34/0x36/0x37, 0x31 체크섬)로 애플리케이션을 재프로그래밍할 수 있어야 한다.", "OEM 리프로그래밍 규격", "진단기")
    D.R("UPD", "부트로더는 애플리케이션 CRC32가 유효하지 않으면 애플리케이션을 실행하지 않고 프로그래밍 세션에 머물러야 한다.", None, "손상 주입")
    D.R("UPD", "애플리케이션 재프로그래밍 중 전원이 차단되어도 부트로더는 손상되지 않아야 하며, 재기동 시 프로그래밍을 재개할 수 있어야 한다.", None, "전원 차단 시험")
    D.h("4.10 타이밍 및 성능", 2)
    D.p("본 절은 소프트웨어 관점의 엔드-투-엔드 타이밍 요구사항을 정의한다. 타이밍은 TRACE32 트레이스 또는 CANoe 타임스탬프로 측정한다.")
    D.R("TIME", "SW는 ACT_CMD 수신(CAN 프레임 종료 시점)부터 PWM 듀티 반영까지의 지연이 2ms 이하여야 한다.", "제어 지연 예산", "CANoe + 오실로스코프")
    D.R("TIME", "SW는 위치 센서 샘플링부터 ACT_STATUS 송신까지의 지연이 12ms 이하여야 한다.", None, "TRACE32 + CANoe")
    D.R("TIME", "100µs ISR의 최악 실행 시간(WCET)은 60µs 이하여야 한다.", "CPU 예산", "TRACE32")
    D.R("TIME", "1ms 태스크의 WCET는 400µs 이하, 10ms 태스크의 WCET는 3ms 이하여야 한다.", None, "TRACE32")
    D.R("TIME", "SW는 OS 태스크 데드라인 초과를 WdgM 논리 감시로 검출해야 하며 3회 연속 초과 시 FAILSAFE로 천이해야 한다.", "REQ-SAFE-004", "고장 주입", "B")
    D.R("TIME", "SW는 전원 인가부터 CAN 첫 송신까지 200ms 이내, SLEEP 웨이크업부터 CAN 수신 가능까지 100ms 이내여야 한다.", "REQ-PWR-012/014", "CANoe")

    D.h("4.11 통계 및 모니터링", 2)
    D.R("STAT", "SW는 누적 이동 사이클 수(0°↔90° 왕복), 누적 작동 시간, 최대 MOSFET 온도, 최대 상 전류를 통계로 기록해야 한다.", "내구 모니터링", "UDS 0x22")
    D.R("STAT", "SW는 통계를 DID 0x0400(누적 사이클), 0x0401(작동 시간), 0x0402(최대 온도), 0x0403(최대 전류)로 읽을 수 있어야 한다.", None, "진단기")
    D.R("STAT", "SW는 누적 사이클 수가 900,000을 초과하면 ACT_DIAG에 수명 경고 플래그를 설정해야 한다.", "REQ-MOT-009 90%", "SIL")
    D.R("STAT", "SW는 FAILSAFE 진입 횟수와 Bus-off 발생 횟수를 카운터로 유지해야 하며, 카운터는 0x14로 삭제되지 않아야 한다.", None, "진단기")

    D.h("4.12 보안", 2)
    D.p("보안 요구사항은 OEM 사이버보안 규격의 '저위험 액추에이터' 등급을 따른다. SecOC는 본 세대에서 적용하지 않으며, 재프로그래밍 보호와 진단 접근 통제에 한정한다.")
    D.R("SEC", "SW는 프로그래밍 세션 진입 및 플래시 쓰기를 SecurityAccess 레벨 3(OEM 키 서버 기반 Seed&Key)로 보호해야 한다.", "OEM 보안 규격", "진단기")
    D.R("SEC", "부트로더는 다운로드된 애플리케이션의 서명(ECDSA P-256)을 검증해야 하며 검증 실패 시 애플리케이션을 활성화하지 않아야 한다.", None, "서명 변조 시험")
    D.R("SEC", "SW는 보안 레벨 1 키 실패 횟수를 NvM에 저장해야 하며, 전원 재인가로 지연 시간이 초기화되지 않아야 한다.", None, "진단기")
    D.R("SEC", "SW는 디버그 인터페이스(DAP)를 양산 모드에서 잠가야 하며, 개발 모드 해제는 OEM 승인 키로만 가능해야 한다.", None, "검사")
    D.R("SEC", "SW는 캘리브레이션 DID 쓰기(0x2E) 이력을 최근 20건까지 기록해야 한다 (DID, 시각 카운터, 세션).", None, "진단기")

    D.h("4.13 제조 및 EOL", 2)
    D.R("EOL", "SW는 EOL 모드(RoutineControl 0xF0F0, 보안 레벨 1)에서 홀 센서 극성, 모터 상 순서, 전류 센서 오프셋을 자동 판별하고 NvM에 저장해야 한다.", "라인 자동화", "EOL 장비")
    D.R("EOL", "SW는 EOL 모드에서 영점 학습을 포함한 전체 자체 진단을 30초 이내에 완료하고 결과를 DID 0x0500으로 제공해야 한다.", None, "EOL 장비")
    D.R("EOL", "SW는 EOL 완료 플래그가 설정되지 않은 제어기에서는 NORMAL 모드 진입을 금지해야 한다.", None, "HIL")
    D.R("EOL", "SW는 제조 일련번호(DID 0xF18C)와 HW 버전(DID 0xF191)을 EOL에서 1회만 쓸 수 있어야 한다 (OTP 동작).", None, "진단기")
    d.add_page_break()

    # 5 HSI ----------------------------------------------------------------
    D.h("5 HW-SW 인터페이스 (HSI)")
    D.p("본 장은 TC364 핀맵과 주변장치 할당을 정의한다. 표 13의 각 행은 SYS.3 HSI 아이템으로 관리되며 SWE.1 요구사항이 참조한다.")
    rows = [["Signal", "Pin", "Port", "Peripheral", "Dir", "Electrical", "비고"],
            ["PWM_U_HS", "45", "P02.0", "GTM TOM0 CH0", "OUT", "3.3V, 20kHz", "3상 PWM 상단"], ["PWM_U_LS", "46", "P02.1", None, "OUT", "3.3V, 20kHz", "3상 PWM 하단"],
            ["PWM_V_HS", "47", "P02.2", None, "OUT", "3.3V, 20kHz", ""], ["PWM_V_LS", "48", "P02.3", None, "OUT", "3.3V, 20kHz", ""], ["PWM_W_HS", "49", "P02.4", None, "OUT", "3.3V, 20kHz", ""], ["PWM_W_LS", "50", "P02.5", None, "OUT", "3.3V, 20kHz", ""],
            ["I_SHUNT_U", "88", "AN0", "EVADC G0 CH0", "IN", "0~3.3V, 100µs 동기", "상 전류 U"], ["I_SHUNT_V", "89", "AN1", None, "IN", "0~3.3V", "상 전류 V"], ["I_SHUNT_W", "90", "AN2", None, "IN", "0~3.3V", "상 전류 W"],
            ["V_KL30_SENSE", "91", "AN3", "EVADC G1 CH3", "IN", "0~3.3V (1:10)", "KL30 감시"], ["T_MOSFET_NTC", "92", "AN4", "EVADC G1 CH4", "IN", "0~3.3V", "MOSFET 온도"], ["T_MOTOR_NTC", "93", "AN5", "EVADC G1 CH5", "IN", "0~3.3V", "모터 온도(예비)"],
            ["HALL_A", "60", "P10.0", "GPIO/ERU", "IN", "5V 풀업", "홀 A"], ["HALL_B", "61", "P10.1", "GPIO/ERU", "IN", "5V 풀업", "홀 B"], ["HALL_C", "62", "P10.2", "GPIO/ERU", "IN", "5V 풀업", "홀 C"],
            ["ENC_SPI_CLK", "70", "P13.0", "QSPI2 SCLK", "OUT", "3.3V, 5MHz", "AS5047"], ["ENC_SPI_MOSI", "71", "P13.1", "QSPI2 MTSR", "OUT", "3.3V", ""], ["ENC_SPI_MISO", "72", "P13.2", "QSPI2 MRST", "IN", "3.3V", ""], ["ENC_SPI_CS", "73", "P13.3", "QSPI2 SLSO0", "OUT", "3.3V", ""],
            ["DRV_SPI_CS", "74", "P13.4", "QSPI2 SLSO1", "OUT", "3.3V", "DRV8305 설정/고장 읽기"], ["DRV_EN_GATE", "75", "P13.5", "GPIO", "OUT", "3.3V", "Shut-off Path"], ["DRV_nFAULT", "76", "P13.6", "ERU", "IN", "3.3V", "게이트 드라이버 고장"],
            ["CAN_TX", "12", "P20.8", "MCMCAN0 TXD0", "OUT", "3.3V, 500kbps", ""], ["CAN_RX", "13", "P20.7", "MCMCAN0 RXD0", "IN", "3.3V", ""], ["CAN_STB", "14", "P20.6", "GPIO", "OUT", "3.3V", "TJA1043 STB"], ["CAN_WAKE", "15", "P20.5", "ERU", "IN", "3.3V", "WUP 검출"],
            ["KL15_SENSE", "20", "P33.0", "GPIO", "IN", "12V→3.3V", "IG 신호"], ["PMIC_WDI", "30", "P33.4", "GPIO", "OUT", "3.3V", "윈도우 와치독"], ["PMIC_SPI_CS", "31", "P33.5", "QSPI0 SLSO2", "OUT", "3.3V", "TLF35584"]]
    t = D.table("TC364 핀맵 및 주변장치 할당", rows, widths=[2.6, 1, 1.4, 2.6, 1, 2.8, 3.2], merges=[(1, 3, 6, 3), (7, 3, 9, 3)])
    D.R("HSI", "SW는 3상 PWM 6채널을 GTM TOM0 CH0~CH5로 생성해야 하며, 상단/하단 데드타임은 500ns여야 한다.", "DRV8305 사양", "오실로스코프")
    D.R("HSI", "SW는 EVADC G0 CH0~CH2 상 전류 샘플링을 PWM 중심(하단 MOSFET ON 구간)에 GTM 트리거로 동기화해야 한다.", "션트 전류 측정", "오실로스코프")
    D.R("HSI", "SW는 KL30 감시 ADC(AN3)를 1ms 주기로 샘플링하고 8샘플 이동 평균으로 필터링해야 한다.", None, "HIL")
    D.R("HSI", "SW는 홀 센서 3 입력을 ERU 양 에지 인터럽트로 처리해야 하며 채터링 제거를 위해 50µs 이내 재발생 에지는 무시해야 한다.", None, "오실로스코프")
    D.R("HSI", "SW는 AS5047과 DRV8305를 QSPI2 모드 1, 5MHz로 통신해야 한다.", None, "오실로스코프")
    D.R("HSI", "SW는 DRV_EN_GATE를 FAILSAFE 진입 시 Low로 구동해야 하며, INIT 모드 자체 진단에서 EN_GATE Low 상태에서 PWM 출력이 모터에 전달되지 않음을 확인해야 한다.", "Shut-off Path", "고장 주입", "B")
    D.R("HSI", "SW는 DRV_nFAULT 하강 에지를 ERU 인터럽트로 받아 10µs 이내에 PWM을 차단해야 한다.", None, "오실로스코프", "B")
    d.add_page_break()

    # 6 검증 ---------------------------------------------------------------
    D.h("6 검증 기준 요약")
    D.p("각 요구사항의 검증 방법은 요구사항 하단에 표기하였다. 다음 표는 검증 환경별 요구사항 분류 기준이다.")
    D.table("검증 환경", [["환경", "대상", "ASPICE 프로세스"], ["단위 시험 (GoogleTest/VectorCAST)", "SWE.3 유닛, MISRA, 커버리지(MC/DC)", "SWE.4"], ["SIL/통합 시험 (TRACE32, RTE 스텁)", "SWE.2 인터페이스, 태스크 타이밍, CPU 부하", "SWE.5"],
                           ["HIL/CANoe (고장 주입, DiVa)", "SWE.1 기능, CAN/UDS, 디바운스, 경계값", "SWE.6"], ["벤치/오실로스코프/HIL", "HSI 신호, 전원 시퀀스, PWM 파형", "SYS.4"], ["다이나모/환경 챔버/EMC/차량", "성능, 환경, EMC, 소음, 내구", "SYS.5"]], widths=[5.5, 7, 2.5])
    D.h("6.1 경계값 시험 원칙", 2)
    D.p("시간·전압·전류 임계값을 포함하는 모든 요구사항은 임계값 양측(예: 490ms / 500ms, 8.9V / 9.0V)에서 동작 차이가 확인되어야 한다. 범위 요구사항은 범위 밖 2점과 범위 끝 2점의 4점 BVA로 검증한다.")
    D.h("6.2 고장 주입 시험 원칙", 2)
    D.p("ASIL B 요구사항은 센서 단선/단락, CAN 타임아웃/CRC 오류, 과전류, 와치독 정지 등 대표 고장을 주입하여 안전 상태 진입 시간과 DTC 발생을 확인한다.")
    D.h("7 부록 A. 요구사항 변경 요청 절차", 1)
    D.p("요구사항 변경은 CR(Change Request)을 통해서만 가능하며, 변경 시 ALM 도구에서 영향 받는 하위 산출물(SWE.1, SWE.2, TC)이 Suspect로 표시된다. 변경 승인 전에는 Suspect 해제가 금지된다.")
    D.bullets(["CR 발행 → 영향 분석(추적 링크 기준) → CCB 승인 → 요구사항 개정 → 하위 산출물 갱신 → Suspect 해제 → 베이스라인", "긴급 변경은 사후 CCB 승인으로 처리할 수 있으나 48시간 이내에 CR을 발행해야 한다."])

    D.h("8 부록 B. ASIL 할당 요약", 1)
    D.p("HARA(별도 문서 HARA-ACT-GEN3)에서 도출된 안전 목표와 본 문서 요구사항의 할당은 다음과 같다. ASIL B 요구사항은 ISO 26262-6 요구사항에 따라 SWE.4 단위 시험에서 MC/DC 커버리지, SWE.6에서 고장 주입 시험을 받아야 한다.")
    D.table("안전 목표 및 요구사항 할당", [["안전 목표", "ASIL", "안전 상태", "관련 요구사항"], ["SG-01 의도하지 않은 액추에이터 이동 방지", "B", "프리휠 + 셀프 로킹 (위치 유지)", "REQ-SAFE-001/002, REQ-FDET-005, REQ-MOT-010"],
                                            ["SG-02 과전류에 의한 화재 방지", "B", "게이트 차단", "REQ-SAFE-003, REQ-CTRL-012, REQ-HSI-006/007"], ["SG-03 제어 불능 상태의 검출 및 통보", "B", "FAILSAFE + 상태 송신", "REQ-SAFE-004/005/006, REQ-TIME-005, REQ-FDET-010"],
                                            ["SG-04 센서 고장 시 안전한 성능 저하", "B", "DEGRADED (속도 제한)", "REQ-MOT-011, REQ-CTRL-010/011, REQ-FDET-001~003"]], widths=[5.5, 1.2, 4, 5])
    D.p("ASIL 분해(Decomposition)는 적용하지 않는다. 모든 ASIL B 요구사항은 QM 요구사항과 간섭 없음(Freedom from Interference)을 보장해야 하며, 메모리 보호(MPU) 및 타이밍 보호(WdgM)를 통해 달성한다.", italic=True)

    p = OUT / f"SRS_BLDC_Full_rev{rev}.docx"
    d.save(p)
    return p


if __name__ == "__main__":
    for r in ("A", "B"):
        print(build(r))
