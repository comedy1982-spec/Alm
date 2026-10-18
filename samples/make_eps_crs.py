"""Generate a ~50 page customer requirements specification (CRS) for a column-type EPS ECU.

  python samples/make_eps_crs.py   ->  samples/CRS_EPS_ECU_rev1.0.docx  (+ .pdf when LibreOffice exists)

The document is written the way an OEM hands a CRS to a supplier: revision history, system context,
use cases, functional / sensor / communication / diagnostic / safety / security / electrical /
environmental / performance / production requirements with native IDs (REQ-<DOM>-NNN), ASIL and
verification method lines, requirement tables, signal / DTC / pin tables and engineering figures.
Import it into ECU-ALM as SYS.1 (mode "crs") and deploy SYS.1 → SYS.2 → SWE.1 / HWE.1 ...

All company names and in-house standard numbers are fictional (ACME Motors, AMS-xxxx).
"""
from __future__ import annotations

import shutil
import subprocess
from io import BytesIO
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from docx import Document
from docx.enum.section import WD_ORIENT  # noqa: F401  (kept for landscape experiments)
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from matplotlib.patches import FancyBboxPatch

plt.rcParams["font.family"] = ["Noto Sans CJK KR", "Noto Sans CJK JP", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
OUT = Path(__file__).parent
DOC_NO = "CRS-EPS-C3-001"
INK, BLUE, GREEN, ORANGE, RED, GRAY = "#1E2A38", "#2a78d6", "#1baf7a", "#eb6834", "#e34948", "#7A8592"


# ============================================================================ figures
def _png(fig) -> bytes:
    b = BytesIO(); fig.savefig(b, format="png", bbox_inches="tight", dpi=150); plt.close(fig); return b.getvalue()


def _box(ax, x, y, w, h, t, fc="#EEF3FC", ec=BLUE, fs=8.5, bold=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.012", fc=fc, ec=ec, lw=1.3))
    ax.text(x + w / 2, y + h / 2, t, ha="center", va="center", fontsize=fs, weight="bold" if bold else "normal", color=INK)


def _arrow(ax, a, b, label="", color=INK, two=False, lfs=7):
    ax.annotate("", xy=b, xytext=a, arrowprops=dict(arrowstyle="<->" if two else "->", color=color, lw=1.2))
    if label:
        ax.text((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 + 0.025, label, ha="center", fontsize=lfs, color=color)


def fig_context():
    fig, ax = plt.subplots(figsize=(7.6, 3.8)); ax.axis("off"); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    _box(ax, 0.38, 0.38, 0.24, 0.26, "EPS ECU\n(본 문서 대상)", fc="#E3F4E7", ec=GREEN, fs=10, bold=True)
    for (x, y, t) in [(0.02, 0.78, "ESC / 차속"), (0.02, 0.50, "BCM / 게이트웨이"), (0.02, 0.22, "ADAS 제어기\n(LKA/LFA/PA)"),
                      (0.80, 0.78, "토크·각도 센서\n(TAS, 이중 채널)"), (0.80, 0.50, "BLDC 모터\n+ 위치 센서"), (0.80, 0.22, "클러스터 / 경고등"),
                      (0.40, 0.04, "배터리 KL30 / IG KL15"), (0.40, 0.84, "진단기 (UDS on CAN-FD)")]:
        _box(ax, x, y, 0.18, 0.13, t)
    for (a, b, l) in [((0.20, 0.84), (0.38, 0.58), "CAN-FD"), ((0.20, 0.56), (0.38, 0.52), "CAN-FD"), ((0.20, 0.28), (0.38, 0.44), "CAN-FD (ADAS)")]:
        _arrow(ax, a, b, l, BLUE, two=True)
    _arrow(ax, (0.80, 0.84), (0.62, 0.58), "SENT x2", GREEN)
    _arrow(ax, (0.62, 0.50), (0.80, 0.56), "3상 U/V/W", ORANGE)
    _arrow(ax, (0.80, 0.53), (0.62, 0.46), "위치 SPI", GREEN)
    _arrow(ax, (0.62, 0.42), (0.80, 0.30), "상태 신호", BLUE)
    _arrow(ax, (0.50, 0.17), (0.50, 0.38), "12V", ORANGE)
    _arrow(ax, (0.50, 0.84), (0.50, 0.64), "UDS", BLUE, two=True)
    return _png(fig)


def fig_block():
    fig, ax = plt.subplots(figsize=(7.6, 3.6)); ax.axis("off"); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    blocks = {"pmic": (0.02, 0.62, "PMIC\n(5V/3.3V, WDG)"), "can": (0.02, 0.22, "CAN-FD XCVR x2"), "mcu": (0.30, 0.40, "Dual-core Lockstep MCU\n(ASIL D)"),
              "gd": (0.58, 0.62, "3상 게이트 드라이버"), "inv": (0.80, 0.62, "MOSFET 인버터\n+ 상 차단 릴레이"), "mot": (0.80, 0.22, "BLDC 모터\n(80A 피크)"),
              "tas": (0.58, 0.22, "TAS 인터페이스\n(SENT x2)"), "cs": (0.58, 0.02, "상전류 션트 x3\n+ CSA")}
    for k, (x, y, t) in blocks.items():
        _box(ax, x, y, 0.19 if k != "mcu" else 0.22, 0.22, t, fc="#FFF3DC" if k in ("mcu",) else "#EEF3FC", ec=ORANGE if k == "mcu" else BLUE)
    _arrow(ax, (0.21, 0.73), (0.30, 0.56), "VDD", ORANGE); _arrow(ax, (0.21, 0.33), (0.30, 0.46), "CAN", BLUE, two=True)
    _arrow(ax, (0.52, 0.56), (0.58, 0.70), "PWM x6", ORANGE); _arrow(ax, (0.77, 0.73), (0.80, 0.73)); _arrow(ax, (0.895, 0.62), (0.895, 0.44), "U/V/W", ORANGE)
    _arrow(ax, (0.58, 0.32), (0.52, 0.46), "SENT", GREEN); _arrow(ax, (0.58, 0.12), (0.52, 0.42), "ADC", GREEN); _arrow(ax, (0.80, 0.30), (0.77, 0.30), "위치", GREEN)
    return _png(fig)


def fig_assist_map():
    tq = np.linspace(0, 8, 200)
    fig, ax = plt.subplots(figsize=(7.0, 3.6))
    for v, gain, col in [(0, 1.0, BLUE), (30, 0.72, ORANGE), (80, 0.45, GREEN), (150, 0.28, "#6250d6")]:
        assist = np.clip(gain * 4.2 * np.maximum(0, tq - 0.4) ** 1.35, 0, 4.2 * gain * 12) / 1.0
        assist = np.minimum(assist, 75 * (0.25 + 0.75 * gain))
        ax.plot(tq, assist, lw=2, color=col, label=f"차속 {v} km/h")
        ax.text(tq[-1] + 0.08, assist[-1], f"{v} km/h", fontsize=7.5, va="center", color=INK)
    ax.axvline(0.4, color=GRAY, ls="--", lw=1); ax.text(0.45, 70, "불감대 0.4 N·m", fontsize=7.5, color=INK)
    ax.set_xlabel("운전자 조향 토크 (N·m)"); ax.set_ylabel("모터 보조 토크 (랙 환산 %)"); ax.set_xlim(0, 9); ax.set_ylim(0, 80)
    ax.grid(alpha=0.25); ax.legend(fontsize=7.5, loc="upper left")
    return _png(fig)


def fig_states():
    fig, ax = plt.subplots(figsize=(7.6, 3.6)); ax.axis("off"); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    st = {"OFF/SLEEP": (0.02, 0.42), "INIT": (0.22, 0.42), "READY": (0.42, 0.42), "ASSIST": (0.62, 0.70), "LIMITED\n(Derating)": (0.62, 0.14),
          "SAFE STATE": (0.84, 0.42)}
    col = {"OFF/SLEEP": "#EEF1F5", "INIT": "#EEF3FC", "READY": "#EEF3FC", "ASSIST": "#E3F4E7", "LIMITED\n(Derating)": "#FFF3DC", "SAFE STATE": "#FCEEED"}
    for n, (x, y) in st.items():
        _box(ax, x, y, 0.15, 0.16, n, fc=col[n], ec=INK, fs=8, bold=True)
    def ar(a, b, l, dy=0.0):
        (x0, y0), (x1, y1) = st[a], st[b]
        _arrow(ax, (x0 + 0.15, y0 + 0.08 + dy), (x1, y1 + 0.08 + dy), l, INK, lfs=6.5)
    ar("OFF/SLEEP", "INIT", "KL15 ON / WUP"); ar("INIT", "READY", "자기진단 OK (≤300ms)")
    _arrow(ax, (0.57, 0.56), (0.62, 0.74), "엔진 ON\n차속 유효", INK, lfs=6.5)
    _arrow(ax, (0.695, 0.70), (0.695, 0.30), "과열·저전압", ORANGE, lfs=6.5)
    _arrow(ax, (0.725, 0.30), (0.725, 0.70), "복귀", GREEN, lfs=6.5)
    _arrow(ax, (0.77, 0.76), (0.84, 0.54), "치명 고장", RED, lfs=6.5)
    _arrow(ax, (0.77, 0.22), (0.84, 0.46), "치명 고장", RED, lfs=6.5)
    ax.text(0.5, 0.02, "SAFE STATE: 보조 토크 램프다운(≤1s, 유지 가능 시) 또는 즉시 상 차단 · 경고등 점등 · DTC 저장", ha="center", fontsize=7.5, color=INK)
    return _png(fig)


def fig_thermal():
    t = np.linspace(60, 160, 200)
    lim = np.where(t < 110, 100, np.where(t < 150, 100 - (t - 110) * 1.5, 40))
    fig, ax = plt.subplots(figsize=(7.0, 3.0))
    ax.plot(t, lim, lw=2.2, color=BLUE)
    ax.axvline(110, color=GRAY, ls="--", lw=1); ax.axvline(150, color=GRAY, ls="--", lw=1)
    ax.text(111, 102, "디레이팅 시작 110°C", fontsize=7.5); ax.text(151, 44, "하한 40% @150°C", fontsize=7.5)
    ax.set_xlabel("파워 스테이지 추정 온도 (°C)"); ax.set_ylabel("허용 모터 전류 (%)"); ax.set_ylim(0, 115); ax.grid(alpha=0.25)
    return _png(fig)


def fig_lowvolt():
    v = np.linspace(6, 18, 300)
    lim = np.clip((v - 7.0) / (10.0 - 7.0), 0, 1) * 100
    lim = np.where(v > 16.5, np.clip(100 - (v - 16.5) / 1.5 * 100, 0, 100), lim)
    fig, ax = plt.subplots(figsize=(7.0, 3.0))
    ax.plot(v, lim, lw=2.2, color=ORANGE)
    for x, l in [(7.0, "7V: 보조 0%"), (10.0, "10V: 100%"), (16.5, "16.5V"), (18.0, "18V: 0%")]:
        ax.axvline(x, color=GRAY, ls="--", lw=1); ax.text(x + 0.1, 108, l, fontsize=7)
    ax.set_xlabel("KL30 전압 (V)"); ax.set_ylabel("허용 보조 토크 (%)"); ax.set_ylim(0, 118); ax.grid(alpha=0.25)
    return _png(fig)


def fig_tas():
    t = np.linspace(0, 120, 600)
    a = 2.0 * np.sin(t / 12)
    b = -a + 0.03 * np.random.default_rng(3).standard_normal(len(t))
    b[t > 70] = -a[t > 70] + 0.9
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(7.0, 3.6), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
    ax.plot(t, a, color=BLUE, lw=1.8, label="채널 1 (T1)"); ax.plot(t, -b, color=ORANGE, lw=1.4, ls="--", label="채널 2 반전 (−T2)")
    ax.axvline(70, color=RED, lw=1, ls=":"); ax.text(71, 1.8, "드리프트 발생", fontsize=7.5)
    ax.set_ylabel("토크 (N·m)"); ax.legend(fontsize=7, loc="lower left"); ax.grid(alpha=0.25)
    diff = np.abs(a + b); ax2.plot(t, diff, color=INK, lw=1.4); ax2.axhline(0.5, color=RED, ls="--", lw=1); ax2.text(2, 0.6, "임계 0.5 N·m", fontsize=7)
    ax2.set_ylabel("|T1+T2|"); ax2.set_xlabel("시간 (ms)"); ax2.grid(alpha=0.25)
    return _png(fig)


def fig_ftti():
    fig, ax = plt.subplots(figsize=(7.4, 2.6)); ax.set_xlim(-5, 60); ax.set_ylim(0, 4); ax.set_yticks([])
    lanes = [("고장 발생", [(0, 60)], RED), ("고장 검출 (FDTI ≤ 10ms)", [(8, 60)], ORANGE), ("고장 반응 (FRTI ≤ 10ms)", [(18, 60)], BLUE), ("안전 상태", [(18, 60)], GREEN)]
    for i, (n, segs, c) in enumerate(lanes):
        y = 3.3 - i * 0.85
        for s, e in segs:
            ax.add_patch(plt.Rectangle((s, y - 0.18), e - s, 0.36, color=c, alpha=0.35))
        ax.text(-4.5, y, n, va="center", fontsize=7.5)
    ax.annotate("", xy=(20, 0.25), xytext=(0, 0.25), arrowprops=dict(arrowstyle="<->", color=INK)); ax.text(10, 0.35, "FTTI 20ms (SG-01)", ha="center", fontsize=8)
    ax.set_xlabel("시간 (ms)"); ax.grid(alpha=0.2, axis="x")
    return _png(fig)


def fig_network():
    fig, ax = plt.subplots(figsize=(7.4, 2.8)); ax.axis("off"); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.plot([0.04, 0.96], [0.62, 0.62], color=BLUE, lw=3); ax.text(0.04, 0.68, "Chassis CAN-FD (500k / 2M)", fontsize=8, color=BLUE)
    ax.plot([0.04, 0.96], [0.22, 0.22], color=GREEN, lw=3); ax.text(0.04, 0.28, "ADAS Private CAN-FD (500k / 2M)", fontsize=8, color=GREEN)
    for x, t, both in [(0.10, "ESC", False), (0.28, "GW", False), (0.46, "EPS ECU", True), (0.64, "SAS*", False), (0.82, "ADAS DCU", True)]:
        _box(ax, x - 0.07, 0.40, 0.14, 0.12, t, fc="#E3F4E7" if t == "EPS ECU" else "#EEF3FC")
        ax.plot([x, x], [0.52, 0.62], color=BLUE, lw=1.5)
        if both:
            ax.plot([x, x], [0.22, 0.40], color=GREEN, lw=1.5)
    ax.text(0.5, 0.04, "* SAS(조향각 센서) 신호는 EPS 내부 산출값으로 대체 가능 (REQ-SENS-011)", ha="center", fontsize=7.5)
    return _png(fig)


def fig_step():
    t = np.linspace(0, 0.3, 400)
    wn, z = 55, 0.62
    y = 1 - np.exp(-z * wn * t) * (np.cos(wn * np.sqrt(1 - z * z) * t) + z / np.sqrt(1 - z * z) * np.sin(wn * np.sqrt(1 - z * z) * t))
    fig, ax = plt.subplots(figsize=(7.0, 3.0))
    ax.plot(t * 1000, y * 3.0, lw=2, color=BLUE, label="ADAS 토크 요청 응답")
    ax.step([0, 5, 300], [0, 3, 3], where="post", color=GRAY, ls="--", lw=1.2, label="요청 3 N·m")
    ax.axhline(3 * 1.1, color=RED, ls=":", lw=1); ax.text(220, 3.35, "오버슈트 한계 +10%", fontsize=7.5)
    ax.axvline(50, color=GRAY, ls=":", lw=1); ax.text(52, 0.4, "90% 도달 ≤ 50ms", fontsize=7.5)
    ax.set_xlabel("시간 (ms)"); ax.set_ylabel("오버레이 토크 (N·m)"); ax.legend(fontsize=7.5, loc="lower right"); ax.grid(alpha=0.25)
    return _png(fig)


def fig_connector():
    fig, ax = plt.subplots(figsize=(7.0, 2.6)); ax.axis("off"); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    _box(ax, 0.03, 0.15, 0.38, 0.7, "", fc="#F4F6F9", ec=INK)
    ax.text(0.22, 0.9, "C1 전원 커넥터 (2핀, 6mm²)", ha="center", fontsize=8)
    for i, (n, c) in enumerate([("1  KL30", ORANGE), ("2  GND", INK)]):
        ax.add_patch(plt.Circle((0.14 + i * 0.16, 0.5), 0.07, fc="white", ec=c, lw=2)); ax.text(0.14 + i * 0.16, 0.5, n.split()[0], ha="center", va="center", fontsize=9)
        ax.text(0.14 + i * 0.16, 0.3, n.split()[1], ha="center", fontsize=7.5)
    _box(ax, 0.50, 0.15, 0.47, 0.7, "", fc="#F4F6F9", ec=INK)
    ax.text(0.735, 0.9, "C2 신호 커넥터 (16핀)", ha="center", fontsize=8)
    for k in range(16):
        x = 0.54 + (k % 8) * 0.055; y = 0.6 if k < 8 else 0.35
        ax.add_patch(plt.Circle((x, y), 0.02, fc="white", ec=BLUE, lw=1.2)); ax.text(x, y, str(k + 1), ha="center", va="center", fontsize=6)
    return _png(fig)


FIGS = {"context": fig_context, "block": fig_block, "assist": fig_assist_map, "states": fig_states, "thermal": fig_thermal,
        "lowvolt": fig_lowvolt, "tas": fig_tas, "ftti": fig_ftti, "network": fig_network, "step": fig_step, "conn": fig_connector}
_CACHE: dict = {}


# ============================================================================ document helpers
class Doc:
    def __init__(self, rev: str, doc_no: str = DOC_NO, product: str = "Column-type EPS ECU"):
        self.d = Document()
        st = self.d.styles["Normal"]; st.font.name = "Malgun Gothic"; st.element.rPr.rFonts.set(qn("w:eastAsia"), "Malgun Gothic")
        st.font.size = Pt(10.5); st.paragraph_format.line_spacing = 1.32; st.paragraph_format.space_after = Pt(5)
        for s in ("Heading 1", "Heading 2", "Heading 3", "Title"):
            self.d.styles[s].font.name = "Malgun Gothic"; self.d.styles[s].element.rPr.rFonts.set(qn("w:eastAsia"), "Malgun Gothic")
        sec = self.d.sections[0]; sec.left_margin = sec.right_margin = Cm(2.3); sec.top_margin = sec.bottom_margin = Cm(2.1)
        sec.header.paragraphs[0].text = f"{doc_no}   |   {product} 고객 요구사양서   |   ACME Motors 대외비"
        sec.footer.paragraphs[0].text = f"ACME Motors 샤시전자개발팀  ·  Rev {rev}  ·  본 문서의 무단 복제 및 제3자 제공을 금한다."
        self.n = {"fig": 0, "tbl": 0}; self.cnt: dict[str, int] = {}; self.reqs = 0

    def h(self, t, l=1): self.d.add_heading(t, l)
    def p(self, t, italic=False):
        para = self.d.add_paragraph(); r = para.add_run(t); r.italic = italic; return para
    def note(self, t):
        para = self.d.add_paragraph(); r = para.add_run("참고: " + t); r.font.size = Pt(9); r.font.color.rgb = RGBColor(0x55, 0x60, 0x6E)
    def bullets(self, items):
        for i in items: self.d.add_paragraph(i, style="List Bullet")
    def nid(self, dom):
        self.cnt[dom] = self.cnt.get(dom, 0) + 1; return f"REQ-{dom}-{self.cnt[dom]:03d}"
    def R(self, dom, text, verify=None, asil=None, rationale=None):
        rid = self.nid(dom); self.reqs += 1
        para = self.d.add_paragraph(); r = para.add_run(f"[{rid}] "); r.bold = True; r.font.color.rgb = RGBColor(0x1F, 0x5F, 0xBF); para.add_run(text)
        meta = ([f"ASIL {asil}"] if asil else []) + ([f"검증: {verify}"] if verify else []) + ([f"근거: {rationale}"] if rationale else [])
        if meta:
            q = self.d.add_paragraph(); q.paragraph_format.left_indent = Cm(1.0)
            rr = q.add_run(" · ".join(meta)); rr.font.size = Pt(8.5); rr.font.color.rgb = RGBColor(0x55, 0x60, 0x6E)
        return rid
    def RT(self, dom, caption, rows, verify_col=True):
        """Requirement table: ID | 요구사항 | ASIL | 검증방법 — each row becomes a requirement item on import."""
        out = [["ID", "요구사항", "ASIL", "검증방법"]]
        for r in rows:
            out.append([self.nid(dom), r[0], r[1] if len(r) > 1 else "QM", r[2] if len(r) > 2 else "HIL"]); self.reqs += 1
        return self.table(caption, out, widths=[3.3, 8.9, 1.3, 2.6])
    def fig(self, name, caption, width=15.2):
        if name not in _CACHE: _CACHE[name] = FIGS[name]()
        self.n["fig"] += 1
        self.d.add_picture(BytesIO(_CACHE[name]), width=Cm(width)); self.d.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
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
            t.autofit = False
            tblPr = t._tbl.tblPr
            lay = OxmlElement("w:tblLayout"); lay.set(qn("w:type"), "fixed"); tblPr.append(lay)
            grid = t._tbl.tblGrid
            for j, gc in enumerate(grid.findall(qn("w:gridCol"))):
                if j < len(widths): gc.set(qn("w:w"), str(int(widths[j] * 567)))
            for j, w in enumerate(widths):
                t.columns[j].width = Cm(w)
                for row in t.rows: row.cells[j].width = Cm(w)
        self.d.add_paragraph()
        return t
    def br(self): self.d.add_page_break()


# ============================================================================ content
def build(rev: str = "1.0") -> Path:
    D = Doc(rev); d = D.d
    d.add_paragraph("Column-type EPS ECU", style="Title")
    d.add_paragraph("고객 요구사양서 (Customer Requirements Specification)").alignment = WD_ALIGN_PARAGRAPH.CENTER
    d.add_paragraph(f"문서번호 {DOC_NO}   ·   개정 {rev}   ·   차량 프로젝트 C3 (중형 SUV, 2028 MY)").alignment = WD_ALIGN_PARAGRAPH.CENTER
    d.add_paragraph("발행: ACME Motors 샤시전자개발팀   ·   수신: EPS 시스템 공급사").alignment = WD_ALIGN_PARAGRAPH.CENTER
    d.add_paragraph()
    D.table("개정 이력", [["개정", "일자", "작성", "변경 내용"],
                         ["0.5", "2026-05-20", "정샤시", "RFQ 배포용 초안"],
                         ["0.9", "2026-08-01", "정샤시", "ADAS 오버레이 요구사항 및 FTTI 추가, 공급사 질의 반영"],
                         ["1.0", "2026-10-15", "정샤시", "SOR(Statement of Requirements) 확정판. 보안·OTA 요구사항 추가"]], widths=[1.4, 2.4, 2, 10.2])
    D.table("승인", [["역할", "이름", "부서", "일자"], ["작성", "정샤시", "샤시전자개발팀", "2026-10-15"], ["검토", "한안전", "기능안전팀", "2026-10-15"],
                    ["검토", "오보안", "차량보안팀", "2026-10-15"], ["승인", "윤팀장", "샤시전자개발팀", "2026-10-16"]], widths=[2, 3, 5, 3])
    D.p("본 문서의 요구사항은 공급사가 개발하는 EPS 제어기(ECU)와 그 소프트웨어에 적용된다. '해야 한다'는 필수, '하는 것이 바람직하다'는 권고 요구사항이다. 각 요구사항에는 고유 ID와 함께 ASIL 등급(표기가 없으면 QM)과 OEM이 기대하는 검증 방법을 표기하였다. 공급사는 모든 필수 요구사항에 대해 준수 여부(Compliance Matrix)를 회신해야 한다.")
    D.br()
    D.p("목차").runs[0].bold = True
    for line in ["1 개요", "2 시스템 개요 (경계, 차량 변형, 운용 시나리오 UC-01~12)", "3 기능 요구사항 (보조 토크, 복원·댐핑, 엔드스톱, 운전 모드, ADAS 오버레이, 각도 제어, MRM, 모터 제어, SW 자원, 기능 조정, 진동 저감, 진동 경고)",
                 "4 운용 모드 및 전원 관리", "5 센서 인터페이스 (TAS, 모터 위치, 조향각)", "6 차량 통신", "7 진단", "8 기능 안전", "9 열 관리", "10 사이버 보안", "11 SW 업데이트 및 메모리",
                 "12 전기적 인터페이스 및 하드웨어 부품", "13 환경 및 EMC", "14 조향 성능 및 NVH", "15 생산·서비스·품질", "16 검증 요구사항 및 납품물",
                 "부록 A 변경 절차 · B 회신 양식 · C 신호 목록 · D 보조 토크 맵 · E 캘리브레이션 파라미터 · F 미결 사항"]:
        q = D.d.add_paragraph(line); q.paragraph_format.left_indent = Cm(0.6)
    D.br()

    # 1 ---------------------------------------------------------------- 개요
    D.h("1 개요")
    D.h("1.1 목적", 2)
    D.p("본 문서는 ACME Motors C3 차량에 장착되는 컬럼 타입 전동식 조향장치(C-EPS)의 전자제어유닛에 대한 고객 요구사항을 정의한다. EPS 제어기는 운전자의 조향 토크와 차량 상태를 기반으로 BLDC 모터의 보조 토크를 제어하여 조향력을 경감하고, ADAS 제어기의 토크·각도 요청을 받아 차로 유지 및 자동 주차 기능을 수행한다.")
    D.p("공급사는 본 문서를 기준으로 시스템 요구사항(SYS.2)과 소프트웨어·하드웨어 요구사항(SWE.1, HWE.1)을 도출하고, 양방향 추적성을 유지해야 한다. 본 문서의 요구사항이 변경되면 공급사는 영향 분석 결과를 10 영업일 이내에 회신해야 한다.")
    D.h("1.2 적용 범위", 2)
    D.p("적용 범위는 EPS ECU 하드웨어(파워 스테이지 포함), 임베디드 소프트웨어(AUTOSAR Classic R4.4 이상), 토크·각도 센서 인터페이스, 모터 제어, 차량 네트워크 인터페이스, 진단, 기능 안전, 사이버 보안, 생산 및 서비스 요구사항이다. 컬럼 기구, 감속기, 모터 본체의 기계 설계는 별도 기구 사양서(MS-EPS-C3)를 따른다.")
    D.h("1.3 참조 문서", 2)
    D.table("참조 문서", [["번호", "문서", "개정", "비고"], ["[1]", "AMS-1100 전장 부품 전원 품질 규격", "2025", "ACME 사내 규격"], ["[2]", "AMS-1200 EMC 시험 규격", "2025", "ACME 사내 규격"],
                         ["[3]", "AMS-1300 환경·내구 시험 규격", "2024", "ACME 사내 규격"], ["[4]", "AMS-2100 CAN-FD 통신 사양서 (C3 Chassis)", "1.3", "DBC 포함"],
                         ["[5]", "AMS-2200 진단 사양서 (UDS)", "2.0", "CDD 포함"], ["[6]", "AMS-3100 사이버 보안 요구사항", "1.1", "ISO/SAE 21434 기반"],
                         ["[7]", "ISO 26262:2018 Part 1~9", "2018", "기능 안전"], ["[8]", "ISO 14229-1:2020 UDS", "2020", "진단"], ["[9]", "ISO 11898-1/-2", "2015/2016", "CAN-FD"],
                         ["[10]", "SAE J2716 SENT", "2016", "토크 센서 인터페이스"], ["[11]", "AUTOSAR E2E Protocol Specification", "R22-11", "E2E Profile 5/7"],
                         ["[12]", "HARA-EPS-C3 위험 분석 및 리스크 평가", "1.2", "안전 목표 출처"]], widths=[1.3, 8.4, 2, 4])
    D.h("1.4 용어 및 약어", 2)
    D.table("용어 및 약어", [["약어", "정의"], ["ADAS", "Advanced Driver Assistance System"], ["C-EPS", "Column-type Electric Power Steering"], ["CSA", "Current Sense Amplifier"],
                           ["DCU", "Domain Control Unit"], ["DTC", "Diagnostic Trouble Code"], ["E2E", "End-to-End 보호 (CRC + Alive Counter)"], ["FDTI / FRTI", "Fault Detection / Reaction Time Interval"],
                           ["FTTI", "Fault Tolerant Time Interval"], ["KL15 / KL30", "점화 전원 / 상시 전원"], ["LKA / LFA", "Lane Keeping Assist / Lane Following Assist"], ["MRM", "Minimal Risk Manoeuvre"],
                           ["PA", "Parking Assist (자동 주차)"], ["SAS", "Steering Angle Sensor"], ["SecOC", "Secure Onboard Communication"], ["SENT", "Single Edge Nibble Transmission (SAE J2716)"],
                           ["SOR", "Statement of Requirements"], ["TAS", "Torque and Angle Sensor"], ["WUP", "Wake-up Pattern"]], widths=[3.2, 12.8])
    D.h("1.5 요구사항 우선순위 및 회신 형식", 2)
    D.p("공급사는 요구사항마다 다음 중 하나로 회신한다: 준수(C), 부분 준수(PC, 대안 제시 필수), 미준수(NC, 사유 필수), 해당 없음(NA). PC·NC 회신은 SOR 확정 전 기술 협의 대상이며, 확정 후에는 변경 요청(CR) 절차를 따른다.")
    D.table("요구사항 분류 체계", [["도메인 코드", "내용", "주 관련 공정"], ["ASSIST", "보조 토크·조향감 제어 기능", "SYS.2 / SWE.1"], ["ADAS", "ADAS 토크·각도 인터페이스", "SYS.2 / SWE.1"],
                                 ["MODE", "운용 모드·전원 관리", "SYS.2 / SWE.1 / HWE.1"], ["SENS", "센서 인터페이스", "SYS.2 / HWE.1 / SWE.1"], ["COM", "차량 통신", "SWE.1"], ["DIAG", "진단·DTC", "SWE.1"],
                                 ["SAFE", "기능 안전", "SYS.2 / HWE.1 / SWE.1"], ["SEC", "사이버 보안", "SYS.2 / SWE.1"], ["ELEC", "전기적 특성", "SYS.2 / HWE.1"], ["ENV", "환경·EMC·기계", "SYS.2 / HWE.1"],
                                 ["PERF", "조향 성능·NVH", "SYS.2"], ["THERM", "열 관리", "SYS.2 / HWE.1 / SWE.1"], ["NVM", "비휘발성 메모리·캘리브레이션", "SWE.1"], ["UPD", "SW 업데이트·OTA", "SWE.1"], ["EOL", "생산·서비스", "SYS.2"]], widths=[3, 8, 5])
    D.br()

    # 2 ---------------------------------------------------------------- 시스템 개요
    D.h("2 시스템 개요")
    D.h("2.1 시스템 경계", 2)
    D.p("EPS 제어기는 조향 컬럼에 장착되며, 토크·각도 센서(TAS)의 이중 채널 SENT 신호와 모터 위치 센서 신호를 입력받아 3상 BLDC 모터를 FOC 방식으로 구동한다. 차량 측과는 Chassis CAN-FD와 ADAS 전용 CAN-FD 두 채널로 통신한다. 그림 1은 시스템 경계와 외부 인터페이스를 나타낸다.")
    D.fig("context", "EPS 제어기 시스템 경계 및 외부 인터페이스")
    D.p("그림 2는 OEM이 가정하는 제어기 내부 구성의 참고 블록도이다. 공급사는 동등 이상의 안전성과 성능을 입증하는 조건으로 다른 구성을 제안할 수 있다.")
    D.fig("block", "EPS 제어기 참고 블록도 (공급사 제안 가능)")
    D.h("2.2 차량 변형", 2)
    D.p("C3 차량은 다음 세 가지 변형으로 생산된다. 변형 정보는 EOL에서 코딩되며(REQ-EOL-004), 제어기는 코딩된 변형에 맞는 보조 토크 맵과 파라미터를 사용해야 한다.")
    D.table("차량 변형별 주요 파라미터", [["변형", "전축 하중", "최대 랙 력", "모터 피크 전류", "타이어", "ADAS 사양"],
                                       ["C3-Base (2WD)", "1,050 kg", "9.5 kN", "70 A", "235/60 R18", "LKA"], ["C3-Premium (AWD)", "1,180 kg", "10.5 kN", "80 A", "245/50 R20", "LKA, LFA, PA"],
                                       ["C3-Sport (AWD)", "1,210 kg", "10.8 kN", "80 A", "255/45 R21", "LKA, LFA, PA, 스포츠 모드"]], widths=[3, 2.2, 2.2, 2.6, 2.6, 3.4])
    D.R("ASSIST", "EPS 제어기는 EOL에서 코딩된 차량 변형(Base/Premium/Sport)에 따라 보조 토크 맵, 모터 전류 한계, ADAS 기능 허용 여부를 선택해야 한다.", "EOL 코딩 시험 + HIL", None, "차량 변형별 주요 파라미터 표")
    D.R("ASSIST", "EPS 제어기는 변형 코딩 값이 유효하지 않거나 기록되지 않은 경우 C3-Base 파라미터로 동작하고 DTC C1A10을 저장해야 한다.", "HIL (코딩 오류 주입)")
    D.h("2.3 운용 시나리오", 2)
    D.p("다음 사용 사례는 EPS 제어기의 대표 운용 시나리오이다. 각 사용 사례의 기대 결과는 시스템 검증(SYS.5)의 합격 기준으로 사용된다.")
    ucs = [("UC-01 저속 주차 조향", "차속 0~10 km/h, 엔진 ON", "운전자가 제자리에서 핸들을 끝까지 돌린다.", "조향력 3.5 N·m 이하, 엔드스톱 충격 완화"),
           ("UC-02 고속 직진 주행", "차속 100~150 km/h", "운전자가 미세 조향으로 차로를 유지한다.", "중립 부근 조향감 안정, 쏠림 보상"),
           ("UC-03 차로 유지 보조 (LKA)", "차속 60 km/h 이상, LKA ON", "차로 이탈 경고 후 ADAS가 토크 오버레이를 요청한다.", "요청 토크 50ms 이내 추종, 운전자 개입 시 즉시 양보"),
           ("UC-04 자동 주차 (PA)", "차속 7 km/h 이하, PA 활성", "ADAS가 목표 조향각을 요청하고 EPS가 각도 제어를 수행한다.", "각도 오차 ±2° 이내, 운전자 토크 3 N·m 초과 시 해제"),
           ("UC-05 고장 시 안전 상태 진입", "임의 주행", "토크 센서 한 채널에 드리프트가 발생한다.", "20ms 이내 검출·반응, 경고등 점등, 안전 상태 유지"),
           ("UC-06 저전압 크랭킹", "시동 중 KL30 6V까지 강하", "시동 직후 운전자가 조향을 시작한다.", "리셋 없이 보조 재개, 보조 토크 점진 복귀"),
           ("UC-07 과열 연속 주차", "외기 45°C, 반복 엔드스톱 조향", "운전자가 10분간 반복 주차 조향을 한다.", "열 디레이팅으로 보호, 보조 상실 없음"),
           ("UC-08 OTA 업데이트", "차량 정차, IG ON, 배터리 12.5V 이상", "게이트웨이가 EPS SW를 무선 업데이트한다.", "업데이트 중 보조 금지, 실패 시 이전 SW로 복귀"),
           ("UC-09 운전자 개입에 의한 LKA 해제", "LKA 오버레이 중, 차속 90 km/h", "운전자가 차로 변경을 위해 2.5 N·m 이상 조향한다.", "200ms 이내 오버레이 해제, 운전자에게 저항감 없음"),
           ("UC-10 MRM 비상 정차", "LFA 중 운전자 무응답", "ADAS가 MRM을 요청하고 갓길로 정차한다.", "확장 오버레이 한계로 차로 유지, EPS 고장 시에도 Degraded Assist 10 s"),
           ("UC-11 서비스 센터 재학습", "조향 컬럼 교환 후", "정비사가 진단기로 조향각 영점과 엔드스톱을 재학습한다.", "학습 완료 후 ADAS 기능 AVAILABLE 복귀"),
           ("UC-12 겨울철 저온 시동", "외기 -35°C, 12시간 냉간 방치", "시동 직후 주차장에서 조향한다.", "3초 이내 정격 보조, 그리스 점도에 의한 조향력 증가 보상")]
    for title, pre, flow, exp in ucs:
        D.table(title, [["항목", "내용"], ["사전 조건", pre], ["시나리오", flow], ["기대 결과", exp]], widths=[3, 13])
    D.br()

    # 3 ---------------------------------------------------------------- 기능 요구사항
    D.h("3 기능 요구사항")
    D.h("3.1 보조 토크 제어", 2)
    D.p("보조 토크는 운전자 조향 토크와 차속의 함수로 결정된다. 그림 3은 C3-Premium 변형의 기준 보조 토크 맵이다. 공급사는 튜닝 단계에서 맵을 조정할 수 있으나, 불감대·최대값·차속 보간 원칙은 유지해야 한다.")
    D.fig("assist", "차속별 기준 보조 토크 맵 (C3-Premium)")
    D.R("ASSIST", "EPS 제어기는 운전자 조향 토크와 차속을 입력으로 하는 2차원 보조 토크 맵에 따라 모터 보조 토크를 산출해야 한다.", "HIL + 차량 튜닝 평가")
    D.R("ASSIST", "보조 토크 맵의 차속 축은 0, 10, 30, 60, 80, 120, 150 km/h 이상 7개 이상의 격자점을 가져야 하며 격자점 사이는 선형 보간해야 한다.", "단위 시험 + HIL")
    D.R("ASSIST", "운전자 조향 토크가 ±0.4 N·m 이내인 불감대에서는 보조 토크를 출력하지 않아야 한다.", "HIL")
    D.R("ASSIST", "EPS 제어기는 보조 토크 산출 주기를 1ms 이하로 유지해야 한다.", "TRACE32 타이밍 측정")
    D.R("ASSIST", "차속 신호가 무효(Invalid) 또는 타임아웃 상태이면 EPS 제어기는 차속 30 km/h에 해당하는 보조 토크 맵을 사용하고 DTC U0122를 저장해야 한다.", "HIL (CAN 타임아웃 주입)", "B")
    D.R("ASSIST", "차속 변화에 의한 보조 토크 변화율은 1 N·m/100ms를 넘지 않아야 한다.", "HIL")
    D.R("ASSIST", "EPS 제어기는 엔진 정지(또는 READY OFF) 상태에서 보조 토크를 출력하지 않아야 하며, 엔진 시동 후 500ms 이내에 보조를 시작해야 한다.", "차량 시험")
    D.R("ASSIST", "보조 시작 및 종료 시 보조 토크는 200ms 이상의 램프로 증가·감소시켜 운전자가 급격한 조향력 변화를 느끼지 않도록 해야 한다.", "차량 시험 + HIL")
    D.h("3.2 복원 및 댐핑 제어", 2)
    D.p("저속 회전 후 핸들 복원이 부족하거나 고속에서 핸들이 과도하게 복원되는 현상을 보상하기 위해 능동 복원과 댐핑 제어를 적용한다.")
    D.RT("ASSIST", "복원·댐핑·보상 제어 요구사항", [
        ("EPS 제어기는 차속 5~60 km/h 구간에서 조향각과 조향 속도에 따른 능동 복원 토크를 최대 2.0 N·m까지 출력해야 한다.", "QM", "차량 시험"),
        ("EPS 제어기는 조향 속도에 비례하는 댐핑 토크를 출력해야 하며, 댐핑 계수는 차속에 따라 0.002~0.02 N·m/(deg/s) 범위에서 조정할 수 있어야 한다.", "QM", "HIL + 차량"),
        ("EPS 제어기는 모터 및 감속기 관성에 의한 조향 지연을 보상하는 관성 보상 토크를 출력해야 한다.", "QM", "차량 튜닝 평가"),
        ("EPS 제어기는 감속기 마찰에 의한 조향감 저하를 보상하는 마찰 보상 토크를 출력해야 하며, 보상량은 최대 0.8 N·m여야 한다.", "QM", "HIL"),
        ("EPS 제어기는 차량 쏠림(Pull) 보상 기능을 제공해야 하며, 직진 주행 중 운전자 토크 평균값을 학습하여 최대 1.0 N·m까지 보상해야 한다.", "QM", "차량 시험"),
        ("쏠림 보상 학습값은 IG OFF 시 NvM에 저장되어야 하며 서비스 진단(0x31 루틴)으로 초기화할 수 있어야 한다.", "QM", "HIL + 진단기"),
        ("모든 보상 토크의 합은 3.0 N·m를 넘지 않아야 하며, 운전자 토크와 반대 방향 보상은 1.5 N·m로 제한해야 한다.", "C", "HIL (고장 주입)")])
    D.h("3.3 엔드스톱 보호", 2)
    D.R("ASSIST", "EPS 제어기는 조향각이 기계적 엔드스톱의 ±20° 이내로 접근하면 보조 토크를 점진적으로 감소시켜 엔드스톱 충격을 완화해야 한다.", "차량 시험")
    D.R("ASSIST", "엔드스톱 위치는 조향각 학습(REQ-SENS-012) 결과를 사용해야 하며, 학습 전에는 엔드스톱 보호를 비활성화하고 보조 토크를 70%로 제한해야 한다.", "HIL")
    D.R("ASSIST", "엔드스톱에 3초 이상 연속으로 접촉한 상태가 유지되면 모터 전류를 50%로 제한해야 한다.", "벤치 + 차량", rationale="열 보호")
    D.h("3.4 운전 모드", 2)
    D.R("ASSIST", "EPS 제어기는 운전 모드 신호(COMFORT/NORMAL/SPORT)에 따라 서로 다른 보조 토크 맵 세트를 사용해야 한다.", "HIL + 차량")
    D.R("ASSIST", "운전 모드 변경 시 보조 토크 맵은 1초 동안 선형 블렌딩되어야 하며, 조향 중(조향 속도 30 deg/s 이상)에는 블렌딩을 지연해야 한다.", "HIL")
    D.R("ASSIST", "SPORT 모드는 C3-Sport 변형에서만 허용되어야 하며, 다른 변형에서 SPORT 요청을 받으면 NORMAL 모드를 유지해야 한다.", "HIL")
    D.br()

    D.h("3.5 ADAS 토크 오버레이 (LKA/LFA)", 2)
    D.p("ADAS 제어기는 ADAS Private CAN-FD로 토크 오버레이 요청(ADAS_TqReq)을 10ms 주기로 송신한다. EPS 제어기는 요청 토크를 보조 토크에 더해 출력하되, 운전자 개입을 최우선으로 해야 한다. 그림 4는 토크 요청에 대한 응답 요구사항이다.")
    D.fig("step", "ADAS 토크 오버레이 스텝 응답 요구사항")
    D.R("ADAS", "EPS 제어기는 ADAS 토크 오버레이 요청을 수신하면 50ms 이내에 요청 토크의 90%에 도달해야 하며 오버슈트는 10% 이하여야 한다.", "HIL (스텝 응답)", "D")
    D.R("ADAS", "EPS 제어기는 ADAS 오버레이 토크를 ±3.0 N·m로 제한해야 하며, 제한을 초과하는 요청은 제한값으로 포화시키고 상태 신호에 포화 플래그를 설정해야 한다.", "HIL", "D")
    D.R("ADAS", "EPS 제어기는 오버레이 토크 변화율을 10 N·m/s로 제한해야 한다.", "HIL", "D")
    D.R("ADAS", "운전자 조향 토크가 2.5 N·m 이상 100ms 이상 지속되면 EPS 제어기는 운전자 개입으로 판단하고 오버레이 토크를 200ms 이내에 0으로 감소시켜야 한다.", "HIL + 차량", "D")
    D.R("ADAS", "EPS 제어기는 ADAS 요청 메시지의 E2E 검사(CRC, Alive Counter) 실패가 3회 연속 발생하면 오버레이 기능을 중지하고 ADAS 상태를 FAULT로 송신해야 한다.", "HIL (E2E 오류 주입)", "D")
    D.R("ADAS", "ADAS 요청 메시지가 50ms 이상 수신되지 않으면 EPS 제어기는 오버레이 토크를 100ms 램프로 0까지 감소시키고 DTC U0423을 저장해야 한다.", "HIL (타임아웃 주입)", "D")
    D.R("ADAS", "EPS 제어기는 차속 60 km/h 미만에서 LKA 오버레이 요청을 거부해야 하며, LFA 요청은 0~180 km/h에서 허용해야 한다.", "HIL")
    D.R("ADAS", "EPS 제어기는 ADAS 기능 가용 상태(AVAILABLE/NOT_AVAILABLE/FAULT)와 거부 사유 코드를 10ms 주기로 ADAS 제어기에 송신해야 한다.", "CANoe")
    D.h("3.6 각도 제어 (자동 주차)", 2)
    D.RT("ADAS", "자동 주차 각도 제어 요구사항", [
        ("EPS 제어기는 자동 주차 모드에서 ADAS 제어기의 목표 조향각을 추종해야 하며 정상 상태 오차는 ±2° 이내여야 한다.", "C", "HIL + 차량"),
        ("각도 제어 모드에서 조향 속도는 최대 540 deg/s로 제한해야 한다.", "C", "HIL"),
        ("각도 제어 모드는 차속 7 km/h 이하에서만 진입할 수 있어야 하며, 차속이 10 km/h를 초과하면 즉시 종료해야 한다.", "C", "HIL"),
        ("운전자 조향 토크가 3.0 N·m 이상이면 각도 제어를 200ms 이내에 종료하고 일반 보조로 전환해야 한다.", "C", "HIL + 차량"),
        ("각도 제어 진입·종료 시 모터 토크는 300ms 램프로 전환되어 핸들 튀는 현상이 없어야 한다.", "QM", "차량 시험"),
        ("목표 조향각 변화량이 10ms당 15°를 초과하는 요청은 비정상 요청으로 판단하고 각도 제어를 종료해야 한다.", "C", "HIL (오류 주입)")])
    D.h("3.7 MRM 지원", 2)
    D.R("ADAS", "EPS 제어기는 ADAS 제어기의 MRM(최소 위험 거동) 요청 시 LFA 오버레이 한계를 ±4.0 N·m로 확장하고 운전자 개입 임계값을 3.5 N·m로 상향해야 한다.", "HIL", "D")
    D.R("ADAS", "MRM 상태에서 EPS 제어기 내부 고장이 발생하면 보조 기능을 유지하는 성능 저하 모드(Degraded Assist)를 최소 10초 유지해야 한다.", "HIL (고장 주입)", "D")
    D.br()

    D.h("3.8 모터 제어", 2)
    D.p("모터 제어는 FOC(Field Oriented Control) 방식을 기준으로 한다. 공급사는 전류 제어 루프의 대역폭과 안정성을 문서로 입증하고, 모든 차량 변형에서 동일한 제어 구조를 사용해야 한다.")
    D.RT("ASSIST", "모터 제어 요구사항", [
        ("EPS 제어기는 d/q축 전류 제어 루프를 50µs 이하 주기로 수행해야 한다.", "D", "TRACE32 + 오실로스코프"),
        ("q축 전류 제어 대역폭은 1kHz 이상, d축 전류 지령은 정상 상태에서 0A로 유지해야 한다.", "QM", "주파수 응답 시험"),
        ("EPS 제어기는 모터 회전수가 3,000 rpm을 초과하면 약계자(Field Weakening) 제어로 전압 포화를 방지해야 한다.", "QM", "다이나모"),
        ("PWM 데드타임은 MOSFET 사양에 맞게 300~800ns 범위에서 설정할 수 있어야 하며 데드타임 보상을 적용해야 한다.", "QM", "오실로스코프"),
        ("EPS 제어기는 모터 토크 지령과 실제 전류 기반 추정 토크의 차이가 3 N·m(모터축 환산) 이상 10ms 지속되면 토크 제어 고장으로 판단해야 한다.", "D", "HIL (고장 주입)"),
        ("모터 역기전력에 의한 회생 전압이 KL30 기준 +3V를 넘지 않도록 회생 전류를 제한해야 한다.", "B", "벤치"),
        ("EPS 제어기는 모터 상 단선을 정차 중 100ms, 주행 중 10ms 이내에 검출해야 한다.", "D", "벤치 (단선 주입)")])
    D.h("3.9 소프트웨어 아키텍처 및 자원", 2)
    D.p("EPS 소프트웨어는 AUTOSAR Classic 플랫폼 기반으로 개발한다. 공급사는 OEM이 제공하는 통신·진단 BSW 구성 파일(ARXML)을 사용하고, 어플리케이션 SWC 인터페이스를 OEM과 합의해야 한다.")
    D.table("OS 태스크 구성 (참고)", [["태스크", "주기", "우선순위", "주요 기능", "WCET 예산"], ["Task_Isr_Pwm", "50 µs", "최고", "전류 제어, PWM 갱신", "25 µs"],
                                    ["Task_1ms", "1 ms", "높음", "보조 토크 산출, TAS 처리, 안전 감시", "400 µs"], ["Task_5ms", "5 ms", "중간", "ADAS 처리, 열 모델", "1.2 ms"],
                                    ["Task_10ms", "10 ms", "중간", "CAN 송수신, E2E, 진단 감시", "2 ms"], ["Task_100ms", "100 ms", "낮음", "NvM, DTC 에이징, 학습", "10 ms"],
                                    ["Task_Bg", "백그라운드", "최저", "RAM/ROM 주기 시험", "—"]], widths=[3, 2, 2, 6, 3])
    D.RT("ASSIST", "소프트웨어 및 자원 요구사항", [
        ("EPS 소프트웨어는 AUTOSAR Classic R4.4 이상을 기반으로 해야 하며 OEM 제공 통신·진단 구성 파일을 사용해야 한다.", "QM", "설계 리뷰"),
        ("최악 조건에서 CPU 부하는 코어별 70% 이하여야 한다.", "QM", "TRACE32 프로파일링"),
        ("양산 SW의 Flash 및 RAM 사용량은 각각 전체 용량의 70% 이하여야 한다.", "QM", "빌드 리포트"),
        ("ASIL 소프트웨어는 MISRA C:2012 필수 규칙을 100% 준수해야 하며 권고 규칙 위반은 정당화 문서로 관리해야 한다.", "D", "정적 분석"),
        ("ASIL C/D 소프트웨어 유닛은 MC/DC 커버리지 100%를 달성해야 한다 (미달 시 정당화 필요).", "D", "단위 시험 리포트"),
        ("1ms 태스크의 시작 지터는 50µs 이하여야 한다.", "B", "TRACE32 타이밍"),
        ("데드라인 위반 또는 태스크 실행 순서 오류는 WdgM으로 검출하여 안전 상태로 천이해야 한다.", "D", "고장 주입 (TRACE32)")])
    D.br()

    D.h("3.10 기능 간 조정 (Arbitration)", 2)
    D.p("여러 기능이 동시에 토크를 요청할 때의 우선순위와 제한 방식은 다음 표를 따른다. 상위 우선순위 기능이 활성화되면 하위 기능의 토크는 표에 정의된 방식으로 제한된다.")
    D.table("토크 요청 우선순위", [["우선순위", "기능", "토크 한계", "하위 기능 처리"], ["1", "안전 상태 / 안전 감시 제한", "0 또는 제한값", "모두 제한"], ["2", "운전자 개입 감지", "—", "ADAS 오버레이 해제 (200 ms)"],
                                 ["3", "열·전압 디레이팅", "전압 범위 표 / 그림 10", "비례 축소"], ["4", "자동 주차 각도 제어", "모터 한계의 60%", "보상 제어 비활성"], ["5", "MRM 오버레이", "±4.0 N·m", "LKA/LFA 무시"],
                                 ["6", "LFA / LKA 오버레이", "±3.0 N·m", "보상 제어 유지"], ["7", "기본 보조 + 보상 제어", "맵 / ±3.0 N·m", "—"]], widths=[1.8, 5, 3.6, 5.6])
    D.RT("ADAS", "기능 조정 요구사항", [
        ("EPS 제어기는 표의 우선순위에 따라 토크 요청을 조정해야 하며 우선순위가 다른 요청이 동시에 활성화될 때 상위 요청만 출력에 반영해야 한다.", "D", "HIL"),
        ("기능 전환 시 출력 토크의 불연속은 0.5 N·m를 넘지 않아야 한다.", "C", "HIL"),
        ("디레이팅으로 보조 토크가 제한되는 동안 ADAS 오버레이 한계도 같은 비율로 축소하고 ADAS 상태에 제한 사유를 송신해야 한다.", "C", "HIL + CANoe"),
        ("자동 주차 각도 제어 중 ADAS 토크 오버레이 요청이 동시에 수신되면 각도 제어를 우선하고 오버레이 요청은 거부해야 한다.", "C", "HIL")])
    D.h("3.11 노면 정보 및 진동 저감", 2)
    D.RT("ASSIST", "노면 피드백·진동 저감 요구사항", [
        ("EPS 제어기는 노면 정보 전달을 위해 1~5Hz 대역의 랙 력 변화를 운전자에게 전달해야 하며 보조 토크 맵으로 이를 감쇠시키지 않아야 한다.", "QM", "차량 평가"),
        ("EPS 제어기는 휠 불균형에 의한 10~20Hz 대역 진동(Shimmy)을 50% 이상 저감하는 능동 진동 저감 기능을 제공해야 한다.", "QM", "차량 시험"),
        ("브레이크 저더에 의한 조향 진동은 진동 저감 기능으로 0.3 N·m p-p 이하로 억제해야 한다.", "QM", "차량 시험"),
        ("진동 저감 기능의 출력 토크는 ±1.0 N·m로 제한해야 한다.", "B", "HIL")])
    D.br()

    D.h("3.12 핸들 진동 경고 (Haptic)", 2)
    D.RT("ADAS", "핸들 진동 경고 요구사항", [
        ("EPS 제어기는 ADAS 제어기의 진동 경고 요청(ADAS_HapticReq)을 받으면 핸들에 30~40Hz, 진폭 0.4 N·m의 진동 토크를 출력해야 한다.", "QM", "차량 평가"),
        ("진동 경고는 요청 1회당 최대 1.5초 동안 출력하고, 요청이 해제되면 100ms 이내에 종료해야 한다.", "QM", "HIL"),
        ("진동 경고 토크는 운전자 조향 의도에 영향을 주지 않도록 평균값이 0 N·m여야 한다.", "B", "HIL"),
        ("EPS 제어기가 LIMITED 또는 SAFE STATE 상태이면 진동 경고 요청을 거부하고 거부 사유를 송신해야 한다.", "QM", "CANoe")])
    D.br()

    # 4 ---------------------------------------------------------------- 운용 모드 및 전원
    D.h("4 운용 모드 및 전원 관리")
    D.p("EPS 제어기의 운용 상태와 천이 조건은 그림 5와 같다. 상태 천이는 아래 상태 천이 조건 표를 만족해야 한다.")
    D.fig("states", "EPS 제어기 운용 상태 천이도")
    D.table("상태 천이 조건", [["현재 상태", "다음 상태", "조건", "최대 시간"], ["OFF/SLEEP", "INIT", "KL15 ON 또는 CAN WUP 수신", "—"], ["INIT", "READY", "자기 진단 완료, 센서 유효", "300 ms"],
                              ["READY", "ASSIST", "엔진 RUN 신호 + 차속 유효", "500 ms"], ["ASSIST", "LIMITED", "과열·저전압·과전압 조건", "10 ms"], ["ASSIST/LIMITED", "SAFE STATE", "치명 고장 검출", "FTTI 이내"],
                              ["ASSIST", "SLEEP", "KL15 OFF 후 차속 0, 네트워크 슬립", "3 s"]], widths=[3, 3, 7, 3])
    D.R("MODE", "EPS 제어기는 KL15 ON 또는 CAN 웨이크업 후 300ms 이내에 자기 진단을 완료하고 READY 상태로 진입해야 한다.", "HIL")
    D.R("MODE", "EPS 제어기는 INIT 상태에서 RAM/ROM 테스트, MCU 코어 자가 시험, 게이트 드라이버 자기 진단, 상 차단 릴레이 동작 확인을 수행해야 한다.", "TRACE32 + HIL", "D")
    D.R("MODE", "주행 중 KL15 신호가 OFF가 되더라도 차속이 3 km/h 이상이면 EPS 제어기는 보조 기능을 유지해야 한다.", "HIL", "B")
    D.R("MODE", "EPS 제어기는 KL15 OFF 후 차속 0 km/h, 네트워크 슬립 요청이 모두 충족되면 3초 이내에 SLEEP 상태로 천이해야 한다.", "CANoe + 전류계")
    D.R("MODE", "SLEEP 상태의 암전류는 KL30 12.6V, 25°C에서 100µA 이하여야 한다.", "전류계")
    D.R("MODE", "EPS 제어기는 SLEEP 상태에서 CAN WUP 수신 후 150ms 이내에 CAN 송신을 시작해야 한다.", "CANoe 타이밍")
    D.h("4.1 전압 범위별 동작", 2)
    D.p("그림 6은 KL30 전압에 따른 허용 보조 토크이다. 저전압 디레이팅은 보조 상실 없이 조향력이 점진적으로 증가하도록 설계되어야 한다.")
    D.fig("lowvolt", "KL30 전압에 따른 허용 보조 토크")
    D.table("전압 범위별 기능 상태", [["KL30 전압", "기능 상태", "보조 토크", "통신·진단"], ["16.5 ~ 18 V", "과전압 디레이팅", "100 → 0 % 선형", "정상"], ["10 ~ 16.5 V", "정상 (Class A)", "100 %", "정상"],
                                  ["7 ~ 10 V", "저전압 디레이팅", "0 → 100 % 선형", "정상"], ["6 ~ 7 V", "보조 중지, 리셋 없음", "0 %", "통신 유지"], ["6 V 미만", "리셋 허용", "0 %", "복귀 후 재개"],
                                  ["18 ~ 26 V (60 s)", "점프 스타트 보호", "0 %", "손상 없음"]], widths=[3.4, 4, 4, 4.6])
    D.RT("ELEC", "전원 전압 요구사항", [
        ("EPS 제어기는 KL30 10V ~ 16.5V 범위에서 모든 기능을 정격 성능으로 수행해야 한다.", "QM", "벤치 (전원 스윕)"),
        ("EPS 제어기는 KL30 7V ~ 10V 범위에서 보조 토크를 전압에 비례하여 0%~100%로 제한해야 한다.", "B", "벤치 + HIL"),
        ("EPS 제어기는 KL30 6V ~ 7V 범위에서 리셋 없이 통신 및 진단 기능을 유지해야 한다.", "QM", "벤치"),
        ("EPS 제어기는 KL30 16.5V ~ 18V 범위에서 보조 토크를 전압에 반비례하여 100%~0%로 제한해야 한다.", "QM", "벤치"),
        ("EPS 제어기는 26V 점프 스타트 전압을 60초 동안 손상 없이 견뎌야 한다.", "QM", "벤치"),
        ("EPS 제어기는 역극성(-14V, 60초) 인가 시 손상되지 않아야 한다.", "QM", "벤치"),
        ("저전압으로 보조가 중지된 후 KL30이 10V 이상으로 복귀하면 EPS 제어기는 500ms 램프로 보조를 재개해야 한다.", "B", "벤치 + HIL")])
    D.R("ELEC", "EPS 제어기는 AMS-1100의 전원 과도 펄스(펄스 1, 2a, 2b, 3a, 3b, 4, 5b)에 대해 규격의 기능 상태 등급을 만족해야 한다.", "EMC 시험소")
    D.R("ELEC", "크랭킹 프로파일(AMS-1100 프로파일 C, 최저 6V)에서 EPS 제어기는 리셋되지 않아야 하며 크랭킹 종료 후 500ms 이내에 보조를 재개해야 한다.", "벤치 (크랭킹 시뮬레이터)", "B")
    D.R("ELEC", "모터 전원 라인의 최대 연속 전류는 C3-Premium 기준 40A, 피크 80A(1초)를 초과하지 않아야 한다.", "벤치 + 차량")
    D.R("ELEC", "EPS 제어기는 정상 동작 중 KL30 라인으로 리플 전류를 5A peak-peak 이하로 제한해야 한다.", "오실로스코프")
    D.br()

    # 5 ---------------------------------------------------------------- 센서
    D.h("5 센서 인터페이스")
    D.h("5.1 토크·각도 센서 (TAS)", 2)
    D.p("TAS는 두 개의 독립 채널(T1, T2)로 토크를 SENT 프로토콜로 출력하며, 두 채널은 서로 반대 부호를 갖는다. EPS 제어기는 두 채널을 상호 비교하여 센서 고장을 검출해야 한다. 그림 7은 채널 편차 검출 예이다.")
    D.fig("tas", "TAS 이중 채널 상호 비교에 의한 드리프트 검출")
    D.table("TAS 신호 사양", [["항목", "채널 1 (T1)", "채널 2 (T2)", "비고"], ["프로토콜", "SENT (SAE J2716), 3µs tick", "SENT, 3µs tick", "Fast channel 12bit"],
                             ["측정 범위", "±10 N·m", "±10 N·m", "역부호 출력"], ["분해능", "0.005 N·m", "0.005 N·m", ""], ["갱신 주기", "≤ 1 ms", "≤ 1 ms", ""], ["각도 출력", "0~1440° (멀티턴)", "—", "Slow channel"],
                             ["전원", "5V ±5%, 15mA", "5V ±5%, 15mA", "채널별 독립 전원"]], widths=[3, 4.4, 4.4, 4.2])
    D.RT("SENS", "토크 센서 요구사항", [
        ("EPS 제어기는 TAS 두 채널을 1ms 주기로 샘플링하고 두 채널의 합(T1+T2)이 0.5 N·m를 초과하는 상태가 5ms 지속되면 센서 불일치 고장으로 판단해야 한다.", "D", "HIL (센서 고장 주입)"),
        ("EPS 제어기는 SENT 메시지의 CRC 오류, 상태 니블 오류, 펄스 폭 이상을 메시지 단위로 검출해야 한다.", "D", "HIL"),
        ("SENT 메시지가 연속 3회 무효이면 해당 채널을 고장으로 판단해야 한다.", "D", "HIL"),
        ("한 채널만 고장인 경우 EPS 제어기는 남은 채널로 보조 토크를 50%로 제한하여 최소 10초 이상 보조를 유지한 후 안전 상태로 천이해야 한다.", "D", "HIL + 차량"),
        ("두 채널이 모두 고장이면 EPS 제어기는 FTTI 20ms 이내에 보조 토크를 0으로 제한해야 한다.", "D", "HIL (고장 주입)"),
        ("EPS 제어기는 TAS 채널별 전원을 독립 감시하고 4.5V 미만 또는 5.5V 초과를 10ms 이내에 검출해야 한다.", "B", "벤치"),
        ("토크 신호의 영점 오프셋은 EOL에서 학습하고 ±0.3 N·m 범위를 벗어나면 학습을 거부해야 한다.", "QM", "EOL 시험")])
    D.h("5.2 모터 위치 센서", 2)
    D.R("SENS", "EPS 제어기는 모터 회전자 위치를 GMR 센서(SPI, 14bit)와 홀 센서 3개로 이중 측정해야 한다.", "벤치", "D")
    D.R("SENS", "GMR 센서와 홀 센서로 계산한 전기각의 차이가 30° 이상 2ms 지속되면 위치 센서 고장으로 판단해야 한다.", "HIL (고장 주입)", "D")
    D.R("SENS", "위치 센서 신호의 갱신 주기는 100µs 이하여야 하며, 모터 최고 회전수 6,000 rpm에서 전기각 오차는 ±5° 이내여야 한다.", "벤치 (다이나모)")
    D.R("SENS", "GMR 센서 고장 시 EPS 제어기는 홀 센서 기반 6-step 제어로 전환하여 보조 토크를 30%로 제한하고 경고등을 점등해야 한다.", "HIL + 차량", "D")
    D.h("5.3 조향각", 2)
    D.R("SENS", "EPS 제어기는 TAS 각도 신호와 모터 위치 적산값을 융합하여 조향각을 0.1° 분해능, ±1.5° 정확도로 산출해야 한다.", "차량 시험")
    D.R("SENS", "EPS 제어기는 산출한 조향각과 조향 속도를 Chassis CAN-FD로 10ms 주기로 송신해야 하며, 조향각 신호는 E2E Profile 5로 보호해야 한다.", "CANoe", "D")
    D.R("SENS", "조향각 신호의 유효성(Valid/Invalid/Not calibrated) 상태를 함께 송신해야 한다.", "CANoe")
    D.R("SENS", "EPS 제어기는 조향각 영점 및 엔드스톱 학습 루틴을 UDS 0x31 서비스로 제공해야 한다.", "진단기")
    D.R("SENS", "조향각 학습이 완료되지 않은 상태에서는 조향각 신호를 'Not calibrated'로 송신하고 ADAS 기능을 NOT_AVAILABLE로 보고해야 한다.", "CANoe")
    D.R("SENS", "외부 SAS가 없는 사양에서 EPS 제어기는 조향각 신호를 ESC가 요구하는 정확도(±2.5°)로 제공해야 한다.", "차량 시험", "C")
    D.br()

    # 6 ---------------------------------------------------------------- 통신
    D.h("6 차량 통신")
    D.p("EPS 제어기는 Chassis CAN-FD와 ADAS Private CAN-FD에 연결된다. 그림 8은 네트워크 토폴로지이다. 메시지·신호의 상세 정의는 AMS-2100 DBC를 따른다.")
    D.fig("network", "C3 샤시 네트워크 토폴로지 (EPS 관련)")
    D.table("EPS 송신 메시지", [["메시지", "ID", "주기", "DLC", "E2E", "주요 신호"], ["EPS_Status_01", "0x2B0", "10 ms", "16", "Profile 5", "EPS_Mode, EPS_Warn, EPS_AssistLim"],
                              ["EPS_Steer_01", "0x2B1", "10 ms", "16", "Profile 5", "StrAngle, StrAngleSpd, StrAngleVld"], ["EPS_Torque_01", "0x2B2", "10 ms", "16", "Profile 5", "DrvTq, MotTq, DrvTqVld"],
                              ["EPS_ADAS_Sts", "0x1C0", "10 ms", "16", "Profile 7", "AdasAvail, AdasRejReason, OverlaySat"], ["EPS_Diag_Resp", "0x7AC", "이벤트", "64", "—", "UDS 응답"]], widths=[3.2, 1.6, 1.6, 1.2, 2, 6.4])
    D.table("EPS 수신 메시지", [["메시지", "송신", "주기", "타임아웃", "사용 신호", "타임아웃 시 대체값"], ["ESC_VehSpd", "ESC", "10 ms", "100 ms", "VehSpd, VehSpdVld", "30 km/h"],
                              ["ENG_State", "GW", "20 ms", "200 ms", "EngRun, ReadyOn", "직전값 유지 (2 s)"], ["BCM_DrvMode", "GW", "100 ms", "500 ms", "DrvMode", "NORMAL"],
                              ["ADAS_TqReq", "ADAS DCU", "10 ms", "50 ms", "TqReq, TqReqAct, AngReq", "오버레이 해제"], ["GW_Time", "GW", "1000 ms", "5 s", "UTC 시간", "내부 카운터"]], widths=[3, 2, 1.6, 1.8, 4, 3.6])
    D.table("EPS_Status_01 신호 상세", [["신호", "시작 비트", "길이", "범위", "단위", "설명"], ["EPS_Mode", "16", "3", "0~5", "—", "0 OFF, 1 INIT, 2 READY, 3 ASSIST, 4 LIMITED, 5 SAFE"],
                                       ["EPS_WarnLamp", "19", "2", "0~2", "—", "0 없음, 1 황색, 2 적색"], ["EPS_AssistLim", "24", "8", "0~100", "%", "현재 허용 보조 토크"], ["EPS_ThermLim", "32", "1", "0/1", "—", "열 디레이팅 중"],
                                       ["EPS_VoltLim", "33", "1", "0/1", "—", "전압 디레이팅 중"], ["EPS_PwrStgTemp", "40", "8", "-40~215", "°C", "추정 온도 (오프셋 -40)"], ["EPS_FaultCode", "48", "16", "0~65535", "—", "최근 고장 코드"],
                                       ["EPS_Status_CRC", "0", "16", "—", "—", "E2E Profile 5 CRC"], ["EPS_Status_Cnt", "64", "8", "0~255", "—", "Alive Counter"]], widths=[3.4, 1.8, 1.4, 2.2, 1.4, 5.8])
    D.table("ADAS_TqReq 신호 상세", [["신호", "시작 비트", "길이", "범위", "단위", "설명"], ["ADAS_TqReq", "16", "12", "-5.12~5.11", "N·m", "오버레이 토크 요청 (0.0025 N·m/bit)"],
                                    ["ADAS_TqReqAct", "28", "1", "0/1", "—", "토크 요청 활성"], ["ADAS_AngReq", "32", "16", "-780~780", "deg", "목표 조향각 (0.1 deg/bit)"], ["ADAS_AngReqAct", "48", "1", "0/1", "—", "각도 제어 요청 활성"],
                                    ["ADAS_Func", "49", "3", "0~4", "—", "0 없음, 1 LKA, 2 LFA, 3 PA, 4 MRM"], ["ADAS_Freshness", "56", "32", "—", "—", "SecOC 신선도 값"], ["ADAS_MAC", "88", "64", "—", "—", "SecOC MAC (절단 64bit)"],
                                    ["ADAS_CRC / Cnt", "0 / 152", "16 / 8", "—", "—", "E2E Profile 7"]], widths=[3.4, 1.8, 1.4, 2.4, 1.4, 5.6])
    D.RT("COM", "통신 요구사항", [
        ("EPS 제어기는 CAN-FD 공칭 500kbps, 데이터 2Mbps로 통신해야 하며 샘플 포인트는 공칭 80%, 데이터 75%여야 한다.", "QM", "CANoe + 오실로스코프"),
        ("EPS 제어기는 EPS 송신 메시지 표의 메시지를 지정 주기 ±5% 이내로 송신해야 한다.", "QM", "CANoe"),
        ("EPS 제어기는 EPS 수신 메시지 표의 메시지가 타임아웃 시간 동안 수신되지 않으면 대체값을 사용하고 해당 DTC를 저장해야 한다.", "B", "CANoe (타임아웃 주입)"),
        ("EPS 제어기는 ASIL 신호를 포함하는 송신 메시지에 E2E Profile 5(Chassis) 또는 Profile 7(ADAS)을 적용해야 한다.", "D", "CANoe"),
        ("EPS 제어기는 수신 E2E 메시지의 CRC 오류, Alive Counter 반복·누락을 메시지 단위로 검출해야 한다.", "D", "CANoe (E2E 오류 주입)"),
        ("Bus-off 발생 시 EPS 제어기는 100ms 후 재접속을 시도하고, 5회 연속 Bus-off 시 1초 간격으로 재시도해야 한다.", "QM", "CANoe"),
        ("EPS 제어기는 AUTOSAR 네트워크 관리(NM)를 지원해야 하며 NM 메시지 주기는 200ms여야 한다.", "QM", "CANoe")])
    D.br()

    # 7 ---------------------------------------------------------------- 진단
    D.h("7 진단")
    D.p("EPS 제어기는 ISO 14229-1 UDS를 CAN-FD 상에서 지원해야 한다. 지원 서비스와 세션 조건은 아래 표와 같다.")
    D.table("지원 UDS 서비스", [["SID", "서비스", "기본", "확장", "프로그래밍", "보안 접근"], ["0x10", "DiagnosticSessionControl", "O", "O", "O", "—"], ["0x11", "ECUReset", "O", "O", "O", "—"],
                              ["0x14", "ClearDiagnosticInformation", "O", "O", "—", "—"], ["0x19", "ReadDTCInformation", "O", "O", "—", "—"], ["0x22", "ReadDataByIdentifier", "O", "O", "O", "—"],
                              ["0x27", "SecurityAccess", "—", "O", "O", "—"], ["0x28", "CommunicationControl", "—", "O", "O", "—"], ["0x2E", "WriteDataByIdentifier", "—", "O", "—", "필요"],
                              ["0x31", "RoutineControl", "—", "O", "O", "필요"], ["0x34/36/37", "다운로드", "—", "—", "O", "필요"], ["0x3E", "TesterPresent", "O", "O", "O", "—"], ["0x85", "ControlDTCSetting", "—", "O", "O", "—"]],
            widths=[2, 5, 1.6, 1.6, 2.4, 2.4])
    D.table("주요 DID", [["DID", "이름", "길이", "접근", "설명"], ["0xF190", "VIN", "17", "R", "차대번호"], ["0xF187", "부품번호", "10", "R", "OEM 부품번호"], ["0xF195", "SW 버전", "8", "R", "어플리케이션 SW"],
                        ["0xF18C", "ECU 일련번호", "16", "R", "EOL 기록"], ["0xD100", "차량 변형 코드", "1", "R/W", "보안 접근 필요"], ["0xD110", "조향각 학습값", "8", "R", "영점·엔드스톱"],
                        ["0xD120", "쏠림 보상 학습값", "4", "R", "REQ-ASSIST-015"], ["0xD130", "파워 스테이지 온도", "2", "R", "추정 온도 °C"], ["0xD140", "누적 보조 시간", "4", "R", "시간 단위"]], widths=[2, 4, 1.4, 1.6, 7])
    dtcs = [["DTC", "설명", "검출 조건", "확정 시간", "반응", "경고등"],
            ["C1A01", "TAS 채널 1 고장", "SENT 3회 연속 무효", "3 ms", "50% 보조 유지 후 안전 상태", "황색"], ["C1A02", "TAS 채널 2 고장", "SENT 3회 연속 무효", "3 ms", "50% 보조 유지 후 안전 상태", "황색"],
            ["C1A03", "TAS 채널 불일치", "|T1+T2| > 0.5 N·m, 5 ms", "5 ms", "안전 상태", "적색"], ["C1A04", "TAS 전원 이상", "4.5V 미만 / 5.5V 초과", "10 ms", "해당 채널 고장 처리", "황색"],
            ["C1A10", "변형 코딩 오류", "코딩값 무효", "즉시", "Base 파라미터", "—"], ["C1A20", "모터 위치 센서 불일치", "전기각 차 > 30°, 2 ms", "2 ms", "6-step 30%", "황색"],
            ["C1A21", "GMR 센서 통신 고장", "SPI CRC 3회 연속", "1 ms", "6-step 30%", "황색"], ["C1A30", "상 전류 측정 고장", "Iu+Iv+Iw ≠ 0 (> 5 A)", "2 ms", "안전 상태", "적색"],
            ["C1A31", "과전류", "상 전류 > 120 A", "10 µs (HW)", "게이트 차단", "적색"], ["C1A32", "MOSFET 단락", "자기 진단 / VDS 감시", "INIT / 10 µs", "상 릴레이 개방", "적색"],
            ["C1A33", "상 릴레이 고장", "INIT 자기 진단 실패", "INIT", "보조 금지", "적색"], ["C1A40", "파워 스테이지 과열", "추정 온도 > 150°C", "100 ms", "40% 제한", "황색"],
            ["C1A41", "온도 센서 고장", "NTC 단선/단락", "100 ms", "50% 제한", "황색"], ["C1A50", "KL30 저전압", "7 V 미만 500 ms", "500 ms", "보조 중지", "황색"],
            ["C1A51", "KL30 과전압", "18 V 초과 500 ms", "500 ms", "보조 중지", "황색"], ["C1A60", "MCU 내부 고장", "Lockstep / SMU 알람", "≤ 1 ms", "안전 상태", "적색"],
            ["C1A61", "와치독 고장", "PMIC 윈도우 위반", "≤ 20 ms", "PMIC 차단", "적색"], ["C1A62", "메모리 고장", "ECC 이중 오류 / CRC", "≤ 10 ms", "안전 상태", "적색"],
            ["C1A70", "조향각 미학습", "학습값 없음", "IG ON", "ADAS 비활성", "—"], ["U0100", "ENG 통신 두절", "ENG_State 200 ms 미수신", "200 ms", "직전값 2 s", "—"],
            ["U0122", "ESC 통신 두절", "ESC_VehSpd 100 ms 미수신", "100 ms", "30 km/h 대체", "황색"], ["U0423", "ADAS 요청 무효", "타임아웃 / E2E 3회", "50 ms", "오버레이 해제", "—"],
            ["U1000", "Chassis CAN Bus-off", "Bus-off 5회 연속", "—", "재접속", "—"], ["U1100", "SecOC 검증 실패", "MAC 불일치 3회", "—", "메시지 폐기", "—"]]
    D.table("DTC 목록", dtcs, widths=[1.6, 3.4, 3.8, 1.8, 3.6, 1.4])
    D.RT("DIAG", "진단 요구사항", [
        ("EPS 제어기는 DTC 목록 표의 DTC를 지정 검출 조건과 확정 시간에 따라 검출하고 ISO 14229 DTC 상태 바이트를 관리해야 한다.", "QM", "진단기 + HIL"),
        ("EPS 제어기는 DTC 확정 시 스냅숏(차속, KL30 전압, 조향각, 운전자 토크, 모터 전류, 파워 스테이지 온도, 운용 상태)을 저장해야 한다.", "QM", "진단기"),
        ("EPS 제어기는 최소 20개의 DTC와 스냅숏을 NvM에 저장할 수 있어야 하며, 공간 부족 시 우선순위가 낮은 항목부터 덮어써야 한다.", "QM", "진단기"),
        ("DTC 에이징은 40 운전 사이클 동안 재발생이 없으면 저장 DTC를 삭제하는 방식으로 수행해야 한다.", "QM", "HIL"),
        ("EPS 제어기는 확장 세션에서 2초 동안 TesterPresent가 없으면 기본 세션으로 복귀해야 한다.", "QM", "진단기"),
        ("주행 중(차속 5 km/h 이상)에는 0x2E, 0x31, 0x34 서비스 요청을 NRC 0x22(conditionsNotCorrect)로 거부해야 한다.", "B", "진단기"),
        ("경고등 요청은 적색(EPS 기능 상실)과 황색(성능 저하) 두 단계로 클러스터에 송신해야 한다.", "B", "CANoe")])
    D.br()

    # 8 ---------------------------------------------------------------- 기능 안전
    D.h("8 기능 안전")
    D.p("본 절의 안전 목표는 HARA-EPS-C3(참조 [12])에서 도출되었다. 공급사는 ISO 26262에 따라 기능 안전 개념(FSC)과 기술 안전 개념(TSC)을 수립하고, 안전 요구사항을 하드웨어·소프트웨어로 할당해야 한다.")
    D.table("안전 목표", [["ID", "안전 목표", "ASIL", "안전 상태", "FTTI"], ["SG-01", "의도하지 않은 조향 토크(자기 조향)를 방지한다", "D", "보조 토크 0 (상 차단)", "20 ms"],
                         ["SG-02", "갑작스러운 보조 상실을 방지한다", "B", "보조 유지 또는 1 s 램프다운", "100 ms"], ["SG-03", "조향 고착(Lock)을 방지한다", "D", "모터 상 개방 (프리휠)", "50 ms"],
                         ["SG-04", "ADAS 오버레이 토크의 과도 출력을 방지한다", "D", "오버레이 해제", "20 ms"], ["SG-05", "잘못된 조향각 신호 송신을 방지한다", "C", "신호 Invalid 송신", "50 ms"]], widths=[1.6, 6.8, 1.2, 4, 1.6])
    D.p("그림 9는 SG-01의 시간 예산이다. 고장 검출 시간(FDTI)과 반응 시간(FRTI)의 합은 FTTI보다 작아야 하며, 공급사는 설계 여유를 문서로 입증해야 한다.")
    D.fig("ftti", "SG-01 시간 예산 (FTTI = FDTI + FRTI + 여유)")
    D.RT("SAFE", "기능 안전 요구사항", [
        ("EPS 제어기는 운전자 토크 방향과 반대이거나 운전자 토크 없이 1.5 N·m를 초과하는 모터 토크가 10ms 이상 출력되는 것을 검출하고 FTTI 20ms 이내에 보조 토크를 0으로 해야 한다.", "D", "HIL (고장 주입)"),
        ("EPS 제어기는 토크 산출 경로를 독립된 감시 경로(모니터링 코어 또는 독립 감시 SW)로 검증해야 한다.", "D", "설계 리뷰 + HIL"),
        ("EPS 제어기는 MCU 코어 Lockstep, ECC, 클럭 감시, 전압 감시를 안전 메커니즘으로 사용해야 한다.", "D", "설계 리뷰 + 고장 주입"),
        ("EPS 제어기는 PMIC 윈도우 와치독을 사용해야 하며, 와치독 위반 시 SW와 독립된 하드웨어 경로로 게이트 드라이버를 비활성화해야 한다.", "D", "벤치 (고장 주입)"),
        ("EPS 제어기는 모터 상 차단 수단(상 릴레이 또는 MOSFET 스위치)을 갖추어야 하며, 조향 고착 위험 고장 시 50ms 이내에 상을 개방해야 한다.", "D", "벤치"),
        ("상 차단 수단의 동작은 매 INIT 시 자기 진단으로 확인해야 하며, 진단 실패 시 보조를 금지해야 한다.", "D", "HIL + 벤치"),
        ("EPS 제어기는 상 전류의 합(Iu+Iv+Iw)을 감시하여 5A 이상 불일치가 2ms 지속되면 전류 측정 고장으로 판단해야 한다.", "D", "HIL"),
        ("상 전류가 120A를 초과하면 하드웨어 비교기로 10µs 이내에 게이트를 차단해야 한다 (SW 개입 없음).", "D", "벤치 (단락 시험)"),
        ("안전 관련 파라미터와 캘리브레이션 데이터는 CRC로 보호하고 매 INIT 및 1초 주기로 검증해야 한다.", "D", "단위 시험 + HIL"),
        ("ASIL 소프트웨어는 QM 소프트웨어로부터 메모리 보호(MPU)와 타이밍 보호로 간섭 없음(FFI)을 보장해야 한다.", "D", "설계 리뷰 + 고장 주입"),
        ("EPS 제어기는 단일점 고장 지표(SPFM) 99% 이상, 잠재 고장 지표(LFM) 90% 이상, PMHF 10 FIT 미만을 달성해야 한다.", "D", "FMEDA"),
        ("안전 상태 진입 시 EPS 제어기는 적색 경고등을 점등하고 안전 상태를 전원 재인가 전까지 유지해야 한다.", "D", "HIL")])
    D.table("안전 메커니즘 할당", [["안전 메커니즘", "대상 고장", "검출 시간", "반응", "관련 SG", "구현"], ["TAS 이중 채널 비교", "토크 센서 드리프트·고착", "5 ms", "50% 보조 / 안전 상태", "SG-01, SG-02", "SW"],
                                   ["SENT CRC·상태 감시", "센서 통신 오류", "3 ms", "채널 고장 처리", "SG-01", "SW"], ["모터 위치 이중 측정", "위치 센서 고장", "2 ms", "6-step 30%", "SG-01, SG-03", "SW"],
                                   ["상 전류 합 감시", "전류 측정 고장", "2 ms", "안전 상태", "SG-01", "SW"], ["토크 독립 감시 경로", "토크 산출 오류", "10 ms", "보조 0", "SG-01, SG-04", "SW (모니터 코어)"],
                                   ["하드웨어 과전류 비교기", "MOSFET 단락, 과전류", "10 µs", "게이트 차단", "SG-01", "HW"], ["상 차단 릴레이 자기 진단", "릴레이 고착", "INIT", "보조 금지", "SG-03", "HW + SW"],
                                   ["Lockstep / SMU", "MCU 연산 오류", "≤ 1 ms", "안전 상태", "SG-01, SG-03", "HW"], ["PMIC 윈도우 와치독", "SW 실행 정지", "≤ 20 ms", "게이트 비활성", "SG-01, SG-03", "HW"],
                                   ["E2E 보호 (수신)", "ADAS 요청 손상", "30 ms", "오버레이 해제", "SG-04", "SW"], ["E2E 보호 (송신)", "조향각 신호 손상", "수신측", "수신측 무효 처리", "SG-05", "SW"],
                                   ["캘리브레이션 CRC", "파라미터 손상", "1 s", "안전 상태", "SG-01", "SW"], ["MPU / 타이밍 보호", "QM → ASIL 간섭", "즉시", "안전 상태", "전체", "HW + SW"]],
            widths=[3.6, 3.4, 1.8, 2.8, 2.2, 2.2])
    D.p("다음 표는 운용 상태별 대표 고장에 대한 반응 매트릭스이다. 공급사는 모든 DTC에 대해 동일한 형식의 반응 정의를 하드웨어·소프트웨어 안전 요구사항으로 구체화해야 한다.")
    D.table("고장 반응 매트릭스", [["고장", "READY", "ASSIST", "ADAS 활성", "자동 주차", "경고등", "복귀 조건"],
        ["TAS 단일 채널", "보조 금지", "50% 10 s 후 램프다운", "오버레이 해제", "종료", "황색", "IG 재시동"], ["TAS 이중 채널", "보조 금지", "20 ms 내 보조 0", "오버레이 해제", "종료", "적색", "IG 재시동 + 진단"],
        ["모터 위치 센서", "보조 금지", "6-step 30%", "오버레이 해제", "종료", "황색", "IG 재시동"], ["상 전류 측정", "보조 금지", "안전 상태", "오버레이 해제", "종료", "적색", "IG 재시동 + 진단"],
        ["MOSFET 단락", "보조 금지", "상 개방", "오버레이 해제", "종료", "적색", "수리"], ["과열", "—", "디레이팅", "한계 축소", "유지", "황색 (150°C)", "온도 복귀"],
        ["저전압", "—", "디레이팅 / 중지", "한계 축소", "종료", "황색", "전압 복귀"], ["차속 신호 상실", "—", "30 km/h 맵", "오버레이 해제", "종료", "황색", "신호 복귀"],
        ["ADAS 요청 무효", "—", "영향 없음", "100 ms 램프 해제", "종료", "—", "요청 재수신"], ["MCU 내부 고장", "보조 금지", "안전 상태", "오버레이 해제", "종료", "적색", "IG 재시동 + 진단"],
        ["와치독 위반", "보조 금지", "PMIC 차단", "오버레이 해제", "종료", "적색", "IG 재시동"], ["캘리브레이션 CRC 오류", "보조 금지", "안전 상태", "—", "—", "적색", "재프로그래밍"]],
        widths=[2.8, 1.8, 2.8, 2.4, 1.6, 1.8, 2.8])
    D.h("8.1 안전 상태 진입 방식", 2)
    D.p("보조 상실 자체가 위험(SG-02)이므로, 단일 채널 고장처럼 보조 유지가 안전한 경우에는 성능 저하 모드를 우선 적용하고 즉시 차단은 SG-01/SG-03 위반 위험이 있을 때만 사용한다.")
    D.R("SAFE", "SG-01 또는 SG-03 위반 위험이 없는 고장에서는 보조 토크를 1초 이상의 램프로 감소시켜야 하며 즉시 차단을 사용하지 않아야 한다.", "HIL", "B")
    D.R("SAFE", "성능 저하 모드에서 보조 토크는 정상 대비 최소 30% 이상을 유지해야 한다.", "HIL + 차량", "B")
    D.R("SAFE", "EPS 제어기는 안전 상태 진입 사유를 고장 코드와 함께 NvM에 기록하고 Chassis CAN-FD 상태 신호(EPS_Mode=SAFE)로 송신해야 한다.", "CANoe", "B")
    D.br()

    # 9 ---------------------------------------------------------------- 열 관리
    D.h("9 열 관리")
    D.p("파워 스테이지 온도는 NTC 측정값과 전류 기반 열 모델로 추정한다. 그림 10은 추정 온도에 따른 전류 디레이팅 요구사항이다.")
    D.fig("thermal", "파워 스테이지 추정 온도에 따른 전류 디레이팅")
    D.RT("THERM", "열 관리 요구사항", [
        ("EPS 제어기는 파워 스테이지 온도를 NTC 측정값과 열 모델로 추정해야 하며 추정 오차는 ±5°C 이내여야 한다.", "QM", "열전대 측정"),
        ("EPS 제어기는 추정 온도 110°C부터 150°C까지 모터 전류 한계를 100%에서 40%로 선형 감소시켜야 한다.", "B", "벤치 + HIL"),
        ("디레이팅 중 전류 한계 변화율은 5%/s를 넘지 않아야 한다.", "B", "HIL"),
        ("추정 온도가 100°C 미만으로 내려가면 전류 한계를 2%/s로 복귀시켜야 한다.", "QM", "HIL"),
        ("NTC 센서가 단선 또는 단락되면 열 모델 단독으로 온도를 추정하고 전류 한계를 50%로 제한해야 한다.", "B", "HIL (고장 주입)"),
        ("IG OFF 시 마지막 추정 온도와 시각을 저장하여 재시동 시 냉각 모델로 초기 온도를 계산해야 한다.", "QM", "HIL")])
    D.br()

    # 10 ---------------------------------------------------------------- 보안
    D.h("10 사이버 보안")
    D.p("EPS는 조향에 직접 영향을 주므로 AMS-3100(ISO/SAE 21434 기반)의 CAL 4 대상이다. 공급사는 TARA 결과를 기반으로 보안 요구사항을 구현하고 침투 시험 결과를 제출해야 한다.")
    D.RT("SEC", "사이버 보안 요구사항", [
        ("EPS 제어기는 ADAS_TqReq 메시지에 SecOC(AES-128 CMAC, 64bit MAC 절단, 신선도 값 포함)를 적용해 검증해야 한다.", "QM", "CANoe + 침투 시험"),
        ("SecOC 검증이 3회 연속 실패하면 해당 메시지를 폐기하고 DTC U1100을 저장해야 한다.", "QM", "CANoe"),
        ("EPS 제어기는 HSM 기반 보안 부팅을 수행하여 부트로더와 어플리케이션의 서명을 검증해야 한다.", "QM", "보안 시험"),
        ("UDS SecurityAccess(0x27)는 레벨별 비대칭 키 기반 Challenge-Response를 사용해야 하며 3회 실패 시 10초간 잠가야 한다.", "QM", "진단기"),
        ("디버그 인터페이스(JTAG/DAP)는 양산 상태에서 영구 잠금되어야 하며, 해제는 OEM 인증 절차로만 가능해야 한다.", "QM", "보안 시험"),
        ("암호 키는 HSM 보안 영역에 저장해야 하며 평문으로 외부에 노출되지 않아야 한다.", "QM", "보안 감사"),
        ("EPS 제어기는 보안 이벤트(인증 실패, 서명 오류, 잠금)를 최소 50건 로그로 저장하고 진단으로 읽을 수 있어야 한다.", "QM", "진단기")])
    D.h("11 SW 업데이트 및 메모리")
    D.R("UPD", "EPS 제어기는 UDS 기반 재프로그래밍(0x34/0x36/0x37)과 OTA 업데이트를 지원해야 한다.", "진단기 + OTA 시험")
    D.R("UPD", "EPS 제어기는 A/B 이중 뱅크로 SW를 저장하여 업데이트 실패 시 이전 SW로 자동 복귀해야 한다.", "OTA 시험")
    D.R("UPD", "SW 업데이트는 차속 0 km/h, 변속 P, KL30 12.5V 이상 조건에서만 시작해야 하며 업데이트 중 보조 기능은 금지되어야 한다.", "OTA 시험", "B")
    D.R("UPD", "다운로드 이미지는 서명 검증 후에만 활성화해야 하며 서명 검증 실패 시 이미지를 폐기해야 한다.", "보안 시험")
    D.R("UPD", "전체 SW 업데이트 시간은 CAN-FD 2Mbps 기준 120초 이하여야 한다.", "OTA 시험")
    D.R("NVM", "EPS 제어기는 캘리브레이션 데이터(보조 맵, 보상 파라미터)를 어플리케이션 SW와 분리된 영역에 저장하고 별도로 업데이트할 수 있어야 한다.", "진단기")
    D.R("NVM", "NvM 데이터는 이중화 블록으로 저장하고 하나의 블록이 손상되어도 데이터를 복구할 수 있어야 한다.", "HIL (메모리 고장 주입)")
    D.R("NVM", "NvM 쓰기는 IG OFF 후 2초 이내에 완료해야 하며 쓰기 중 전원 차단 시 데이터 일관성을 보장해야 한다.", "벤치 (전원 차단 시험)")
    D.br()

    # 12 ---------------------------------------------------------------- 전기/커넥터
    D.h("12 전기적 인터페이스")
    D.p("EPS 제어기는 전원 커넥터(C1)와 신호 커넥터(C2)를 갖는다. 그림 11과 커넥터 핀 배열 표는 커넥터 핀 정의이다.")
    D.fig("conn", "EPS 제어기 커넥터 배치 (차량 하네스 측에서 본 모습)", width=13)
    pins = [["커넥터", "핀", "신호", "방향", "전압/전류", "비고"], ["C1", "1", "KL30", "IN", "12V, 80A 피크", "6mm² 전선"], [None, "2", "GND (전원)", "—", "80A 피크", "6mm² 전선"],
            ["C2", "1", "KL15", "IN", "12V, 10mA", "IG 신호"], [None, "2", "CAN1_H (Chassis)", "I/O", "CAN-FD", "트위스트"], [None, "3", "CAN1_L (Chassis)", "I/O", "CAN-FD", ""],
            [None, "4", "CAN2_H (ADAS)", "I/O", "CAN-FD", "트위스트"], [None, "5", "CAN2_L (ADAS)", "I/O", "CAN-FD", ""], [None, "6", "TAS_T1_SIG", "IN", "SENT 5V", "실드"],
            [None, "7", "TAS_T2_SIG", "IN", "SENT 5V", "실드"], [None, "8", "TAS_VCC1", "OUT", "5V, 20mA", "채널 1 전원"], [None, "9", "TAS_VCC2", "OUT", "5V, 20mA", "채널 2 전원"],
            [None, "10", "TAS_GND1", "—", "", ""], [None, "11", "TAS_GND2", "—", "", ""], [None, "12", "TAS_ANGLE (Slow ch.)", "IN", "SENT 5V", "멀티턴 각도"],
            [None, "13", "WAKE_IN", "IN", "12V", "예비"], [None, "14", "GND (신호)", "—", "", ""], [None, "15", "NC", "—", "", ""], [None, "16", "NC", "—", "", ""]]
    D.table("커넥터 핀 배열", pins, widths=[1.6, 1, 4.2, 1.4, 3, 4.8], merges=[(1, 0, 2, 0), (3, 0, 18, 0)])
    D.RT("ELEC", "전기적 인터페이스 요구사항", [
        ("EPS 제어기는 TAS 채널별 5V 전원을 독립적으로 공급해야 하며 각 전원은 단락 보호 기능을 가져야 한다.", "B", "벤치"),
        ("TAS 신호 입력은 12V 단락 및 GND 단락에 손상 없이 견뎌야 한다.", "QM", "벤치"),
        ("CAN 트랜시버는 ISO 11898-2:2016 및 CAN-FD 2Mbps를 지원해야 하며 선택적 웨이크업(Partial Networking)을 지원해야 한다.", "QM", "벤치"),
        ("모든 커넥터 핀은 ESD ±8kV(접촉)에 손상되지 않아야 한다.", "QM", "EMC 시험소"),
        ("EPS 제어기의 절연 저항은 500V DC에서 10MΩ 이상이어야 한다.", "QM", "절연 시험")])
    D.h("12.1 하드웨어 부품 요구사항", 2)
    D.p("공급사는 AEC-Q 인증 부품을 사용하고, 주요 부품의 디레이팅 기준을 하드웨어 설계 문서에 명시해야 한다. 아래 요구사항은 OEM이 요구하는 최소 기준이다.")
    D.RT("ELEC", "하드웨어 부품 요구사항", [
        ("EPS 제어기의 모든 능동 부품은 AEC-Q100(반도체) 또는 AEC-Q101(개별 소자) 인증을 받아야 한다.", "QM", "부품 승인 문서"),
        ("MCU는 ASIL D 안전 매뉴얼을 제공하는 Lockstep 코어 제품이어야 하며 동작 온도 등급 1(-40~125°C) 이상이어야 한다.", "D", "설계 리뷰"),
        ("파워 MOSFET의 접합 온도는 최악 조건(주변 85°C, 80A 1초 피크)에서 150°C를 넘지 않아야 한다.", "QM", "열 시뮬레이션 + 열전대 측정"),
        ("전해 콘덴서는 105°C 등급 이상, 설계 수명 15년 동안의 리플 전류 디레이팅 80% 이하로 사용해야 한다.", "QM", "설계 리뷰"),
        ("상 전류 션트 저항은 ±1% 정밀도, 온도 계수 50ppm/°C 이하여야 한다.", "QM", "부품 사양 검토"),
        ("PCB는 6층 이상, 동박 두께 파워층 70µm 이상이어야 하며 IPC-6012 Class 3를 만족해야 한다.", "QM", "PCB 승인 시험"),
        ("파워 스테이지와 제어부는 열적·전기적으로 분리 배치하고 게이트 드라이브 루프 면적을 최소화해야 한다.", "QM", "레이아웃 리뷰"),
        ("하드웨어 안전 메커니즘(과전류 비교기, 와치독 차단 경로)은 MCU 소프트웨어와 독립적으로 동작해야 한다.", "D", "회로 리뷰 + 고장 주입")])
    D.br()

    # 13 ---------------------------------------------------------------- 환경
    D.h("13 환경 및 EMC")
    D.table("환경 시험 조건", [["시험", "조건", "판정 기준", "규격"], ["고온 동작", "+85°C (주변), 1,000 h", "기능 정상", "AMS-1300 4.1"], ["저온 동작", "-40°C, 500 h", "기능 정상", "AMS-1300 4.2"],
                              ["열충격", "-40°C ↔ +125°C, 1,000 cycle", "기능 정상, 외관 이상 없음", "AMS-1300 4.4"], ["고온 고습", "+85°C, 85% RH, 1,000 h", "기능 정상, 절연 10MΩ 이상", "AMS-1300 4.5"],
                              ["진동", "랜덤 27.8 m/s² RMS, 축당 8 h", "기능 정상", "AMS-1300 5.1"], ["기계 충격", "50 g, 11 ms, 축당 10회", "손상 없음", "AMS-1300 5.2"],
                              ["방수·방진", "IP6K9K (컬럼 내 장착 시 IP5K2)", "침수 없음", "ISO 20653"], ["염수 분무", "96 h", "부식 등급 2 이하", "AMS-1300 6.1"]], widths=[3, 5, 4.6, 3.4])
    D.RT("ENV", "환경 요구사항", [
        ("EPS 제어기는 주변 온도 -40°C ~ +85°C 범위에서 모든 기능을 정격 성능으로 수행해야 한다.", "QM", "환경 챔버"),
        ("EPS 제어기는 보관 온도 -40°C ~ +105°C 범위에서 손상되지 않아야 한다.", "QM", "환경 챔버"),
        ("EPS 제어기는 환경 시험 조건 표의 시험 후 기능 및 외관 판정 기준을 만족해야 한다.", "QM", "환경 시험소"),
        ("EPS 제어기는 저온(-40°C) 시동 후 3초 이내에 정격 보조 토크를 출력할 수 있어야 한다.", "QM", "환경 챔버 + 벤치"),
        ("EPS 제어기의 설계 수명은 15년 또는 300,000 km이며 누적 보조 동작 시간 8,000 h를 만족해야 한다.", "QM", "내구 시험")])
    D.RT("ENV", "EMC 요구사항", [
        ("EPS 제어기는 AMS-1200의 방사 방출(RE) 및 전도 방출(CE) 등급 3을 만족해야 한다.", "QM", "EMC 시험소"),
        ("EPS 제어기는 BCI 200mA(1~400MHz)에서 기능 상태 A를 만족해야 한다.", "B", "EMC 시험소"),
        ("EPS 제어기는 ALSE 방사 내성 100V/m(200MHz~3.2GHz)에서 기능 상태 A를 만족해야 한다.", "B", "EMC 시험소"),
        ("EMC 시험 중 보조 토크 변동은 ±0.5 N·m 이내여야 하며 의도하지 않은 조향 토크가 발생하지 않아야 한다.", "D", "EMC 시험소 (토크 모니터링)"),
        ("EPS 제어기는 ESD ±8kV 접촉, ±15kV 기중(동작 중)에서 기능 상태 B 이상을 만족해야 한다.", "QM", "EMC 시험소")])
    D.br()

    # 14 ---------------------------------------------------------------- 성능
    D.h("14 조향 성능 및 NVH")
    D.table("조향감 목표값 (C3-Premium)", [["평가 항목", "조건", "목표", "측정 방법"], ["제자리 조향력", "정차, 엔진 ON, 100 deg/s", "≤ 3.5 N·m", "조향 로봇"],
                                         ["저속 조향력", "20 km/h, 90° 조향", "≤ 2.5 N·m", "조향 로봇"], ["중립 감도", "100 km/h, ±0.1 g", "1.2 ~ 1.8 N·m/g", "Weave 시험"],
                                         ["복원 잔류각", "20 km/h, 180° 후 해제", "≤ 15°", "조향각 측정"], ["토크 리플", "정차 조향 50 deg/s", "≤ 0.15 N·m p-p", "토크 센서"],
                                         ["작동 소음", "정차 조향, 운전석 귀 위치", "≤ 38 dB(A)", "마이크로폰"], ["전기적 소음", "PWM 주파수 대역", "가청 대역 밖 (≥ 18 kHz)", "주파수 분석"]], widths=[3.4, 4.6, 3.6, 4.4])
    D.RT("PERF", "성능 요구사항", [
        ("EPS 시스템은 정차 상태 엔진 ON, 조향 속도 100 deg/s에서 운전자 조향력 3.5 N·m 이하를 달성해야 한다.", "QM", "차량 시험 (조향 로봇)"),
        ("EPS 시스템은 최대 조향 속도 720 deg/s에서 보조 토크가 부족해 조향력이 급증(Catch-up)하지 않아야 한다.", "QM", "차량 시험"),
        ("모터 토크 리플은 정차 조향 50 deg/s에서 0.15 N·m p-p 이하여야 한다.", "QM", "벤치"),
        ("EPS 작동 소음은 운전석 귀 위치에서 38 dB(A) 이하여야 한다.", "QM", "NVH 시험"),
        ("PWM 주파수는 18kHz 이상이어야 하며 가청 소음을 유발하지 않아야 한다.", "QM", "벤치"),
        ("운전자 토크 입력에 대한 보조 토크 응답 지연은 10ms 이하여야 한다.", "QM", "HIL"),
        ("보조 토크 제어의 위상 여유는 45° 이상, 이득 여유는 6dB 이상이어야 한다.", "QM", "주파수 응답 시험")])
    D.br()

    # 15 ---------------------------------------------------------------- 생산·서비스
    D.h("15 생산 및 서비스")
    D.RT("EOL", "생산·서비스 요구사항", [
        ("EPS 제어기는 EOL에서 일련번호, 생산 일자, HW/SW 버전을 기록해야 하며 UDS로 읽을 수 있어야 한다.", "QM", "EOL 시험"),
        ("EPS 제어기는 EOL에서 토크 센서 영점, 모터 위치 오프셋, 조향각 영점을 학습해야 한다.", "QM", "EOL 시험"),
        ("EOL 학습 루틴은 각각 5초 이내에 완료되어야 한다.", "QM", "EOL 시험"),
        ("EPS 제어기는 차량 변형 코딩(DID 0xD100)을 EOL에서 기록할 수 있어야 하며 보안 접근 후에만 변경할 수 있어야 한다.", "QM", "EOL 시험"),
        ("서비스 센터에서 조향각 재학습과 쏠림 보상 초기화를 진단기로 수행할 수 있어야 한다.", "QM", "진단기"),
        ("EPS 제어기는 공급사 출하 검사 결과를 일련번호별로 15년간 보관해야 한다.", "QM", "공정 감사"),
        ("공급사는 양산 불량률을 출하 기준 10 ppm 이하로 유지해야 한다.", "QM", "품질 실적")])

    D.h("15.1 품질 및 신뢰성", 2)
    D.table("신뢰성 목표", [["항목", "목표", "평가 방법"], ["필드 고장률", "≤ 10 FIT (EPS ECU)", "신뢰성 예측 (SN 29500) + 필드 데이터"], ["보증 기간 불량률", "≤ 100 ppm (3년)", "필드 품질 실적"],
                           ["MTBF", "≥ 1.5 × 10⁶ h", "신뢰성 예측"], ["솔더 접합 수명", "열충격 1,000 cycle 후 크랙 없음", "단면 분석"], ["코팅", "컨포멀 코팅, 커버리지 ≥ 95%", "UV 검사"]], widths=[4, 6, 6])
    D.RT("EOL", "품질·신뢰성 요구사항", [
        ("공급사는 EPS 제어기의 신뢰성 예측 결과를 C 샘플 단계에서 제출해야 하며 필드 고장률 목표 10 FIT 이하를 입증해야 한다.", "QM", "납품물 검토"),
        ("공급사는 DFMEA와 PFMEA를 AIAG-VDA FMEA 방식으로 작성하고 AP(Action Priority) H 항목에 대한 조치를 완료해야 한다.", "QM", "FMEA 리뷰"),
        ("공급사는 양산 전 PV(Production Validation) 시험을 양산 공정 부품으로 수행해야 한다.", "QM", "PV 성적서"),
        ("공급사는 필드 불량품 접수 후 8D 보고서 초안을 5 영업일 이내에 제출해야 한다.", "QM", "품질 감사"),
        ("EPS 제어기는 고장 해석을 위해 최근 10회 안전 상태 진입 기록(시각, 고장 코드, 주요 신호)을 비휘발성으로 보관해야 한다.", "QM", "진단기"),
        ("공급사는 생산 라인에서 100% 기능 시험(전원, 통신, 센서, 모터 구동, 안전 메커니즘 동작)을 수행해야 한다.", "QM", "공정 감사")])

    # 16 ---------------------------------------------------------------- 검증
    D.h("16 검증 요구사항")
    D.p("공급사는 각 요구사항의 검증 방법에 따른 검증 계획을 수립하고, ASPICE 검증 공정(SWE.4~6, HWE.3~4, SYS.4~5)별 결과를 제출해야 한다. 다음 표는 OEM이 기대하는 검증 공정 매핑이다.")
    D.table("검증 환경 매핑", [["검증 환경", "주 대상 요구사항", "ASPICE 공정", "제출물"], ["단위 시험 (MC/DC)", "ASIL C/D SW 유닛", "SWE.4", "커버리지 리포트"], ["SW 통합 시험", "SWC 인터페이스, 타이밍", "SWE.5", "통합 시험 보고서"],
                              ["HIL (고장 주입 포함)", "ASSIST, ADAS, SENS, COM, DIAG, SAFE", "SWE.6 / SYS.4", "HIL 보고서 + 파형"], ["벤치 / 오실로스코프", "ELEC, THERM, 하드웨어 안전 메커니즘", "HWE.3 / HWE.4", "측정 보고서"],
                              ["환경·EMC 시험소", "ENV", "HWE.4 / SYS.5", "시험 성적서"], ["차량 시험", "PERF, ASSIST 튜닝, UC-01~08", "SYS.5", "평가 보고서"]], widths=[3.6, 5.8, 2.8, 3.8])
    D.R("SAFE", "공급사는 ASIL C/D 요구사항마다 최소 1개 이상의 고장 주입 시험을 수행하고 반응 시간 측정 파형을 제출해야 한다.", "보고서 검토", "D")
    D.R("SAFE", "공급사는 모든 안전 목표에 대해 FDTI·FRTI 측정 결과가 FTTI 이내임을 입증해야 한다.", "보고서 검토", "D")
    D.p("공급사는 요구사항–설계–시험 간 양방향 추적성 매트릭스를 각 샘플 단계(B/C/D 샘플) 출하 시 제출해야 하며, 변경된 요구사항에 대해서는 영향받는 시험의 재수행 여부를 명시해야 한다.")

    D.h("16.1 납품물 및 샘플 단계", 2)
    D.table("샘플 단계별 납품물", [["단계", "시기", "HW", "SW 기능 범위", "필수 납품물"], ["A 샘플", "2027-02", "기능 시제품", "기본 보조, CAN 통신", "회로도, 초기 FMEA, SW 아키텍처 초안"],
                                 ["B 샘플", "2027-07", "양산 설계 반영", "보조·보상 전체, 진단, ADAS 오버레이", "HW/SW 요구사항, 추적 매트릭스, HIL 보고서"],
                                 ["C 샘플", "2027-12", "양산 공정 시제품", "전체 기능 + 안전 메커니즘", "FMEDA, 안전 사례 초안, 환경·EMC 성적서"],
                                 ["D 샘플 (PPAP)", "2028-04", "양산품", "양산 SW (보안 포함)", "안전 사례, 침투 시험, PPAP 문서 일체"]], widths=[2.2, 1.8, 3, 4.4, 4.6])
    D.RT("EOL", "개발 프로세스 및 납품 요구사항", [
        ("공급사는 Automotive SPICE 4.0 기준 HWE, SWE, SYS, SUP.1/8/9/10, MAN.3 프로세스에서 Capability Level 2 이상을 달성해야 한다.", "QM", "ASPICE 평가"),
        ("공급사는 각 샘플 단계에서 요구사항 대비 구현·검증 상태를 추적성 매트릭스로 제출해야 한다.", "QM", "납품물 검토"),
        ("공급사는 변경된 고객 요구사항에 대해 영향받는 설계·시험 산출물 목록을 10 영업일 이내에 제출해야 한다.", "QM", "변경 관리 감사"),
        ("공급사는 ISO 26262 Part 2에 따른 기능 안전 관리 계획(Safety Plan)과 확인 조치(Confirmation Review) 결과를 제출해야 한다.", "D", "납품물 검토"),
        ("공급사는 SW 배포 시 릴리스 노트, 알려진 결함 목록, 빌드 환경 정보를 함께 제출해야 한다.", "QM", "납품물 검토"),
        ("공급사는 하위 공급사(부품·SW 라이선스)에 대해서도 동등한 기능 안전·보안 요구사항을 전달해야 한다.", "QM", "공급망 감사")])

    D.h("부록 A. 요구사항 변경 절차", 1)
    D.bullets(["OEM 또는 공급사는 변경 요청(CR)을 발행한다.", "공급사는 10 영업일 이내에 영향 분석(일정, 비용, 안전 영향, 영향받는 산출물)을 회신한다.",
               "변경 통제 위원회(CCB)가 승인하면 본 문서를 개정하고 개정 이력을 갱신한다.", "공급사는 추적성 도구에서 영향받는 하위 산출물을 재검토(Suspect 해제)하고 다음 샘플 단계에 반영한다."])
    D.h("부록 B. 공급사 회신 양식 (Compliance Matrix 예)", 1)
    D.p("공급사는 다음 양식으로 모든 요구사항의 준수 여부를 회신한다. 아래는 작성 예이다.")
    D.table("준수 여부 회신 예", [["요구사항 ID", "회신", "공급사 요구사항 ID", "비고"], ["REQ-ASSIST-001", "C", "SYS-ASSIST-0001", ""], ["REQ-ASSIST-005", "C", "SYS-ASSIST-0005, SWE-ASSIST-0012", ""],
                                 ["REQ-ADAS-001", "PC", "SYS-ADAS-0001", "90% 도달 60ms 제안 (대안: 예측 제어 적용 시 50ms)"], ["REQ-SENS-001", "C", "SYS-SENS-0001, HWE-SENS-0003", ""],
                                 ["REQ-SAFE-008", "C", "HWE-SAFE-0002", "비교기 응답 6µs 설계"], ["REQ-UPD-005", "NC", "—", "CAN-FD 2Mbps 기준 150 s 예상, 압축 적용 협의 요청"]], widths=[3.2, 1.4, 5.4, 6])
    D.h("부록 C. 신호 목록 요약", 1)
    D.table("EPS 관련 신호 요약", [["신호", "메시지", "방향", "주기", "ASIL", "사용 요구사항"], ["VehSpd", "ESC_VehSpd", "RX", "10 ms", "B", "REQ-ASSIST-001, 005"], ["EngRun", "ENG_State", "RX", "20 ms", "QM", "REQ-ASSIST-007"],
                                  ["DrvMode", "BCM_DrvMode", "RX", "100 ms", "QM", "REQ-ASSIST-019~021"], ["ADAS_TqReq", "ADAS_TqReq", "RX", "10 ms", "D", "REQ-ADAS-001~008"], ["ADAS_AngReq", "ADAS_TqReq", "RX", "10 ms", "C", "REQ-ADAS-009~014"],
                                  ["StrAngle", "EPS_Steer_01", "TX", "10 ms", "D", "REQ-SENS-014~016"], ["DrvTq", "EPS_Torque_01", "TX", "10 ms", "B", "REQ-SENS-008"], ["EPS_Mode", "EPS_Status_01", "TX", "10 ms", "B", "REQ-SAFE-015"],
                                  ["EPS_WarnLamp", "EPS_Status_01", "TX", "10 ms", "B", "REQ-DIAG-007"], ["AdasAvail", "EPS_ADAS_Sts", "TX", "10 ms", "D", "REQ-ADAS-008"]], widths=[2.8, 3.2, 1.4, 1.6, 1.2, 5.8])
    D.h("부록 D. 기준 보조 토크 맵", 1)
    D.p("다음 표는 C3-Premium 변형의 기준 보조 토크 맵(랙 환산 %)이다. 공급사 튜닝 결과는 이 표 대비 ±15% 이내여야 하며, 차량 평가 후 OEM 승인을 받아 확정한다.")
    tq = [0.4, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
    rows = [["차속 \\ 토크 (N·m)"] + [f"{t:g}" for t in tq]]
    for v, g in [(0, 1.0), (10, 0.92), (30, 0.72), (60, 0.55), (80, 0.45), (120, 0.34), (150, 0.28)]:
        rows.append([f"{v} km/h"] + [f"{min(75*(0.25+0.75*g), g*4.2*max(0,t-0.4)**1.35):.1f}" for t in tq])
    D.table("기준 보조 토크 맵 (C3-Premium, NORMAL 모드)", rows, widths=[2.6] + [1.34] * 10)
    rows2 = [rows[0]]
    for v, g in [(0, 0.9), (10, 0.82), (30, 0.62), (60, 0.46), (80, 0.37), (120, 0.27), (150, 0.22)]:
        rows2.append([f"{v} km/h"] + [f"{min(75*(0.25+0.75*g), g*4.2*max(0,t-0.4)**1.35):.1f}" for t in tq])
    D.table("기준 보조 토크 맵 (C3-Sport, SPORT 모드)", rows2, widths=[2.6] + [1.34] * 10)
    D.h("부록 E. 주요 캘리브레이션 파라미터", 1)
    D.p("다음 파라미터는 차량 튜닝 단계에서 조정 가능해야 하며, 안전 관련 파라미터(★)는 기능 안전팀 승인 없이 변경할 수 없다.")
    D.table("캘리브레이션 파라미터", [["파라미터", "기본값", "범위", "단위", "비고"],
        ["Assist_DeadBand", "0.4", "0.2 ~ 0.8", "N·m", "REQ-ASSIST-005"], ["Assist_RampTime", "200", "100 ~ 500", "ms", "시작/종료 램프"], ["Damp_Gain_Low", "0.004", "0.002 ~ 0.02", "N·m/(deg/s)", "차속 0~30"],
        ["Damp_Gain_High", "0.012", "0.002 ~ 0.02", "N·m/(deg/s)", "차속 80 이상"], ["Return_MaxTq", "2.0", "0 ~ 2.0", "N·m", "능동 복원"], ["Friction_Comp", "0.5", "0 ~ 0.8", "N·m", "마찰 보상"],
        ["Pull_Comp_Max", "1.0", "0 ~ 1.0", "N·m", "쏠림 보상"], ["EndStop_Zone", "20", "10 ~ 30", "deg", "엔드스톱 보호 구간"], ["Therm_Derate_Start", "110", "100 ~ 120", "°C", "★ 디레이팅 시작"],
        ["Therm_Derate_Min", "40", "30 ~ 60", "%", "★ 최소 전류 한계"], ["LV_Derate_Low", "7.0", "6.5 ~ 8.0", "V", "★ 보조 0% 전압"], ["LV_Derate_High", "10.0", "9.0 ~ 11.0", "V", "★ 보조 100% 전압"],
        ["Adas_TqLimit", "3.0", "1.0 ~ 3.0", "N·m", "★ 오버레이 한계"], ["Adas_TqRate", "10", "5 ~ 10", "N·m/s", "★ 오버레이 변화율"], ["Adas_DrvOverride", "2.5", "1.5 ~ 3.0", "N·m", "★ 운전자 개입 임계"],
        ["Pa_AngleRateMax", "540", "180 ~ 540", "deg/s", "★ 각도 제어 속도"], ["Tas_DiffLimit", "0.5", "0.3 ~ 0.8", "N·m", "★ 채널 비교 임계"], ["Tas_DiffTime", "5", "2 ~ 10", "ms", "★ 채널 비교 시간"],
        ["Haptic_Freq", "35", "30 ~ 40", "Hz", "진동 경고"], ["Haptic_Amp", "0.4", "0.2 ~ 0.6", "N·m", "진동 경고"], ["Vib_Rej_Gain", "0.6", "0 ~ 1.0", "—", "진동 저감"]],
        widths=[4, 2, 3, 2.6, 4.4])
    D.h("부록 F. 미결 사항", 1)
    D.table("미결 사항 (TBD)", [["번호", "항목", "담당", "목표 일자"], ["TBD-01", "C3-Sport 변형의 SPORT 모드 맵 튜닝 목표", "OEM 샤시튜닝팀", "2027-01"],
                               ["TBD-02", "MRM 시 Degraded Assist 유지 시간 확정 (10 s 잠정)", "OEM 기능안전팀", "2026-12"], ["TBD-03", "OTA 업데이트 시간 목표 재검토 (120 s 잠정)", "OEM 커넥티드팀", "2026-12"]], widths=[1.8, 8.4, 3.4, 2.4])
    p = OUT / f"CRS_EPS_ECU_rev{rev}.docx"
    d.save(p)
    print(f"requirements: {D.reqs}, figures: {D.n['fig']}, tables: {D.n['tbl']}")
    return p


def to_pdf(docx: Path) -> Path | None:
    exe = shutil.which("soffice") or shutil.which("libreoffice")
    if not exe:
        return None
    subprocess.run([exe, "--headless", "--convert-to", "pdf", "--outdir", str(docx.parent), str(docx)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=240)
    pdf = docx.with_suffix(".pdf")
    return pdf if pdf.exists() else None


if __name__ == "__main__":
    out = build("1.0")
    print(out)
    pdf = to_pdf(out)
    if pdf:
        print(pdf)
