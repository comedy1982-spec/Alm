"""Generate a ~50 page customer requirements specification (CRS) for an eLSD ECU, AUTOSAR included.

  python samples/make_elsd_crs.py   ->  samples/CRS_eLSD_ECU_rev1.0.docx  (+ .pdf when LibreOffice exists)

eLSD = electronic Limited Slip Differential: a BLDC motor drives a ball-ramp actuator that presses a wet
multi-plate clutch in the rear differential and so builds a locking torque between the rear wheels.
The document covers functions (traction, yaw coordination with ESC, drive modes, launch, clutch control,
thermal / wear models), operating modes, sensors, CAN-FD, UDS, functional safety, a full AUTOSAR Classic
chapter (layers, SWCs, ports, runnables / OS / multicore, BSW configuration, FFI, Dem/FiM mapping, ARXML
and A2L deliverables), security, electrical, environment, performance, production and verification.
Requirements carry native IDs (REQ-<DOM>-NNN), ASIL and verification method. Names are fictional.
"""
from __future__ import annotations

import sys
from io import BytesIO  # noqa: F401
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm

sys.path.insert(0, str(Path(__file__).parent))
import make_eps_crs as base  # noqa: E402  (Doc, figure helpers, PDF conversion)
from make_eps_crs import BLUE, GRAY, GREEN, INK, ORANGE, RED, Doc, _arrow, _box, _png, to_pdf  # noqa: E402

OUT = Path(__file__).parent
DOC_NO = "CRS-LSD-C3-001"
VIOLET = "#6250d6"


# ============================================================================ figures
def fig_context():
    fig, ax = plt.subplots(figsize=(7.6, 3.8)); ax.axis("off"); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    _box(ax, 0.38, 0.38, 0.24, 0.26, "eLSD ECU\n(본 문서 대상)", fc="#E3F4E7", ec=GREEN, fs=10, bold=True)
    for (x, y, t) in [(0.02, 0.78, "ESC\n(휠속·요레이트·개입)"), (0.02, 0.50, "VCU / EMS\n(구동 토크·변속)"), (0.02, 0.22, "통합 주행모드\n제어기 (IDM)"),
                      (0.80, 0.78, "BLDC 액추에이터\n(볼램프)"), (0.80, 0.50, "습식 다판 클러치\n(후륜 차동)"), (0.80, 0.22, "오일 온도 센서\n(NTC)"),
                      (0.40, 0.04, "배터리 KL30 / IG KL15"), (0.40, 0.84, "진단기 · XCP")]:
        _box(ax, x, y, 0.18, 0.13, t)
    for (a, b, l) in [((0.20, 0.84), (0.38, 0.58), "CAN-FD"), ((0.20, 0.56), (0.38, 0.52), "CAN-FD"), ((0.20, 0.28), (0.38, 0.44), "CAN-FD")]:
        _arrow(ax, a, b, l, BLUE, two=True)
    _arrow(ax, (0.62, 0.58), (0.80, 0.84), "3상 U/V/W", ORANGE)
    _arrow(ax, (0.80, 0.80), (0.62, 0.54), "위치 SPI", GREEN)
    _arrow(ax, (0.89, 0.78), (0.89, 0.63), "볼램프 추력", INK)
    _arrow(ax, (0.80, 0.28), (0.62, 0.44), "온도", GREEN)
    _arrow(ax, (0.50, 0.17), (0.50, 0.38), "12V", ORANGE)
    _arrow(ax, (0.50, 0.84), (0.50, 0.64), "UDS / XCP", BLUE, two=True)
    return _png(fig)


def fig_block():
    fig, ax = plt.subplots(figsize=(7.6, 3.4)); ax.axis("off"); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    items = [(0.02, 0.62, "PMIC\n(WDG, 전압 감시)"), (0.02, 0.18, "CAN-FD XCVR\n(PN 지원)"), (0.30, 0.38, "Multicore Lockstep MCU\nCore0 ASIL · Core1 QM"),
             (0.60, 0.62, "3상 게이트 드라이버"), (0.80, 0.62, "MOSFET 브리지\n+ 상 차단 스위치"), (0.80, 0.18, "BLDC 모터\n(40A 피크)"),
             (0.60, 0.18, "위치 센서 I/F\n(TMR SPI + 홀)"), (0.60, 0.00, "션트 x3 · NTC")]
    for x, y, t in items:
        _box(ax, x, y, 0.22 if "MCU" in t else 0.18, 0.24 if "MCU" in t else 0.2, t, fc="#FFF3DC" if "MCU" in t else "#EEF3FC", ec=ORANGE if "MCU" in t else BLUE, fs=8)
    _arrow(ax, (0.20, 0.72), (0.30, 0.56), "VDD", ORANGE); _arrow(ax, (0.20, 0.28), (0.30, 0.44), "CAN", BLUE, two=True)
    _arrow(ax, (0.52, 0.56), (0.60, 0.70), "PWM", ORANGE); _arrow(ax, (0.78, 0.72), (0.80, 0.72)); _arrow(ax, (0.89, 0.62), (0.89, 0.38), "U/V/W", ORANGE)
    _arrow(ax, (0.60, 0.28), (0.52, 0.44), "SPI", GREEN); _arrow(ax, (0.60, 0.08), (0.52, 0.40), "ADC", GREEN); _arrow(ax, (0.80, 0.28), (0.78, 0.28))
    return _png(fig)


def fig_autosar():
    fig, ax = plt.subplots(figsize=(7.6, 4.4)); ax.axis("off"); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    _box(ax, 0.02, 0.80, 0.96, 0.16, "", fc="#E3F4E7", ec=GREEN)
    ax.text(0.04, 0.935, "Application Layer (ASW)", fontsize=8, color=GREEN, weight="bold")
    for k, n in enumerate(["SWC_LsdCoord\n(ASIL C)", "SWC_LockTqCalc\n(ASIL C)", "SWC_ClutchCtrl\n(ASIL C)", "SWC_ThermWear\n(QM)", "SWC_SafetyMon\n(ASIL C)", "SWC_DiagMgr\n(QM)"]):
        _box(ax, 0.04 + k * 0.158, 0.815, 0.145, 0.10, n, fc="white", ec=GREEN, fs=6.8)
    _box(ax, 0.02, 0.70, 0.96, 0.07, "RTE (Runtime Environment) — S/R · C/S · Mode · IOC (core 간)", fc="#EEF1F5", ec=INK, fs=8, bold=True)
    _box(ax, 0.02, 0.36, 0.70, 0.31, "", fc="#EEF3FC", ec=BLUE)
    ax.text(0.04, 0.645, "Basic Software", fontsize=8, color=BLUE, weight="bold")
    svc = ["EcuM · BswM", "Os (멀티코어)", "WdgM", "Dem · FiM", "Dcm", "NvM · Fee", "Com · PduR", "E2E · SecOC", "Csm · CryIf", "Xcp"]
    for k, n in enumerate(svc):
        _box(ax, 0.04 + (k % 5) * 0.136, 0.53 - (k // 5) * 0.075, 0.125, 0.06, n, fc="white", ec=BLUE, fs=6.6)
    _box(ax, 0.04, 0.38, 0.66, 0.055, "ECU Abstraction: CanIf · CanTp · IoHwAb · MemIf · WdgIf", fc="white", ec=BLUE, fs=6.8)
    _box(ax, 0.74, 0.36, 0.24, 0.31, "CDD_MotorCtrl\n(FOC 50 µs,\nASIL C)\n\nCDD_PosSens", fc="#FFF3DC", ec=ORANGE, fs=7.5)
    _box(ax, 0.02, 0.18, 0.96, 0.15, "", fc="#F4F6F9", ec=GRAY)
    ax.text(0.04, 0.305, "MCAL (MCU 공급사)", fontsize=8, color=INK, weight="bold")
    for k, n in enumerate(["Mcu", "Port · Dio", "Adc", "Gtm / Pwm", "Spi", "Can", "Fls", "Wdg", "Gpt", "Icu"]):
        _box(ax, 0.04 + k * 0.094, 0.20, 0.085, 0.06, n, fc="white", ec=GRAY, fs=6.6)
    _box(ax, 0.02, 0.02, 0.96, 0.12, "Microcontroller (Lockstep, HSM, MPU)   ·   PMIC   ·   게이트 드라이버   ·   CAN-FD XCVR", fc="#FCEEED", ec=RED, fs=8)
    return _png(fig)


def fig_swc():
    fig, ax = plt.subplots(figsize=(7.6, 3.0)); ax.axis("off"); ax.set_xlim(0, 1); ax.set_ylim(0.02, 0.86)
    pos = {"Com": (0.02, 0.42), "Coord": (0.24, 0.42), "LockTq": (0.46, 0.66), "Safety": (0.46, 0.14), "Clutch": (0.68, 0.42), "Motor": (0.86, 0.42), "Therm": (0.46, 0.40)}
    lab = {"Com": "BSW Com\n(Rx/Tx 신호)", "Coord": "SWC_LsdCoord\n모드·요청 조정", "LockTq": "SWC_LockTqCalc\n목표 잠금 토크", "Safety": "SWC_SafetyMon\n독립 감시",
           "Clutch": "SWC_ClutchCtrl\n토크→위치", "Motor": "CDD_MotorCtrl\n위치/전류", "Therm": "SWC_ThermWear\n열·마모 모델"}
    for k, (x, y) in pos.items():
        _box(ax, x, y, 0.13 if k != "Motor" else 0.12, 0.16, lab[k], fc="#E3F4E7" if k.startswith(("Coord", "LockTq", "Clutch", "Safety")) else "#EEF3FC", ec=INK, fs=6.8)
    _arrow(ax, (0.15, 0.50), (0.24, 0.50), "VehDyn_*", BLUE, lfs=6)
    _arrow(ax, (0.37, 0.54), (0.46, 0.72), "LsdMode", INK, lfs=6)
    _arrow(ax, (0.59, 0.72), (0.68, 0.54), "TqLockReq", INK, lfs=6)
    _arrow(ax, (0.59, 0.48), (0.68, 0.48), "TqLimTherm", INK, lfs=6)
    _arrow(ax, (0.81, 0.50), (0.86, 0.50), "PosReq", ORANGE, lfs=6)
    _arrow(ax, (0.68, 0.44), (0.59, 0.22), "TqLockAct", GREEN, lfs=6)
    ax.text(0.02, 0.05, "SWC_SafetyMon 은 Core0 ASIL 파티션에서 실행되며 TqLockReq·TqLockAct 를 독립 검증하고 SafeState 모드를 요청한다.", fontsize=7, color=INK)
    return _png(fig)


def fig_lockmap():
    ds = np.linspace(0, 200, 200)
    fig, ax = plt.subplots(figsize=(7.0, 3.4))
    for n, k, c in [("COMFORT", 4.0, BLUE), ("SPORT", 7.0, ORANGE), ("TRACK", 11.0, VIOLET), ("SNOW", 9.0, GREEN)]:
        tq = np.minimum(2500, k * ds ** 1.35)
        ax.plot(ds, tq, lw=2, color=c, label=n)
        ax.text(ds[-1] + 2, tq[-1], n, fontsize=7.5, va="center", color=INK)
    ax.axhline(2500, color=GRAY, ls="--", lw=1); ax.text(4, 2560, "최대 잠금 토크 2,500 N·m", fontsize=7.5)
    ax.set_xlabel("후륜 좌우 회전수 차 Δn (rpm)"); ax.set_ylabel("목표 잠금 토크 (N·m)"); ax.set_xlim(0, 230); ax.set_ylim(0, 2800); ax.grid(alpha=0.25); ax.legend(fontsize=7.5, loc="upper left")
    return _png(fig)


def fig_thermal():
    t = np.linspace(80, 180, 200)
    lim = np.where(t < 130, 100, np.where(t < 165, 100 - (t - 130) * (80 / 35), 20))
    fig, ax = plt.subplots(figsize=(7.0, 3.0))
    ax.plot(t, lim, lw=2.2, color=ORANGE)
    for x, l in [(130, "130°C 제한 시작"), (165, "165°C: 20%")]:
        ax.axvline(x, color=GRAY, ls="--", lw=1); ax.text(x + 1, 104, l, fontsize=7.5)
    ax.set_xlabel("클러치 판 추정 온도 (°C)"); ax.set_ylabel("허용 잠금 토크 (%)"); ax.set_ylim(0, 115); ax.grid(alpha=0.25)
    return _png(fig)


def fig_states():
    fig, ax = plt.subplots(figsize=(7.6, 3.5)); ax.axis("off"); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    st = {"SLEEP": (0.02, 0.42), "INIT\n(자기진단·영점)": (0.20, 0.42), "STANDBY\n(클러치 개방)": (0.40, 0.42), "ACTIVE": (0.62, 0.70), "LIMITED": (0.62, 0.14), "SAFE\n(강제 개방)": (0.84, 0.42)}
    col = ["#EEF1F5", "#EEF3FC", "#EEF3FC", "#E3F4E7", "#FFF3DC", "#FCEEED"]
    for (n, (x, y)), c in zip(st.items(), col):
        _box(ax, x, y, 0.15, 0.16, n, fc=c, ec=INK, fs=7.5, bold=True)
    _arrow(ax, (0.17, 0.50), (0.20, 0.50), "IG ON", INK, lfs=6.5); _arrow(ax, (0.35, 0.50), (0.40, 0.50), "≤ 400ms", INK, lfs=6.5)
    _arrow(ax, (0.55, 0.56), (0.62, 0.74), "Ready + 차속 유효", INK, lfs=6.5)
    _arrow(ax, (0.69, 0.70), (0.69, 0.30), "과열·저전압", ORANGE, lfs=6.5); _arrow(ax, (0.72, 0.30), (0.72, 0.70), "복귀", GREEN, lfs=6.5)
    _arrow(ax, (0.77, 0.76), (0.84, 0.54), "치명 고장", RED, lfs=6.5); _arrow(ax, (0.77, 0.22), (0.84, 0.46), "치명 고장", RED, lfs=6.5)
    ax.text(0.5, 0.02, "SAFE: 모터 역구동으로 볼램프 복귀 + 리턴 스프링 → 클러치 개방 (잠금 토크 < 50 N·m), 경고등 점등", ha="center", fontsize=7.5)
    return _png(fig)


def fig_step():
    t = np.linspace(0, 0.4, 500)
    pos = 1 - np.exp(-t / 0.035)
    tq = np.clip((pos - 0.18) / 0.82, 0, 1) ** 1.2 * 1500
    fig, ax = plt.subplots(2, 1, figsize=(7.0, 3.6), sharex=True, gridspec_kw={"height_ratios": [1, 1.3]})
    ax[0].plot(t * 1000, pos * 100, color=BLUE, lw=2); ax[0].set_ylabel("볼램프 위치 (%)"); ax[0].axhline(18, color=GRAY, ls=":", lw=1); ax[0].text(250, 22, "Kiss point 18%", fontsize=7.5); ax[0].grid(alpha=0.25)
    ax[1].plot(t * 1000, tq, color=ORANGE, lw=2); ax[1].step([0, 2, 400], [0, 1500, 1500], where="post", color=GRAY, ls="--", lw=1.2)
    ax[1].axvline(120, color=GRAY, ls=":", lw=1); ax[1].text(124, 300, "90% 도달 ≤ 120ms", fontsize=7.5)
    ax[1].set_ylabel("잠금 토크 (N·m)"); ax[1].set_xlabel("시간 (ms)"); ax[1].grid(alpha=0.25)
    return _png(fig)


def fig_ftti():
    fig, ax = plt.subplots(figsize=(7.4, 2.6)); ax.set_xlim(-10, 220); ax.set_ylim(0, 4); ax.set_yticks([])
    for i, (n, s, c) in enumerate([("의도치 않은 잠금 발생", 0, RED), ("검출 (FDTI ≤ 50ms)", 40, ORANGE), ("개방 반응 (FRTI ≤ 100ms)", 140, BLUE), ("안전 상태 (잠금 < 50 N·m)", 140, GREEN)]):
        y = 3.3 - i * 0.85; ax.add_patch(plt.Rectangle((s, y - 0.18), 220 - s, 0.36, color=c, alpha=0.35)); ax.text(-9, y, n, va="center", fontsize=7.5)
    ax.annotate("", xy=(200, 0.25), xytext=(0, 0.25), arrowprops=dict(arrowstyle="<->", color=INK)); ax.text(100, 0.35, "FTTI 200ms (SG-01)", ha="center", fontsize=8)
    ax.set_xlabel("시간 (ms)"); ax.grid(alpha=0.2, axis="x")
    return _png(fig)


def fig_kiss():
    x = np.linspace(0, 40, 300)
    tq = np.where(x < 17.5, 0, (x - 17.5) ** 1.6 * 6)
    fig, ax = plt.subplots(figsize=(7.0, 2.9))
    ax.plot(x, tq, lw=2, color=BLUE, label="측정 토크 (학습 주행)")
    ax.plot(x, np.where(x < 19, 0, (x - 19) ** 1.6 * 6), lw=1.6, ls="--", color=ORANGE, label="마모 후 (8만 km)")
    ax.axvline(17.5, color=GRAY, ls=":", lw=1); ax.text(17.8, 300, "Kiss point (신품)", fontsize=7.5)
    ax.axhline(20, color=RED, ls=":", lw=1); ax.text(1, 32, "판정 임계 20 N·m", fontsize=7)
    ax.set_xlabel("볼램프 위치 (%)"); ax.set_ylabel("잠금 토크 (N·m)"); ax.set_ylim(0, 450); ax.legend(fontsize=7.5); ax.grid(alpha=0.25)
    return _png(fig)


def fig_network():
    fig, ax = plt.subplots(figsize=(7.4, 2.6)); ax.axis("off"); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.plot([0.04, 0.96], [0.62, 0.62], color=BLUE, lw=3); ax.text(0.04, 0.68, "Chassis CAN-FD (500k / 2M)", fontsize=8, color=BLUE)
    ax.plot([0.04, 0.96], [0.22, 0.22], color=GREEN, lw=3); ax.text(0.04, 0.28, "Powertrain CAN-FD (500k / 2M)", fontsize=8, color=GREEN)
    for x, t, both in [(0.10, "ESC", False), (0.28, "GW", True), (0.46, "eLSD ECU", True), (0.64, "IDM", False), (0.82, "VCU/EMS", True)]:
        _box(ax, x - 0.07, 0.40, 0.14, 0.12, t, fc="#E3F4E7" if t == "eLSD ECU" else "#EEF3FC")
        ax.plot([x, x], [0.52, 0.62], color=BLUE, lw=1.5)
        if both:
            ax.plot([x, x], [0.22, 0.40], color=GREEN, lw=1.5)
    return _png(fig)


def fig_connector():
    fig, ax = plt.subplots(figsize=(7.0, 2.4)); ax.axis("off"); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    _box(ax, 0.03, 0.12, 0.30, 0.72, "", fc="#F4F6F9", ec=INK); ax.text(0.18, 0.9, "C1 전원 (2핀, 4mm²)", ha="center", fontsize=8)
    for i, n in enumerate(["KL30", "GND"]):
        ax.add_patch(plt.Circle((0.11 + i * 0.14, 0.48), 0.06, fc="white", ec=ORANGE if i == 0 else INK, lw=2)); ax.text(0.11 + i * 0.14, 0.48, str(i + 1), ha="center", va="center", fontsize=9); ax.text(0.11 + i * 0.14, 0.28, n, ha="center", fontsize=7.5)
    _box(ax, 0.40, 0.12, 0.57, 0.72, "", fc="#F4F6F9", ec=INK); ax.text(0.685, 0.9, "C2 신호·모터 (20핀)", ha="center", fontsize=8)
    for k in range(20):
        x = 0.44 + (k % 10) * 0.052; y = 0.6 if k < 10 else 0.32
        ax.add_patch(plt.Circle((x, y), 0.019, fc="white", ec=BLUE if k > 5 else ORANGE, lw=1.2)); ax.text(x, y, str(k + 1), ha="center", va="center", fontsize=6)
    return _png(fig)


base.FIGS.update({"l_context": fig_context, "l_block": fig_block, "l_autosar": fig_autosar, "l_swc": fig_swc, "l_lockmap": fig_lockmap,
                  "l_thermal": fig_thermal, "l_states": fig_states, "l_step": fig_step, "l_ftti": fig_ftti, "l_kiss": fig_kiss,
                  "l_network": fig_network, "l_conn": fig_connector})


# ============================================================================ content
def build(rev: str = "1.0") -> Path:
    D = Doc(rev, doc_no=DOC_NO, product="eLSD (Electronic Limited Slip Differential) ECU"); d = D.d
    d.add_paragraph("eLSD ECU", style="Title")
    d.add_paragraph("전자식 차동제한장치 제어기 고객 요구사양서 (Customer Requirements Specification)").alignment = WD_ALIGN_PARAGRAPH.CENTER
    d.add_paragraph(f"문서번호 {DOC_NO}   ·   개정 {rev}   ·   차량 프로젝트 C3 AWD / C3-Sport (2028 MY)").alignment = WD_ALIGN_PARAGRAPH.CENTER
    d.add_paragraph("발행: ACME Motors 구동·샤시제어개발팀   ·   수신: eLSD 시스템 공급사").alignment = WD_ALIGN_PARAGRAPH.CENTER
    d.add_paragraph()
    D.table("개정 이력", [["개정", "일자", "작성", "변경 내용"], ["0.5", "2026-04-28", "서구동", "RFQ 배포용 초안"],
                         ["0.8", "2026-07-15", "서구동", "AUTOSAR 아키텍처 요구사항(9장) 추가, ESC 협조 인터페이스 확정"],
                         ["1.0", "2026-10-15", "서구동", "SOR 확정판. FTTI 재평가 결과(200ms), 보안·OTA·XCP 요구사항 반영"]], widths=[1.4, 2.4, 2, 10.2])
    D.table("승인", [["역할", "이름", "부서", "일자"], ["작성", "서구동", "구동·샤시제어개발팀", "2026-10-15"], ["검토", "한안전", "기능안전팀", "2026-10-15"],
                    ["검토", "문플랫폼", "SW 플랫폼팀 (AUTOSAR)", "2026-10-15"], ["검토", "오보안", "차량보안팀", "2026-10-15"], ["승인", "강팀장", "구동·샤시제어개발팀", "2026-10-16"]], widths=[2, 3, 5, 3])
    D.p("본 문서는 공급사가 개발하는 eLSD 제어기(ECU)와 그 소프트웨어에 대한 고객 요구사항이다. '해야 한다'는 필수, '하는 것이 바람직하다'는 권고 요구사항이다. 각 요구사항에는 고유 ID와 ASIL 등급(표기가 없으면 QM), OEM이 기대하는 검증 방법을 표기하였다. 공급사는 모든 필수 요구사항에 대해 준수 여부를 회신해야 한다.")
    D.br()
    D.p("목차").runs[0].bold = True
    for line in ["1 개요", "2 시스템 개요 (경계, 차량 변형, 운용 시나리오 UC-01~12)", "3 기능 요구사항 (잠금 토크, ESC 협조, 주행 모드, 런치, 클러치 제어, 열·마모 모델, 서비스 모드, 기능 조정)",
                 "4 운용 모드 및 전원", "5 센서·액추에이터 인터페이스", "6 차량 통신", "7 진단", "8 기능 안전", "9 AUTOSAR 소프트웨어 아키텍처",
                 "10 사이버 보안", "11 SW 업데이트 · 메모리 · 캘리브레이션(XCP)", "12 전기적 인터페이스 및 하드웨어", "13 환경 및 EMC", "14 성능", "15 생산·서비스·품질",
                 "16 검증 및 납품", "부록 A 변경 절차 · B 회신 양식 · C 신호 목록 · D 잠금 토크 맵 · E 캘리브레이션 파라미터 · F 검증 매핑 · G ASPICE 산출물 · H 미결 사항"]:
        q = d.add_paragraph(line); q.paragraph_format.left_indent = Cm(0.6)
    D.br()

    # 1 ---------------------------------------------------------------- 개요
    D.h("1 개요")
    D.h("1.1 목적", 2)
    D.p("본 문서는 ACME Motors C3 AWD 및 C3-Sport 차량의 후륜 차동장치에 적용되는 전자식 차동제한장치(eLSD) 제어기의 고객 요구사항을 정의한다. eLSD 제어기는 BLDC 모터로 볼램프 액추에이터를 구동하여 습식 다판 클러치를 가압하고, 좌우 후륜 사이에 잠금 토크를 발생시켜 견인력·선회 안정성·주행 감성을 향상시킨다.")
    D.p("공급사는 본 문서를 기준으로 시스템 요구사항(SYS.2)과 하드웨어·소프트웨어 요구사항(HWE.1, SWE.1)을 도출하고, 양방향 추적성을 유지해야 한다. 소프트웨어는 AUTOSAR Classic 플랫폼 기반으로 개발하며 9장의 아키텍처 요구사항을 따라야 한다.")
    D.h("1.2 적용 범위", 2)
    D.p("적용 범위는 eLSD ECU 하드웨어(모터 파워 스테이지 포함), AUTOSAR 기반 임베디드 소프트웨어, 액추에이터·센서 인터페이스, 차량 네트워크 인터페이스, 진단, 기능 안전, 사이버 보안, 생산·서비스 요구사항이다. 차동장치·클러치 팩·볼램프의 기계 설계는 별도 기구 사양서(MS-LSD-C3)를 따른다.")
    D.h("1.3 참조 문서", 2)
    D.table("참조 문서", [["번호", "문서", "개정", "비고"], ["[1]", "AMS-1100 전장 부품 전원 품질 규격", "2025", "ACME 사내"], ["[2]", "AMS-1200 EMC 시험 규격", "2025", "ACME 사내"],
                         ["[3]", "AMS-1300 환경·내구 시험 규격", "2024", "ACME 사내"], ["[4]", "AMS-2100 CAN-FD 통신 사양서 (Chassis / Powertrain)", "1.3", "DBC 포함"],
                         ["[5]", "AMS-2200 진단 사양서 (UDS)", "2.0", "CDD / ODX"], ["[6]", "AMS-2400 AUTOSAR 플랫폼 가이드라인", "3.0", "BSW 구성·명명 규칙"],
                         ["[7]", "AMS-3100 사이버 보안 요구사항", "1.1", "ISO/SAE 21434"], ["[8]", "ISO 26262:2018", "2018", "기능 안전"], ["[9]", "AUTOSAR Classic Platform R20-11", "R20-11", "SWS, TPS, EXP"],
                         ["[10]", "AUTOSAR E2E Protocol Specification", "R22-11", "Profile 5/11"], ["[11]", "ASAM MCD-1 XCP / ASAM MCD-2 MC (A2L)", "1.5 / 1.7", "캘리브레이션"],
                         ["[12]", "HARA-LSD-C3 위험 분석 및 리스크 평가", "1.1", "안전 목표 출처"]], widths=[1.3, 8.4, 2, 4])
    D.h("1.4 용어 및 약어", 2)
    D.table("용어 및 약어", [["약어", "정의"], ["ARXML", "AUTOSAR XML 교환 형식"], ["ASW / BSW / RTE", "Application SW / Basic SW / Runtime Environment"], ["A2L", "ASAM MCD-2 MC 캘리브레이션 기술 파일"],
                           ["CDD", "Complex Device Driver"], ["C/S, S/R", "Client/Server, Sender/Receiver 통신"], ["Dem / FiM", "Diagnostic Event Manager / Function Inhibition Manager"],
                           ["ESC", "Electronic Stability Control"], ["FFI", "Freedom from Interference"], ["IDM", "Integrated Drive Mode 제어기"], ["IOC", "Inter-OS-Application Communicator"],
                           ["Kiss point", "클러치 판이 접촉하기 시작하는 볼램프 위치"], ["MCAL", "Microcontroller Abstraction Layer"], ["Δn", "후륜 좌우 회전수 차"],
                           ["SWC", "Software Component"], ["XCP", "Universal Measurement and Calibration Protocol"]], widths=[3.4, 12.6])
    D.h("1.5 요구사항 분류 체계", 2)
    D.table("도메인 코드", [["코드", "내용", "주 관련 공정"], ["LOCK", "잠금 토크 산출·견인 제어", "SYS.2 / SWE.1"], ["YAW", "ESC 협조·요 안정화", "SYS.2 / SWE.1"], ["MODE", "주행 모드·운용 상태·전원", "SYS.2 / SWE.1"],
                           ["CLU", "클러치·액추에이터 제어", "SYS.2 / SWE.1 / HWE.1"], ["THERM", "열·마모 모델", "SWE.1"], ["SENS", "센서 인터페이스", "HWE.1 / SWE.1"], ["COM", "통신", "SWE.1"],
                           ["DIAG", "진단", "SWE.1"], ["SAFE", "기능 안전", "SYS.2 / HWE.1 / SWE.1"], ["AR", "AUTOSAR 아키텍처·BSW", "SWE.1 / SWE.2"], ["SEC", "사이버 보안", "SYS.2 / SWE.1"],
                           ["UPD / NVM", "업데이트·메모리·캘리브레이션", "SWE.1"], ["ELEC / ENV", "전기·환경·EMC", "SYS.2 / HWE.1"], ["PERF", "성능", "SYS.2"], ["EOL", "생산·서비스·품질·개발 프로세스", "SYS.2"]], widths=[2.6, 8, 5.4])
    D.br()

    # 2 ---------------------------------------------------------------- 시스템 개요
    D.h("2 시스템 개요")
    D.h("2.1 시스템 경계", 2)
    D.p("eLSD 제어기는 후륜 차동장치 하우징 근처에 장착되며, BLDC 모터와 위치 센서, 클러치 오일 온도 센서에 직접 연결된다. 차량 측과는 Chassis CAN-FD(ESC, IDM)와 Powertrain CAN-FD(VCU/EMS)로 통신한다. 그림 1은 시스템 경계이다.")
    D.fig("l_context", "eLSD 제어기 시스템 경계 및 외부 인터페이스")
    D.p("그림 2는 OEM이 가정하는 제어기 내부 구성이다. MCU는 ASIL 소프트웨어용 Lockstep 코어와 QM 소프트웨어용 코어를 가진 멀티코어 제품을 가정한다. 공급사는 동등 이상의 안전성을 입증하는 조건으로 다른 구성을 제안할 수 있다.")
    D.fig("l_block", "eLSD 제어기 참고 블록도")
    D.h("2.2 차량 변형", 2)
    D.table("차량 변형별 주요 파라미터", [["변형", "구동", "최대 잠금 토크", "후륜 최대 토크", "주행 모드", "비고"], ["C3 AWD", "AWD (전자식 커플링)", "1,800 N·m", "2,600 N·m", "COMFORT, SPORT, SNOW", "견인 중심"],
                                       ["C3 AWD Off-road", "AWD", "2,200 N·m", "2,900 N·m", "+ OFF-ROAD (MUD/SAND)", "저속 고잠금"], ["C3-Sport", "AWD (후륜 편향)", "2,500 N·m", "3,400 N·m", "+ TRACK, DRIFT", "런치 컨트롤"]], widths=[2.8, 3, 2.4, 2.4, 3.4, 2])
    D.R("MODE", "eLSD 제어기는 EOL에서 코딩된 차량 변형에 따라 잠금 토크 맵, 최대 잠금 토크, 허용 주행 모드를 선택해야 한다.", "EOL 코딩 시험 + HIL")
    D.R("MODE", "변형 코딩 값이 유효하지 않으면 eLSD 제어기는 C3 AWD 파라미터로 동작하고 TRACK·DRIFT 모드를 금지하며 DTC C2A10을 저장해야 한다.", "HIL (코딩 오류 주입)")
    D.h("2.3 운용 시나리오", 2)
    ucs = [("UC-01 미끄러운 노면 출발", "눈길, 한쪽 바퀴 μ 0.1", "운전자가 가속 페달을 50% 밟아 출발한다.", "Δn 증가 후 200ms 이내 잠금 토크 형성, 출발 가능"),
           ("UC-02 고속 선회 안정화", "건조 노면, 120 km/h 선회", "선회 중 가속하여 오버스티어 경향이 생긴다.", "ESC 요청에 따라 잠금 토크 감소, 요 안정성 확보"),
           ("UC-03 ESC 제동 개입", "μ-split 제동", "ESC가 한쪽 바퀴를 제동한다.", "ESC 개입 중 잠금 토크를 요청값 이하로 제한"),
           ("UC-04 런치 컨트롤", "C3-Sport, TRACK, 정차", "런치 모드로 풀가속 출발한다.", "초기 잠금 토크 프리로드, 휠스핀 억제"),
           ("UC-05 트랙 주행 열부하", "서킷 20분 연속 주행", "반복 고잠금 선회를 수행한다.", "클러치 열 모델 기반 단계적 제한, 기능 상실 없음"),
           ("UC-06 고장 시 안전 상태", "임의 주행", "모터 위치 센서가 고장 난다.", "100ms 이내 클러치 개방, 경고등, 개방 상태 유지"),
           ("UC-07 저속 주차 선회", "차속 10 km/h 이하, 최대 조향", "운전자가 주차를 위해 크게 선회한다.", "잠금 토크 50 N·m 이하로 타이어 스크럽 방지"),
           ("UC-08 롤러 다이나모 시험", "서비스 모드, 2륜 롤러", "검사장에서 2륜 롤러 시험을 한다.", "다이나모 모드 진입 시 잠금 금지"),
           ("UC-09 견인", "차량 고장, 후륜 접지 견인", "견인차가 차량을 끈다.", "IG OFF 상태에서 클러치 개방 유지"),
           ("UC-10 Kiss point 재학습", "클러치 교환 후", "정비사가 진단기로 학습 루틴을 실행한다.", "학습 완료 후 정상 잠금 토크 정확도 복귀"),
           ("UC-11 OTA 업데이트", "정차, IG ON, 배터리 12.5V 이상", "게이트웨이가 SW를 업데이트한다.", "업데이트 중 클러치 개방, 실패 시 이전 SW 복귀"),
           ("UC-12 DRIFT 모드", "C3-Sport, 폐쇄 코스, ESC OFF", "운전자가 드리프트 주행을 한다.", "높은 잠금 토크 유지, ESC 완전 해제 확인 시에만 허용")]
    for title, pre, flow, exp in ucs:
        D.table(title, [["항목", "내용"], ["사전 조건", pre], ["시나리오", flow], ["기대 결과", exp]], widths=[3, 13])
    D.br()

    # 3 ---------------------------------------------------------------- 기능
    D.h("3 기능 요구사항")
    D.h("3.1 잠금 토크 산출 (견인 제어)", 2)
    D.p("목표 잠금 토크는 후륜 좌우 회전수 차(Δn), 구동 토크, 차속, 조향각, 주행 모드의 함수로 산출한다. 그림 3은 모드별 기준 Δn–잠금 토크 특성이다.")
    D.fig("l_lockmap", "주행 모드별 기준 잠금 토크 특성 (Δn 기반 피드백 성분)")
    D.R("LOCK", "eLSD 제어기는 Δn 피드백 성분, 구동 토크 피드포워드 성분, 선회 보정 성분의 합으로 목표 잠금 토크를 산출해야 한다.", "HIL + 차량 튜닝")
    D.R("LOCK", "목표 잠금 토크 산출 주기는 5ms 이하여야 한다.", "TRACE32 타이밍")
    D.R("LOCK", "Δn은 ESC 휠속 신호(4륜)로 산출하며 타이어 반경 편차 보정값을 적용해야 한다.", "HIL")
    D.R("LOCK", "Δn이 5 rpm 이하인 불감대에서는 Δn 피드백 성분을 0으로 해야 한다.", "HIL")
    D.R("LOCK", "구동 토크 피드포워드 성분은 후륜 구동 토크의 최대 40%로 제한해야 한다.", "HIL")
    D.R("LOCK", "차속 10 km/h 이하이고 조향각 180° 이상이면 목표 잠금 토크를 50 N·m 이하로 제한해야 한다.", "차량 시험", None, "UC-07 타이어 스크럽")
    D.R("LOCK", "목표 잠금 토크의 변화율은 증가 20,000 N·m/s, 감소 40,000 N·m/s로 제한해야 한다.", "HIL")
    D.R("LOCK", "휠속 신호가 무효이거나 타임아웃이면 eLSD 제어기는 잠금 토크를 300ms 램프로 0까지 감소시키고 DTC U0121을 저장해야 한다.", "HIL (타임아웃 주입)", "C")
    D.h("3.2 ESC 협조 및 요 안정화", 2)
    D.p("ESC는 차량 안정성 제어의 최상위 권한을 가진다. eLSD 제어기는 ESC가 송신하는 잠금 토크 상한(ESC_LsdTqMax)과 개입 상태를 항상 준수해야 한다.")
    D.RT("YAW", "ESC 협조 요구사항", [
        ("eLSD 제어기는 ESC가 송신하는 잠금 토크 상한(ESC_LsdTqMax)을 초과하는 잠금 토크를 출력하지 않아야 한다.", "C", "HIL"),
        ("ESC 제동 개입(ESC_Active=1) 중에는 잠금 토크 상한을 ESC 요청값과 300 N·m 중 작은 값으로 제한해야 한다.", "C", "HIL"),
        ("ESC 협조 메시지가 30ms 이상 수신되지 않거나 E2E 검사에 실패하면 잠금 토크를 200 N·m 이하로 제한해야 한다.", "C", "HIL (E2E 오류 주입)"),
        ("eLSD 제어기는 요레이트 오차(목표 대비 실제)가 오버스티어 방향으로 5 deg/s를 초과하면 잠금 토크를 감소시켜야 한다.", "C", "HIL + 차량"),
        ("언더스티어 상황에서 요레이트 오차가 3 deg/s를 초과하면 선회 보정 성분으로 잠금 토크를 최대 30% 증가시킬 수 있어야 한다.", "QM", "차량 시험"),
        ("eLSD 제어기는 현재 잠금 토크(LSD_TqAct)와 가용 최대 잠금 토크를 10ms 주기로 ESC에 송신해야 한다.", "C", "CANoe"),
        ("ESC가 OFF(완전 해제) 상태가 아니면 DRIFT 모드의 잠금 토크 특성을 사용하지 않아야 한다.", "C", "HIL")])
    D.h("3.3 주행 모드", 2)
    D.table("주행 모드별 특성", [["모드", "변형", "Δn 이득", "최대 잠금", "선회 보정", "비고"], ["COMFORT", "전체", "낮음 (×1.0)", "1,200 N·m", "약", "기본"], ["SPORT", "전체", "중간 (×1.75)", "최대값", "중", ""],
                              ["SNOW", "전체", "높음 (×2.25)", "1,500 N·m", "약", "저속 견인"], ["OFF-ROAD", "Off-road", "높음 (×2.5)", "최대값", "없음", "차속 40 km/h 이하"],
                              ["TRACK", "Sport", "매우 높음 (×2.75)", "최대값", "강", "런치 허용"], ["DRIFT", "Sport", "고정 프리로드", "최대값", "없음", "ESC OFF 필수"]], widths=[2.4, 2.2, 3, 2.4, 2.2, 3.8])
    D.R("MODE", "eLSD 제어기는 IDM 주행 모드 신호에 따라 모드별 잠금 토크 파라미터 세트를 선택해야 한다.", "HIL")
    D.R("MODE", "주행 모드 변경 시 파라미터는 500ms 동안 선형 블렌딩해야 하며, 잠금 토크 500 N·m 이상 출력 중에는 블렌딩을 지연해야 한다.", "HIL")
    D.R("MODE", "OFF-ROAD 모드는 차속 40 km/h를 초과하면 SPORT 특성으로 자동 전환해야 하며 전환 사유를 IDM에 송신해야 한다.", "HIL")
    D.R("MODE", "변형에서 허용되지 않은 모드가 요청되면 COMFORT 모드를 유지하고 거부 사유 코드를 송신해야 한다.", "CANoe")
    D.h("3.4 런치 컨트롤", 2)
    D.RT("LOCK", "런치 컨트롤 요구사항", [
        ("런치 컨트롤은 C3-Sport 변형, TRACK 모드, 차속 0 km/h, 브레이크 페달 ON 조건에서만 활성화되어야 한다.", "QM", "HIL"),
        ("런치 대기 중 eLSD 제어기는 잠금 토크를 600 N·m로 프리로드해야 한다.", "QM", "벤치 + 차량"),
        ("브레이크 해제 후 3초 동안 Δn 이득을 1.5배로 높여 휠스핀을 억제해야 한다.", "QM", "차량 시험"),
        ("런치 대기 상태가 10초를 넘으면 클러치 열 보호를 위해 프리로드를 해제해야 한다.", "QM", "HIL")])
    D.br()

    D.h("3.5 클러치 액추에이터 제어", 2)
    D.p("목표 잠금 토크는 클러치 특성 모델(토크–볼램프 위치)로 목표 위치로 변환되고, CDD_MotorCtrl이 위치·전류 제어를 수행한다. 그림 4는 잠금 토크 스텝 요청에 대한 응답 요구사항이다.")
    D.fig("l_step", "잠금 토크 스텝 응답 (0 → 1,500 N·m)")
    D.RT("CLU", "액추에이터 제어 요구사항", [
        ("eLSD 제어기는 목표 잠금 토크 0 → 1,500 N·m 스텝 요청에 대해 120ms 이내에 90%에 도달해야 한다.", "QM", "벤치 (토크 측정 다이나모)"),
        ("잠금 토크 1,500 N·m → 0 해제 요청에 대해 80ms 이내에 잠금 토크를 100 N·m 이하로 낮춰야 한다.", "C", "벤치"),
        ("정상 상태 잠금 토크 오차는 요청값의 ±10% 또는 ±50 N·m 중 큰 값 이내여야 한다.", "QM", "벤치"),
        ("볼램프 위치 제어 루프는 1ms 주기, 모터 전류 제어 루프는 50µs 주기로 수행해야 한다.", "C", "TRACE32 + 오실로스코프"),
        ("eLSD 제어기는 클러치 특성 모델을 오일 온도와 마모 상태에 따라 보정해야 한다.", "QM", "벤치 + 내구"),
        ("eLSD 제어기는 모터 위치 기준점(완전 개방 위치)을 매 INIT 시 기계적 스토퍼 접촉으로 확인해야 하며 400ms 이내에 완료해야 한다.", "C", "벤치"),
        ("모터 전류는 연속 15A, 피크 40A(500ms)로 제한해야 한다.", "QM", "벤치")])
    D.h("3.6 Kiss point 학습", 2)
    D.p("Kiss point는 클러치 판이 접촉하여 토크가 발생하기 시작하는 볼램프 위치이다. 마모에 따라 이동하므로 주기적으로 학습해야 한다. 그림 5는 학습 원리이다.")
    D.fig("l_kiss", "Kiss point 학습 원리 및 마모에 따른 이동")
    D.RT("CLU", "Kiss point 학습 요구사항", [
        ("eLSD 제어기는 직진 정속 주행(차속 30~80 km/h, 조향각 ±5°, 구동 토크 변동 10% 이내) 중 Kiss point 학습을 수행해야 한다.", "QM", "차량 시험"),
        ("학습 중 잠금 토크는 100 N·m를 넘지 않아야 하며 운전자가 느낄 수 없어야 한다.", "QM", "차량 평가"),
        ("학습값이 직전 값 대비 ±3% 이상 변하면 3회 연속 확인 후에만 반영해야 한다.", "QM", "HIL"),
        ("학습값이 허용 범위(12%~28%)를 벗어나면 학습을 거부하고 DTC C2A40을 저장해야 한다.", "QM", "HIL"),
        ("학습값은 IG OFF 시 NvM에 저장하고 UDS 루틴(0x31)으로 초기화·재학습할 수 있어야 한다.", "QM", "진단기")])
    D.h("3.7 클러치 열 및 마모 모델", 2)
    D.p("클러치 판 온도는 슬립 에너지와 오일 온도를 입력으로 하는 열 모델로 추정한다. 그림 6은 추정 온도에 따른 잠금 토크 제한이다.")
    D.fig("l_thermal", "클러치 판 추정 온도에 따른 허용 잠금 토크")
    D.RT("THERM", "열·마모 모델 요구사항", [
        ("eLSD 제어기는 클러치 슬립 파워(잠금 토크 × Δn)를 적산하는 2-질량 열 모델로 클러치 판 온도를 10ms 주기로 추정해야 한다.", "QM", "벤치 (열전대)"),
        ("클러치 판 추정 온도의 오차는 실측 대비 ±10°C 이내여야 한다.", "QM", "벤치"),
        ("추정 온도 130°C부터 165°C까지 허용 잠금 토크를 100%에서 20%로 선형 감소시켜야 한다.", "B", "HIL"),
        ("추정 온도가 175°C를 초과하면 잠금 토크를 0으로 하고 경고등(황색)을 점등해야 한다.", "B", "HIL"),
        ("오일 온도 센서가 고장 나면 냉각 모델의 오일 온도를 120°C로 가정하고 허용 잠금 토크를 60%로 제한해야 한다.", "B", "HIL (고장 주입)"),
        ("IG OFF 시 마지막 추정 온도와 시각을 저장하고 재시동 시 냉각 모델로 초기 온도를 계산해야 한다.", "QM", "HIL"),
        ("eLSD 제어기는 누적 슬립 에너지로 클러치 마모량을 추정하고 마모 한계의 90%에 도달하면 서비스 경고를 송신해야 한다.", "QM", "내구 시험")])
    D.h("3.8 서비스 모드", 2)
    D.R("MODE", "eLSD 제어기는 진단 루틴 또는 롤러 다이나모 검출(전륜 휠속 0, 후륜 휠속 > 20 km/h, 5초)로 다이나모 모드에 진입해야 하며, 다이나모 모드에서 잠금 토크를 0으로 유지해야 한다.", "차량 시험 (롤러)")
    D.R("MODE", "다이나모 모드는 IG OFF 또는 차속 신호 정상화(4륜 휠속 차 3 km/h 이내 10초) 시 해제되어야 한다.", "HIL")
    D.R("MODE", "IG OFF 및 견인 상태에서 클러치는 리턴 스프링으로 개방되어야 하며 잔류 잠금 토크는 30 N·m 이하여야 한다.", "벤치", "B")
    D.h("3.9 기능 조정 (우선순위)", 2)
    D.table("잠금 토크 요청 우선순위", [["순위", "요청원", "처리"], ["1", "안전 감시 (SWC_SafetyMon) / SAFE 상태", "강제 개방"], ["2", "ESC 잠금 토크 상한·개입", "상한 적용 (최솟값 선택)"],
                                      ["3", "열 보호·전압 제한", "비례 축소"], ["4", "서비스 모드 (다이나모·견인)", "0 고정"], ["5", "주차 선회 제한", "50 N·m 상한"], ["6", "런치 컨트롤 프리로드", "하한 적용"],
                                      ["7", "모드별 잠금 토크 산출 (견인·선회)", "기본"]], widths=[1.6, 7.4, 7])
    D.R("LOCK", "eLSD 제어기는 잠금 토크 요청을 표의 우선순위로 조정해야 하며, 상한 요청은 최솟값 선택, 하한 요청은 상한 이내에서만 적용해야 한다.", "HIL", "C")
    D.R("LOCK", "조정 결과와 활성 제한 사유(비트필드)를 10ms 주기로 송신해야 한다.", "CANoe")
    D.table("활성 제한 사유 비트필드 (LSD_LimReason)", [["비트", "사유", "설정 조건", "해제 조건"], ["0", "ESC 상한", "ESC_LsdTqMax < 목표", "상한 ≥ 목표 100 ms"], ["1", "ESC 개입", "ESC_Active = 1", "ESC_Active = 0"],
                                                  ["2", "열 제한", "추정 온도 ≥ 130 °C", "≤ 120 °C"], ["3", "전압 제한", "KL30 < 10 V 또는 > 16 V", "정상 500 ms"], ["4", "주차 선회", "차속 ≤ 10 km/h, 조향 ≥ 180°", "조건 해제"],
                                                  ["5", "서비스 모드", "다이나모·견인", "모드 해제"], ["6", "통신 품질", "타임아웃 / E2E 오류", "정상 1 s"], ["7", "안전 감시", "SafeState 요청", "전원 재인가"]], widths=[1.2, 3, 6, 5.8])
    D.h("3.10 입력 신호 처리", 2)
    D.p("잠금 토크 산출의 품질은 휠속·요레이트 신호 처리에 좌우된다. 본 절은 OEM이 기대하는 신호 처리 요구사항이다.")
    D.table("입력 신호 처리 파라미터", [["신호", "필터", "차단 주파수", "타당성 검사", "대체값"], ["휠속 (4륜)", "2차 버터워스", "15 Hz", "인접 휠 비교, 변화율 ≤ 150 km/h/s", "직전값 유지 50 ms"],
                                      ["요레이트", "1차 저역", "10 Hz", "조향각·횡가속 기반 모델 비교", "모델값"], ["횡가속", "1차 저역", "8 Hz", "요레이트×차속 비교", "추정값"],
                                      ["조향각", "없음 (ESC 처리값)", "—", "범위 ±780°", "0° (선회 보정 해제)"], ["후륜 구동 토크", "1차 저역", "20 Hz", "범위, 변화율", "0 (피드포워드 해제)"]], widths=[2.6, 3, 2.2, 5, 3.2])
    D.RT("LOCK", "입력 신호 처리 요구사항", [
        ("eLSD 제어기는 휠속 신호를 표의 필터로 처리하고 필터 지연은 15ms 이하여야 한다.", "QM", "MIL / HIL"),
        ("휠속 4개 중 1개가 타당성 검사에 실패하면 해당 차축의 Δn 산출을 중지하고 잠금 토크를 300 N·m 이하로 제한해야 한다.", "C", "HIL (신호 오류 주입)"),
        ("타이어 반경 편차 보정값은 직진 정속 주행 중 학습하고 ±3% 범위로 제한해야 한다.", "QM", "차량 시험"),
        ("요레이트 신호가 모델 대비 10 deg/s 이상 500ms 차이 나면 선회 보정 성분을 해제해야 한다.", "B", "HIL"),
        ("모든 입력 신호는 신호별 Qualifier(유효·대체·무효)를 갖고 SWC로 전달되어야 한다.", "C", "단위 시험")])
    D.br()

    # 4 ---------------------------------------------------------------- 운용 모드/전원
    D.h("4 운용 모드 및 전원")
    D.fig("l_states", "eLSD 제어기 운용 상태 천이도")
    D.table("상태 천이 조건", [["현재", "다음", "조건", "최대 시간"], ["SLEEP", "INIT", "KL15 ON 또는 CAN WUP", "—"], ["INIT", "STANDBY", "자기 진단·위치 기준점 확인 완료", "400 ms"],
                              ["STANDBY", "ACTIVE", "차량 Ready + 휠속 유효 + ESC 협조 유효", "100 ms"], ["ACTIVE", "LIMITED", "과열·저전압·통신 품질 저하", "10 ms"],
                              ["ACTIVE/LIMITED", "SAFE", "치명 고장", "FTTI 이내"], ["STANDBY", "SLEEP", "KL15 OFF, 차속 0, NM 슬립", "2 s"]], widths=[3, 3, 7, 3])
    D.RT("MODE", "운용 상태 요구사항", [
        ("eLSD 제어기는 KL15 ON 후 400ms 이내에 자기 진단과 위치 기준점 확인을 완료하고 STANDBY로 진입해야 한다.", "C", "HIL"),
        ("INIT 상태에서 RAM/ROM 테스트, 코어 자가 시험, 게이트 드라이버·상 차단 스위치 자기 진단을 수행해야 한다.", "C", "TRACE32"),
        ("STANDBY에서 클러치는 완전 개방 위치를 유지해야 한다.", "C", "벤치"),
        ("SAFE 상태는 전원 재인가 전까지 유지되어야 하며 SAFE 진입 사유를 NvM에 기록해야 한다.", "C", "HIL"),
        ("SLEEP 상태 암전류는 12.6V, 25°C에서 80µA 이하여야 한다.", "QM", "전류계")])
    D.table("전압 범위별 기능", [["KL30 전압", "기능 상태", "잠금 토크", "통신"], ["16 ~ 18 V", "과전압 제한", "100 → 0 %", "정상"], ["10 ~ 16 V", "정상", "100 %", "정상"],
                                ["8 ~ 10 V", "저전압 제한", "50 %", "정상"], ["6.5 ~ 8 V", "개방 유지", "0 % (개방)", "유지"], ["6.5 V 미만", "리셋 허용", "스프링 개방", "복귀 후 재개"]], widths=[3.4, 4, 4, 4.6])
    D.RT("ELEC", "전원 요구사항", [
        ("eLSD 제어기는 KL30 10V ~ 16V 범위에서 모든 기능을 정격 성능으로 수행해야 한다.", "QM", "벤치"),
        ("KL30 8V ~ 10V 범위에서 잠금 토크를 정격의 50%로 제한해야 한다.", "B", "벤치 + HIL"),
        ("KL30 8V 미만에서 클러치를 개방하고 통신을 유지해야 한다.", "B", "벤치"),
        ("크랭킹 프로파일(최저 6V)에서 리셋되지 않아야 하며 종료 후 300ms 이내에 STANDBY로 복귀해야 한다.", "QM", "크랭킹 시뮬레이터"),
        ("eLSD 제어기는 26V 점프 스타트(60초)와 역극성(-14V, 60초)에 손상되지 않아야 한다.", "QM", "벤치")])
    D.br()

    # 5 ---------------------------------------------------------------- 센서
    D.h("5 센서·액추에이터 인터페이스")
    D.table("센서 사양", [["센서", "방식", "범위", "정확도", "갱신", "비고"], ["모터 위치 (주)", "TMR, SPI 14bit", "0~360° 전기각", "±1°", "50 µs", "ASIL C"], ["모터 위치 (보조)", "홀 x3", "60° 분해능", "—", "에지", "타당성 비교"],
                         ["모터 상전류", "션트 + CSA x3", "±60 A", "±2 %", "50 µs", ""], ["오일 온도", "NTC 10kΩ", "-40 ~ 180 °C", "±3 °C", "100 ms", "차동 하우징"], ["PCB 온도", "NTC (온보드)", "-40 ~ 150 °C", "±3 °C", "100 ms", ""]],
            widths=[3, 3, 2.6, 1.8, 1.6, 4])
    D.RT("SENS", "센서 요구사항", [
        ("eLSD 제어기는 모터 위치를 TMR 센서와 홀 센서로 이중 측정하고 전기각 차가 30° 이상 2ms 지속되면 위치 센서 고장으로 판단해야 한다.", "C", "HIL (고장 주입)"),
        ("TMR 센서 SPI 통신의 CRC 오류가 3회 연속 발생하면 위치 센서 고장으로 판단해야 한다.", "C", "HIL"),
        ("위치 센서 고장 시 홀 센서로 클러치를 개방 위치로 복귀시키고 SAFE 상태로 천이해야 한다.", "C", "HIL + 벤치"),
        ("eLSD 제어기는 상전류 합(Iu+Iv+Iw)이 3A 이상 불일치하면 2ms 이내에 전류 측정 고장으로 판단해야 한다.", "C", "HIL"),
        ("오일 온도 센서 단선·단락은 500ms 이내에 검출해야 한다.", "B", "벤치"),
        ("오일 온도 신호가 1초에 20°C 이상 변하면 신호 타당성 고장으로 판단해야 한다.", "B", "HIL")])
    D.br()

    # 6 ---------------------------------------------------------------- 통신
    D.h("6 차량 통신")
    D.fig("l_network", "C3 구동·샤시 네트워크 토폴로지 (eLSD 관련)")
    D.table("eLSD 송신 메시지", [["메시지", "ID", "주기", "버스", "E2E", "주요 신호"], ["LSD_Status_01", "0x3A0", "10 ms", "Chassis", "Profile 5", "LSD_TqAct, LSD_TqAvail, LSD_State"],
                               ["LSD_Status_02", "0x3A1", "100 ms", "Chassis", "—", "LSD_ClutchTemp, LSD_WearLvl, LSD_LimReason"], ["LSD_PT_01", "0x2C0", "10 ms", "Powertrain", "Profile 5", "LSD_TqAct (VCU 토크 배분용)"],
                               ["LSD_Diag_Resp", "0x7B4", "이벤트", "Chassis", "—", "UDS 응답"]], widths=[3, 1.6, 1.6, 2.2, 2, 5.6])
    D.table("eLSD 수신 메시지", [["메시지", "송신", "주기", "타임아웃", "사용 신호", "타임아웃 시"], ["ESC_WhlSpd", "ESC", "10 ms", "30 ms", "WhlSpd_FL/FR/RL/RR", "램프 개방"],
                               ["ESC_Coord", "ESC", "10 ms", "30 ms", "ESC_LsdTqMax, ESC_Active, ESC_Off", "200 N·m 제한"], ["ESC_VehDyn", "ESC", "10 ms", "50 ms", "YawRate, LatAcc, StrAngle", "선회 보정 해제"],
                               ["VCU_Torque", "VCU", "10 ms", "50 ms", "TqRearAxle, Gear", "피드포워드 해제"], ["IDM_DrvMode", "IDM", "100 ms", "500 ms", "DrvMode, LaunchReq", "COMFORT"]], widths=[2.6, 1.4, 1.6, 1.8, 5, 3.6])
    D.table("ESC_Coord 신호 상세", [["신호", "시작 비트", "길이", "범위", "단위", "설명"], ["ESC_LsdTqMax", "16", "12", "0~4095", "N·m", "eLSD 잠금 토크 상한"], ["ESC_Active", "28", "1", "0/1", "—", "ESC 제동 개입 중"],
                                   ["ESC_Off", "29", "2", "0~2", "—", "0 ON, 1 SPORT, 2 완전 OFF"], ["ESC_LsdReqMode", "31", "3", "0~5", "—", "0 없음, 1 감소, 2 개방, 3 유지"], ["ESC_Coord_CRC/Cnt", "0 / 64", "16 / 8", "—", "—", "E2E Profile 5"]],
            widths=[3.4, 1.8, 1.4, 2.2, 1.4, 5.8])
    D.RT("COM", "통신 요구사항", [
        ("eLSD 제어기는 CAN-FD 공칭 500kbps, 데이터 2Mbps로 Chassis·Powertrain 두 채널에서 통신해야 한다.", "QM", "CANoe"),
        ("eLSD 제어기는 송신 메시지를 지정 주기 ±5% 이내로 송신해야 한다.", "QM", "CANoe"),
        ("ASIL 신호를 포함한 송수신 메시지에는 E2E Profile 5를 적용하고 CRC·카운터 오류를 메시지 단위로 검출해야 한다.", "C", "CANoe (E2E 오류 주입)"),
        ("수신 메시지가 타임아웃되면 표의 대체 동작을 수행하고 해당 DTC를 저장해야 한다.", "C", "CANoe"),
        ("eLSD 제어기는 AUTOSAR CanNm을 지원하고 Partial Networking으로 선택적 웨이크업을 지원해야 한다.", "QM", "CANoe")])
    D.br()

    # 7 ---------------------------------------------------------------- 진단
    D.h("7 진단")
    D.table("지원 UDS 서비스", [["SID", "서비스", "기본", "확장", "프로그래밍"], ["0x10", "DiagnosticSessionControl", "O", "O", "O"], ["0x11", "ECUReset", "O", "O", "O"], ["0x14", "ClearDiagnosticInformation", "O", "O", "—"],
                              ["0x19", "ReadDTCInformation", "O", "O", "—"], ["0x22", "ReadDataByIdentifier", "O", "O", "O"], ["0x27", "SecurityAccess", "—", "O", "O"], ["0x2E", "WriteDataByIdentifier", "—", "O", "—"],
                              ["0x2F", "InputOutputControlByIdentifier", "—", "O", "—"], ["0x31", "RoutineControl", "—", "O", "O"], ["0x34/36/37", "다운로드", "—", "—", "O"], ["0x3E", "TesterPresent", "O", "O", "O"], ["0x85", "ControlDTCSetting", "—", "O", "O"]],
            widths=[2, 6, 2, 2, 2.6])
    D.table("DTC 목록", [["DTC", "설명", "검출 조건", "확정", "반응", "경고등"],
                       ["C2A01", "모터 위치 센서 불일치", "전기각 차 > 30°, 2 ms", "2 ms", "SAFE (개방)", "황색"], ["C2A02", "TMR 센서 통신 고장", "SPI CRC 3회 연속", "1 ms", "SAFE", "황색"],
                       ["C2A03", "상전류 측정 고장", "합 불일치 > 3 A", "2 ms", "SAFE", "황색"], ["C2A04", "과전류", "상전류 > 60 A", "10 µs (HW)", "게이트 차단", "황색"],
                       ["C2A05", "MOSFET 단락", "VDS 감시 / 자기진단", "10 µs", "상 차단", "황색"], ["C2A06", "모터 구속", "목표 위치 미도달 300 ms", "300 ms", "SAFE", "황색"],
                       ["C2A10", "변형 코딩 오류", "코딩값 무효", "즉시", "AWD 파라미터", "—"], ["C2A20", "클러치 과열", "추정 온도 > 175 °C", "100 ms", "잠금 0", "황색"],
                       ["C2A21", "오일 온도 센서 고장", "단선·단락·급변", "500 ms", "60% 제한", "—"], ["C2A30", "잠금 토크 타당성 고장", "요청·추정 차 > 300 N·m, 50 ms", "50 ms", "SAFE", "황색"],
                       ["C2A31", "의도치 않은 잠금", "요청 0인데 추정 > 200 N·m", "50 ms", "SAFE", "황색"], ["C2A40", "Kiss point 학습 실패", "범위 이탈", "학습 시", "기본값", "—"],
                       ["C2A41", "클러치 마모 한계", "추정 마모 > 90 %", "—", "서비스 경고", "—"], ["C2A50", "KL30 저전압", "8 V 미만 500 ms", "500 ms", "개방", "—"], ["C2A51", "KL30 과전압", "18 V 초과", "500 ms", "개방", "—"],
                       ["C2A60", "MCU 내부 고장", "Lockstep / SMU", "≤ 1 ms", "SAFE", "황색"], ["C2A61", "와치독 고장", "WdgM / PMIC 위반", "≤ 20 ms", "PMIC 차단", "황색"], ["C2A62", "메모리 고장", "ECC / CRC", "≤ 10 ms", "SAFE", "황색"],
                       ["C2A63", "OS 타이밍 위반", "데드라인 / 실행 순서", "≤ 10 ms", "SAFE", "황색"], ["U0121", "ESC 휠속 통신 두절", "30 ms 미수신", "30 ms", "램프 개방", "—"],
                       ["U0122", "ESC 협조 무효", "타임아웃 / E2E 3회", "30 ms", "200 N·m 제한", "—"], ["U0101", "VCU 통신 두절", "50 ms 미수신", "50 ms", "피드포워드 해제", "—"],
                       ["U1101", "SecOC 검증 실패", "MAC 불일치 3회", "—", "메시지 폐기", "—"]], widths=[1.6, 3.4, 3.8, 1.8, 3, 1.4])
    D.table("DID 목록", [["DID", "이름", "길이", "접근", "설명"], ["0xF187", "OEM 부품 번호", "10 B", "R", "ACME 품번"], ["0xF18C", "ECU 일련번호", "16 B", "R", "EOL 기록"],
                       ["0xF195", "SW 버전", "8 B", "R", "어플리케이션 / 캘리브레이션"], ["0xF1A0", "AUTOSAR BSW 버전", "8 B", "R", "BSW 릴리스·MCAL 버전"], ["0x0100", "변형 코딩", "4 B", "R/W", "보안 레벨 1"],
                       ["0x0200", "현재 잠금 토크 요청/실제", "4 B", "R", "N·m"], ["0x0201", "볼램프 위치", "2 B", "R", "0.01 %"], ["0x0202", "클러치 추정 온도 / 오일 온도", "4 B", "R", "0.1 °C"],
                       ["0x0203", "Kiss point 학습값", "2 B", "R", "0.01 %"], ["0x0204", "누적 마모율", "2 B", "R", "0.1 %"], ["0x0205", "활성 제한 사유", "2 B", "R", "비트필드"],
                       ["0x0206", "SAFE 진입 기록", "32 B", "R", "최근 4회"], ["0x0207", "FiM 억제 상태", "2 B", "R", "FID별 비트"], ["0x0210", "모터 위치 오프셋", "2 B", "R/W", "EOL 전용"]],
            widths=[1.8, 5, 1.4, 1.6, 6.2])
    D.table("루틴 목록 (0x31)", [["RID", "이름", "조건", "결과"], ["0x0301", "Kiss point 재학습", "차속 0, 엔진 ON, P단", "학습값, 성공/실패"], ["0x0302", "마모량 초기화", "보안 레벨 1", "—"],
                               ["0x0303", "액추에이터 풀스트로크 시험", "차속 0, 리프트 업", "위치·전류 프로파일"], ["0x0304", "다이나모 모드 진입/해제", "차속 0", "모드 상태"],
                               ["0x0305", "위치 기준점 확인", "차속 0", "오프셋, 성공/실패"], ["0xFF00", "메모리 삭제", "프로그래밍 세션", "—"], ["0xFF01", "의존성 검사", "프로그래밍 세션", "서명·호환성"]], widths=[1.8, 5, 4.6, 4.6])
    D.RT("DIAG", "진단 요구사항", [
        ("eLSD 제어기는 DTC 목록 표의 고장을 지정 조건과 확정 시간에 따라 검출하고 AUTOSAR Dem으로 DTC 상태를 관리해야 한다.", "QM", "진단기 + HIL"),
        ("DTC 확정 시 스냅숏(차속, 휠속 4개, 잠금 토크 요청·실제, 클러치 온도, KL30, 운용 상태)을 저장해야 한다.", "QM", "진단기"),
        ("eLSD 제어기는 0x2F 서비스로 볼램프 위치를 강제 구동하는 액추에이터 시험을 지원해야 하며 차속 0 km/h에서만 허용해야 한다.", "B", "진단기"),
        ("주행 중(차속 3 km/h 이상) 0x2E, 0x2F, 0x31, 0x34 요청은 NRC 0x22로 거부해야 한다.", "B", "진단기"),
        ("DTC 에이징은 40 운전 사이클 동안 재발생이 없을 때 수행해야 한다.", "QM", "HIL")])
    D.br()

    # 8 ---------------------------------------------------------------- 안전
    D.h("8 기능 안전")
    D.p("본 절의 안전 목표는 HARA-LSD-C3에서 도출되었다. 고속 선회 중 의도하지 않은 잠금은 요 불안정을 일으킬 수 있으므로 가장 높은 등급으로 평가되었다.")
    D.table("안전 목표", [["ID", "안전 목표", "ASIL", "안전 상태", "FTTI"], ["SG-01", "의도하지 않은 잠금 토크 발생(과잉 잠금)을 방지한다", "C", "클러치 개방 (< 50 N·m)", "200 ms"],
                         ["SG-02", "ESC 개입 중 잠금 토크 상한 위반을 방지한다", "C", "상한 이하로 제한 / 개방", "100 ms"], ["SG-03", "고착된 잠금(해제 불능)을 방지한다", "B", "스프링 개방 + 경고", "500 ms"],
                         ["SG-04", "잘못된 잠금 토크 정보 송신을 방지한다", "B", "신호 Invalid", "100 ms"]], widths=[1.6, 7, 1.2, 4, 1.6])
    D.fig("l_ftti", "SG-01 시간 예산")
    D.RT("SAFE", "기능 안전 요구사항", [
        ("eLSD 제어기는 잠금 토크 요청과 클러치 모델 기반 추정 잠금 토크의 차이가 300 N·m 이상 50ms 지속되면 잠금 토크 타당성 고장으로 판단해야 한다.", "C", "HIL (고장 주입)"),
        ("요청이 0인데 추정 잠금 토크가 200 N·m를 초과하면 의도하지 않은 잠금으로 판단하고 FTTI 200ms 이내에 클러치를 개방해야 한다.", "C", "HIL + 벤치"),
        ("잠금 토크 산출·조정 경로는 독립된 감시 SWC(SWC_SafetyMon)가 ASIL C 파티션에서 검증해야 한다.", "C", "설계 리뷰 + HIL"),
        ("eLSD 제어기는 PMIC 윈도우 와치독과 AUTOSAR WdgM(Alive·Deadline·Logical 감시)을 함께 사용해야 한다.", "C", "고장 주입 (TRACE32)"),
        ("와치독 위반 시 SW와 독립된 하드웨어 경로로 게이트 드라이버를 비활성화해야 하며 리턴 스프링으로 클러치가 개방되어야 한다.", "C", "벤치"),
        ("상 차단 스위치는 매 INIT 시 자기 진단해야 하며 진단 실패 시 ACTIVE 진입을 금지해야 한다.", "C", "HIL + 벤치"),
        ("모터 상전류가 60A를 초과하면 하드웨어 비교기로 10µs 이내에 게이트를 차단해야 한다.", "C", "벤치 (단락)"),
        ("안전 관련 캘리브레이션 데이터는 CRC로 보호하고 INIT 및 1초 주기로 검증해야 한다.", "C", "단위 시험 + HIL"),
        ("eLSD 제어기는 SPFM 97% 이상, LFM 80% 이상, PMHF 100 FIT 미만을 달성해야 한다.", "C", "FMEDA"),
        ("SAFE 상태 진입 시 경고등을 점등하고 LSD_State=SAFE를 송신해야 하며 ESC는 이를 수신해 eLSD 기여 없이 안정성 제어를 수행한다.", "C", "CANoe + 차량")])
    D.table("고장 반응 매트릭스", [["고장 분류", "ACTIVE 반응", "LIMITED 반응", "경고등", "ESC 통보", "복귀 조건"], ["센서 (위치·전류)", "SAFE (개방)", "SAFE", "황색", "LSD_State=SAFE", "IG 재시동 + 고장 해소"],
                                   ["액추에이터 (구속·단락)", "SAFE", "SAFE", "황색", "SAFE", "IG 재시동"], ["타당성 (잠금 토크)", "SAFE", "SAFE", "황색", "SAFE", "IG 재시동"],
                                   ["통신 (ESC 협조)", "200 N·m 제한", "200 N·m 제한", "—", "LIMITED", "신호 정상 1 s"], ["통신 (휠속)", "램프 개방", "램프 개방", "—", "LIMITED", "신호 정상 1 s"],
                                   ["열 (과열)", "단계 제한 / 0", "단계 제한", "175 °C 초과 시", "LIMITED", "온도 하강 (히스테리시스 10 °C)"], ["전원 (저/과전압)", "50% / 개방", "개방", "—", "LIMITED", "전압 정상 500 ms"],
                                   ["MCU·WDG·메모리", "SAFE (HW 차단)", "SAFE", "황색", "SAFE / 무응답", "전원 재인가"]], widths=[3.2, 2.6, 2.4, 1.8, 2.6, 3.4])
    D.R("SAFE", "eLSD 제어기는 고장 분류별로 고장 반응 매트릭스의 반응과 복귀 조건을 따라야 하며, SAFE 상태에서의 복귀는 전원 재인가 이후에만 허용해야 한다.", "HIL (고장 주입 캠페인)", "C")
    D.R("SAFE", "LIMITED 상태에서 복귀할 때 잠금 토크는 1초 램프로 정상 상한까지 복원해야 한다.", "HIL", "B")
    D.R("SAFE", "SG-03(고착 잠금) 방지를 위해 eLSD 제어기는 개방 지령 후 300ms 이내에 볼램프 위치가 10% 미만으로 복귀하지 않으면 모터 역구동 재시도와 경고를 수행해야 한다.", "벤치 (마찰 증대)", "B")
    D.R("SAFE", "SG-04 방지를 위해 LSD_TqAct 신호는 고장 시 Invalid(0xFFF)로 송신하고 E2E 카운터를 계속 증가시켜야 한다.", "CANoe", "B")
    D.table("안전 메커니즘 할당", [["안전 메커니즘", "대상 고장", "검출 시간", "반응", "SG", "구현"], ["위치 센서 이중 측정", "위치 센서 고장", "2 ms", "SAFE", "SG-01, 03", "SW (CDD)"],
                                   ["잠금 토크 타당성 감시", "모델·액추에이터 고장", "50 ms", "SAFE", "SG-01", "SW (SafetyMon)"], ["ESC 상한 독립 비교", "조정 로직 오류", "10 ms", "개방", "SG-02", "SW (SafetyMon)"],
                                   ["상전류 합 감시", "전류 측정 고장", "2 ms", "SAFE", "SG-01", "SW (CDD)"], ["하드웨어 과전류 비교기", "단락·과전류", "10 µs", "게이트 차단", "SG-01", "HW"],
                                   ["Lockstep / SMU / ECC", "MCU 내부 고장", "≤ 1 ms", "SAFE", "전체", "HW"], ["WdgM + PMIC WDG", "SW 실행·타이밍 오류", "≤ 20 ms", "게이트 비활성", "SG-01, 02", "HW + BSW"],
                                   ["E2E Profile 5", "CAN 신호 손상", "30 ms", "제한·개방", "SG-02", "BSW"], ["MPU 메모리 파티션", "QM → ASIL 간섭", "즉시", "SAFE", "전체", "OS + HW"], ["리턴 스프링", "전원·구동 상실", "기계적", "개방", "SG-01, 03", "기구"]],
            widths=[3.8, 3.4, 1.8, 2.4, 2, 2.6])
    D.br()

    # 9 ---------------------------------------------------------------- AUTOSAR
    D.h("9 AUTOSAR 소프트웨어 아키텍처")
    D.p("eLSD 소프트웨어는 AUTOSAR Classic 플랫폼을 기반으로 한다. 본 장은 OEM이 차량 통합과 재사용, 안전성 확보를 위해 요구하는 아키텍처·구성·산출물 요구사항이다. 공급사는 AMS-2400 가이드라인의 명명 규칙과 구성 원칙을 따라야 한다.")
    D.h("9.1 플랫폼", 2)
    D.RT("AR", "AUTOSAR 플랫폼 요구사항", [
        ("eLSD 소프트웨어는 AUTOSAR Classic Platform R20-11 이상 규격을 따르는 BSW와 RTE를 사용해야 한다.", "QM", "설계 리뷰 (BSW 버전 목록)"),
        ("BSW와 RTE 생성 도구는 ISO 26262 도구 신뢰 수준(TCL)을 평가하고 ASIL C 이상 사용 근거를 제출해야 한다.", "C", "도구 적격성 보고서"),
        ("MCAL은 MCU 공급사가 제공하는 ASIL 인증 MCAL을 사용해야 하며 버전과 안전 매뉴얼 준수 내역을 제출해야 한다.", "C", "설계 리뷰"),
        ("SW는 그림 10의 계층 구조를 따라야 하며 ASW는 MCAL·하드웨어 레지스터에 직접 접근하지 않아야 한다.", "QM", "정적 분석 + 아키텍처 리뷰"),
        ("하드웨어 직접 접근이 필요한 모터 제어와 위치 센서 처리는 CDD(CDD_MotorCtrl, CDD_PosSens)로 구현하고 인터페이스를 ARXML로 기술해야 한다.", "C", "설계 리뷰")])
    D.fig("l_autosar", "eLSD SW 계층 구조 (AUTOSAR Classic)")
    D.h("9.2 소프트웨어 컴포넌트", 2)
    D.p("그림 11은 주요 SWC와 포트 연결이다. 공급사는 SWC 분할을 변경할 수 있으나 ASIL 할당과 감시 구조(제어 경로와 감시 경로 분리)는 유지해야 한다.")
    D.fig("l_swc", "주요 SWC 구성 및 데이터 흐름")
    D.table("SWC 목록", [["SWC", "ASIL", "주요 Runnable", "주기", "역할"], ["SWC_LsdCoord", "C", "LsdCoord_Run", "5 ms", "모드·ESC 상한·요청 조정"], ["SWC_LockTqCalc", "C", "LockTq_Run", "5 ms", "목표 잠금 토크 산출"],
                       ["SWC_ClutchCtrl", "C", "ClutchCtrl_Run", "1 ms", "토크→위치 변환, 위치 지령"], ["SWC_ThermWear", "QM", "Therm_Run / Wear_Run", "10 / 100 ms", "열·마모 모델"],
                       ["SWC_KissLearn", "QM", "Kiss_Run", "10 ms", "Kiss point 학습"], ["SWC_SafetyMon", "C", "SafeMon_Run", "5 ms", "독립 감시·SafeState 요청"],
                       ["SWC_ModeMgr", "C", "ModeMgr_Run", "10 ms", "운용 상태 머신 (BswM 연동)"], ["SWC_DiagMgr", "QM", "DiagMgr_Run", "10 ms", "진단 이벤트·루틴"],
                       ["SWC_SignalIf", "C", "SigIf_Rx / SigIf_Tx", "10 ms", "Com 신호 변환·타당성"], ["CDD_MotorCtrl", "C", "Foc_Isr / PosCtrl_Run", "50 µs / 1 ms", "FOC·위치 제어"],
                       ["CDD_PosSens", "C", "PosSens_Isr", "50 µs", "TMR/홀 처리, 이중 비교"]], widths=[3.4, 1.2, 3.8, 2.4, 5.2])
    D.table("주요 포트 인터페이스", [["인터페이스", "종류", "데이터 요소 / 오퍼레이션", "자료형", "제공 → 요구"], ["If_LsdMode", "S/R (Mode)", "LsdMode", "Mode 그룹 MDG_LsdState", "ModeMgr → 전체"],
                                    ["If_TqLockReq", "S/R", "TqLockReq", "uint16, 1 N·m/bit", "LockTqCalc → ClutchCtrl"], ["If_TqLimit", "S/R", "TqLimEsc, TqLimTherm, TqLimVolt", "uint16", "LsdCoord·ThermWear → ClutchCtrl"],
                                    ["If_TqLockAct", "S/R", "TqLockAct, TqLockActQf", "uint16 + QF", "ClutchCtrl → SafetyMon·SignalIf"], ["If_PosReq", "S/R", "PosReq", "uint16, 0.01 %/bit", "ClutchCtrl → CDD_MotorCtrl"],
                                    ["If_VehDyn", "S/R", "WhlSpd[4], YawRate, LatAcc", "레코드 + QF", "SignalIf → LsdCoord·LockTqCalc"], ["If_SafeState", "C/S", "RequestSafeState(reason)", "Std_ReturnType", "SafetyMon → ModeMgr"],
                                    ["If_NvKiss", "C/S (NvM)", "ReadBlock / WriteBlock", "NvM_BlockIdType", "KissLearn → NvM"], ["If_DiagEvent", "C/S (Dem)", "SetEventStatus", "Dem_EventIdType", "각 SWC → Dem"],
                                    ["If_Fim", "C/S (FiM)", "GetFunctionPermission", "FiM_FunctionIdType", "LockTqCalc·KissLearn → FiM"]], widths=[2.8, 2, 4.6, 3.2, 3.4])
    D.RT("AR", "SWC 및 RTE 요구사항", [
        ("모든 SWC 간 통신은 RTE를 통해야 하며 전역 변수 공유를 금지해야 한다.", "C", "정적 분석"),
        ("ASIL 데이터 요소에는 범위·타당성 정보(Qualifier)를 함께 전달해야 하며 수신 SWC는 Qualifier가 무효이면 대체 동작을 수행해야 한다.", "C", "단위 시험 + HIL"),
        ("SWC_SafetyMon은 SWC_LockTqCalc·SWC_ClutchCtrl과 다른 OS-Application에 배치되어야 한다.", "C", "구성 리뷰 (ECU 구성 ARXML)"),
        ("Runnable의 실행 순서(SignalIf → LsdCoord → LockTqCalc → ClutchCtrl → SafetyMon)는 동일 태스크 내 순서로 보장해야 한다.", "C", "TRACE32 타이밍"),
        ("SWC 설명(SWC Description ARXML)은 포트·자료형·Runnable·타이밍 이벤트를 포함해야 하며 OEM 통합 도구에서 오류 없이 가져올 수 있어야 한다.", "QM", "ARXML 검증 (OEM 도구)"),
        ("자료형은 AUTOSAR Application/Implementation 데이터 타입과 Compu-Method로 물리 단위를 정의해야 한다.", "QM", "ARXML 리뷰")])
    D.br()
    D.h("9.3 OS 및 멀티코어", 2)
    D.table("OS 태스크 및 코어 할당", [["태스크", "코어", "OS-Application", "주기", "우선순위", "주요 Runnable", "WCET 예산"],
                                     ["Task_Isr_Foc", "Core0", "OsApp_Asil", "50 µs (ISR)", "최고", "Foc_Isr, PosSens_Isr", "20 µs"], ["Task_1ms_Asil", "Core0", "OsApp_Asil", "1 ms", "높음", "PosCtrl_Run, ClutchCtrl_Run", "300 µs"],
                                     ["Task_5ms_Asil", "Core0", "OsApp_Asil", "5 ms", "중간", "SigIf, LsdCoord, LockTq, SafeMon", "1.2 ms"], ["Task_10ms_Asil", "Core0", "OsApp_Asil", "10 ms", "중간", "ModeMgr, E2E 처리", "1 ms"],
                                     ["Task_10ms_Qm", "Core1", "OsApp_Qm", "10 ms", "중간", "Therm, Kiss, DiagMgr, Com", "2.5 ms"], ["Task_100ms_Qm", "Core1", "OsApp_Qm", "100 ms", "낮음", "Wear, NvM, Dem 에이징", "8 ms"],
                                     ["Task_Bsw", "Core1", "OsApp_Bsw", "5 ms", "중간", "Com, Dcm, CanTp MainFunction", "1.5 ms"], ["Task_Bg", "Core0/1", "각각", "백그라운드", "최저", "RAM/ROM 시험", "—"]],
            widths=[2.8, 1.4, 2.6, 2, 1.6, 4, 1.6])
    D.RT("AR", "OS·멀티코어 요구사항", [
        ("AUTOSAR OS는 SC3 이상(메모리 보호 + 타이밍 보호)으로 구성해야 한다.", "C", "구성 리뷰"),
        ("ASIL 소프트웨어는 Core0의 OsApp_Asil에, QM 소프트웨어는 Core1의 OsApp_Qm에 배치해야 한다.", "C", "구성 리뷰"),
        ("코어 간 데이터 교환은 IOC 또는 RTE 코어 간 통신을 사용해야 하며 공유 메모리 직접 접근을 금지해야 한다.", "C", "정적 분석"),
        ("QM 파티션의 데이터를 ASIL 파티션에서 사용할 때는 범위 검사와 E2E 수준의 보호(CRC 또는 이중 저장)를 적용해야 한다.", "C", "단위 시험"),
        ("최악 조건 CPU 부하는 코어별 70% 이하여야 한다.", "QM", "TRACE32 프로파일링"),
        ("타이밍 보호 위반, 메모리 보호 위반은 ProtectionHook에서 처리하여 SAFE 상태로 천이해야 한다.", "C", "고장 주입"),
        ("1ms 태스크 시작 지터는 30µs 이하여야 한다.", "C", "TRACE32")])
    D.h("9.4 BSW 구성", 2)
    D.table("BSW 모듈 구성 요구사항", [["모듈", "주요 구성 요구사항", "ASIL"], ["EcuM / BswM", "INIT·STANDBY·ACTIVE·SAFE 상태를 BswM 규칙으로 구성, SAFE 진입 시 Com 송신 상태 갱신", "C"],
                                     ["Com / PduR / CanIf", "신호 그룹 단위 송수신, 타임아웃 시 대체값, 2채널 CAN-FD", "QM / C(E2E)"], ["E2E (E2EXf)", "Profile 5, ESC_WhlSpd·ESC_Coord·LSD_Status_01·LSD_PT_01", "C"],
                                     ["SecOC / Csm", "ESC_Coord 수신 MAC 검증 (AES-128 CMAC), 신선도 관리", "QM"], ["Dcm / Dem", "AMS-2200 진단 사양, DTC·스냅숏·에이징, 세션·보안 레벨", "QM"],
                                     ["FiM", "Dem 이벤트별 기능 억제 (부록의 매핑 표)", "C"], ["NvM / Fee", "이중화 블록(학습값·열 상태·SAFE 기록), CRC16, 쓰기 지연 2 s", "QM / C"],
                                     ["WdgM / WdgIf", "Alive·Deadline·Logical 감시, 감시 엔티티 = ASIL Runnable", "C"], ["Os", "SC3, 2코어, ProtectionHook, IOC", "C"], ["Xcp", "CAN-FD 기반 측정·캘리브레이션, 양산에서 비활성", "QM"],
                                     ["Det", "개발 단계 활성, 양산 비활성 (Runtime 오류만 Dem 보고)", "QM"]], widths=[3.4, 10.6, 2])
    D.RT("AR", "BSW 구성 요구사항", [
        ("BSW 모듈 구성은 표의 요구사항을 만족해야 하며 OEM이 제공한 통신·진단 추출(System Extract, Diagnostic Extract)을 입력으로 사용해야 한다.", "QM", "구성 리뷰"),
        ("E2E 보호는 E2E Transformer 또는 E2E Library로 구현하고 수신 상태(E2E_P05CheckStatus)를 SWC에 전달해야 한다.", "C", "단위 시험 + CANoe"),
        ("FiM은 Dem 이벤트 상태에 따라 잠금 토크 기능·Kiss 학습·런치 기능을 억제해야 하며 억제 상태를 진단으로 읽을 수 있어야 한다.", "C", "HIL"),
        ("NvM 이중화 블록 중 하나가 손상되어도 데이터를 복구해야 하며, 둘 다 손상되면 기본값을 사용하고 DTC를 저장해야 한다.", "QM", "HIL (메모리 고장 주입)"),
        ("WdgM 감시 결과가 FAILED가 되면 BswM이 SAFE 모드로 전환하고 PMIC 와치독 트리거를 중지해야 한다.", "C", "고장 주입"),
        ("양산 SW에서 Det와 Xcp 쓰기 기능은 비활성화되어야 한다.", "QM", "구성 리뷰 + 보안 시험")])
    D.table("Dem 이벤트 · DTC · FiM 억제 매핑", [["Dem 이벤트", "DTC", "디바운스", "FiM 억제 기능", "동작 사이클"], ["DEM_E_POS_SENS_PLAUS", "C2A01", "카운터 2", "FID_LOCK_TORQUE, FID_KISS_LEARN", "IGNITION"],
                                             ["DEM_E_TMR_COMM", "C2A02", "카운터 3", "FID_LOCK_TORQUE", "IGNITION"], ["DEM_E_CURR_PLAUS", "C2A03", "타이머 2 ms", "FID_LOCK_TORQUE", "IGNITION"],
                                             ["DEM_E_CLUTCH_OVERTEMP", "C2A20", "타이머 100 ms", "FID_LOCK_TORQUE (0%), FID_LAUNCH", "IGNITION"], ["DEM_E_OILTEMP_SENS", "C2A21", "타이머 500 ms", "FID_KISS_LEARN", "IGNITION"],
                                             ["DEM_E_LOCKTQ_PLAUS", "C2A30", "타이머 50 ms", "FID_LOCK_TORQUE", "IGNITION"], ["DEM_E_KISS_RANGE", "C2A40", "즉시", "FID_KISS_LEARN", "IGNITION"],
                                             ["DEM_E_ESC_COORD", "U0122", "타이머 30 ms", "FID_LAUNCH, FID_DRIFT", "IGNITION"], ["DEM_E_WDGM", "C2A61", "즉시", "FID_LOCK_TORQUE", "POWER"]], widths=[4.2, 1.6, 2.4, 5.2, 2.6])
    D.h("9.5 산출물 및 통합", 2)
    D.RT("AR", "AUTOSAR 산출물 요구사항", [
        ("공급사는 SWC Description, ECU Extract, BSW 모듈 구성(EcucValues), 진단 구성 ARXML을 각 SW 배포 시 제출해야 한다.", "QM", "납품물 검토"),
        ("ARXML은 AUTOSAR 스키마 검증과 OEM 규칙 검사(AMS-2400)를 오류 없이 통과해야 한다.", "QM", "ARXML 검증 도구"),
        ("공급사는 XCP 측정·캘리브레이션을 위한 A2L 파일을 SW 빌드와 동일한 버전으로 제출해야 하며 주소 일치를 자동 검사해야 한다.", "QM", "A2L 검증"),
        ("공급사는 RTE·BSW 생성 로그와 MISRA 위반 정당화 목록을 함께 제출해야 한다.", "QM", "납품물 검토"),
        ("OEM 차량 통신 사양 변경(DBC/System Extract) 시 공급사는 10 영업일 이내에 Com·E2E·SecOC 구성을 갱신해 배포해야 한다.", "QM", "변경 관리 감사"),
        ("ASIL C 소프트웨어 유닛은 MC/DC 커버리지 100%를 달성해야 하며 MISRA C:2012 필수 규칙을 100% 준수해야 한다.", "C", "단위 시험 + 정적 분석")])
    D.br()

    D.h("9.6 모드 관리 및 통신 관리", 2)
    D.table("BswM 모드 규칙", [["규칙", "조건", "동작 (Action List)"], ["BswM_Rule_Startup", "EcuM RUN 진입", "ComM FULL_COM 요청, Com I-PDU 그룹 Rx 시작, Dem 동작 사이클 시작"],
                              ["BswM_Rule_Active", "LsdMode = ACTIVE", "Tx I-PDU 그룹(LSD_Status_*) 시작, FiM 활성"], ["BswM_Rule_Limited", "LsdMode = LIMITED", "LSD_LimReason 갱신, 진단 이벤트 보고"],
                              ["BswM_Rule_Safe", "SafeState 요청 / WdgM FAILED", "CDD 출력 비활성, LSD_State=SAFE 송신 유지, NvM SAFE 기록 요청"], ["BswM_Rule_Prog", "Dcm 프로그래밍 세션", "Tx 일반 PDU 정지, 클러치 개방 확인 후 부트로더 점프"],
                              ["BswM_Rule_Shutdown", "KL15 OFF + 차속 0", "NvM WriteAll, ComM NO_COM, EcuM 슬립 준비"]], widths=[3.6, 4.4, 8])
    D.RT("AR", "모드·통신 관리 요구사항", [
        ("운용 상태 머신은 SWC_ModeMgr가 소유하고 BswM은 Mode 포트로 상태를 받아 BSW 동작을 수행해야 한다.", "C", "설계 리뷰"),
        ("ComM은 두 CAN-FD 채널을 독립 채널로 구성하고 한 채널의 Bus-Off가 다른 채널 통신에 영향을 주지 않아야 한다.", "QM", "CANoe (Bus-Off 주입)"),
        ("Bus-Off 복구는 빠른 복구 5회(10ms) 후 느린 복구(200ms)로 수행하고 Bus-Off 지속 1초 시 DTC를 저장해야 한다.", "QM", "CANoe"),
        ("CanNm 슬립 준비 시간은 1.5초 이하여야 하며 eLSD는 NM 메시지 반복 상태에서 버스를 깨우지 않아야 한다.", "QM", "CANoe"),
        ("셧다운 시 NvM WriteAll 완료 전에는 전원 유지 요청을 해제하지 않아야 한다.", "QM", "벤치 (전원 차단)")])
    D.h("9.7 NvM 블록 구성", 2)
    D.table("NvM 블록 목록", [["블록", "크기", "관리 형식", "CRC", "쓰기 시점", "ASIL", "기본값"], ["NvBlk_KissPoint", "8 B", "Redundant", "CRC16", "학습 확정·IG OFF", "QM", "18.0 %"],
                             ["NvBlk_ThermState", "12 B", "Native", "CRC16", "IG OFF", "QM", "오일 온도"], ["NvBlk_WearAcc", "16 B", "Redundant", "CRC32", "IG OFF", "QM", "0"],
                             ["NvBlk_PosOffset", "8 B", "Redundant", "CRC16", "EOL", "C", "없음 (DTC)"], ["NvBlk_SafeRecord", "32 B", "Dataset (4)", "CRC16", "SAFE 진입", "C", "—"],
                             ["NvBlk_VariantCoding", "4 B", "Redundant", "CRC16", "EOL / 0x2E", "C", "C3 AWD"], ["NvBlk_DemPrimary", "1 KB", "Native", "CRC16", "IG OFF", "QM", "—"],
                             ["NvBlk_SecOcFv", "16 B", "Redundant", "CRC32", "주기 (1 h) / IG OFF", "QM", "동기화 요청"]], widths=[3.4, 1.2, 2.2, 1.4, 3.2, 1.2, 3.4])
    D.R("NVM", "eLSD 제어기는 NvM 블록 목록 표의 블록을 지정 관리 형식과 CRC로 구성하고, ASIL 블록은 읽기 후 범위 검사를 수행해야 한다.", "단위 시험 + HIL", "C")
    D.R("NVM", "Fee 영역은 1,000,000회 이상의 블록 쓰기를 15년 수명 동안 보장해야 하며 마모 평준화를 적용해야 한다.", "내구 계산서 + 시험")
    D.R("NVM", "NvBlk_PosOffset이 무효이면 eLSD 제어기는 ACTIVE 진입을 금지하고 DTC C2A62를 저장해야 한다.", "HIL", "C")
    D.h("9.8 타이밍 체인", 2)
    D.p("표는 휠속 수신부터 모터 전류 반영까지의 End-to-End 지연 예산이다. 공급사는 AUTOSAR Timing Extensions로 이벤트 체인을 기술하고 측정 결과를 제출해야 한다.")
    D.table("이벤트 체인 지연 예산 (휠속 → 잠금 토크)", [["구간", "구성 요소", "예산", "누적"], ["CAN 수신 → Com 신호", "CanIf · PduR · Com · E2E", "1.0 ms", "1.0 ms"],
                                                  ["Com → SWC_SignalIf", "RTE (5 ms 태스크 대기 포함)", "5.0 ms", "6.0 ms"], ["SignalIf → LockTqCalc → LsdCoord", "Task_5ms_Asil 내부", "1.2 ms", "7.2 ms"],
                                                  ["→ ClutchCtrl 위치 지령", "Task_1ms_Asil 대기", "1.0 ms", "8.2 ms"], ["위치 제어 → 전류 지령", "CDD_MotorCtrl", "0.1 ms", "8.3 ms"],
                                                  ["기계 응답 (90%)", "모터 · 볼램프 · 클러치", "≤ 110 ms", "≤ 120 ms"]], widths=[4.6, 5.4, 2.6, 3.4])
    D.RT("AR", "타이밍 요구사항", [
        ("휠속 수신부터 위치 지령 갱신까지의 소프트웨어 지연은 10ms 이하여야 한다.", "C", "TRACE32 이벤트 체인 측정"),
        ("공급사는 이벤트 체인을 AUTOSAR Timing Extensions(TIMEX)로 ARXML에 기술해야 한다.", "QM", "ARXML 리뷰"),
        ("ISR(Foc_Isr) 실행 시간은 최악 조건에서 20µs 이하여야 하며 인터럽트 비활성 구간은 5µs 이하여야 한다.", "C", "TRACE32"),
        ("공급사는 정적 WCET 분석 또는 측정 기반 분석 결과를 태스크별로 제출해야 한다.", "QM", "보고서 검토")])
    D.h("9.9 Freedom from Interference", 2)
    D.table("FFI 분석 대상 및 대책", [["간섭 유형", "원인 예", "대책", "검증"], ["메모리", "QM SWC의 잘못된 포인터 쓰기", "MPU 파티션 (OsApp별), 스택 보호", "고장 주입 (MPU 위반)"],
                                   ["타이밍·실행", "QM 태스크 무한 루프, 우선순위 역전", "OS 타이밍 보호, 코어 분리, WdgM Deadline", "고장 주입 (실행 시간 초과)"],
                                   ["정보 교환", "QM 데이터 손상, 지연·반복", "IOC + 범위 검사, 카운터/CRC, 타임아웃", "단위 시험"], ["주변장치", "QM 코드의 레지스터 접근", "Peripheral 보호, CDD 독점 접근", "정적 분석 + 고장 주입"],
                                   ["BSW 공유", "QM 모듈에 의한 공유 BSW 손상", "ASIL BSW(Os, WdgM, E2E, MCAL) 분리 배치", "구성 리뷰"]], widths=[2.4, 4.6, 5.4, 3.6])
    D.RT("SAFE", "FFI 요구사항", [
        ("공급사는 ASIL C와 QM 소프트웨어 간 메모리·타이밍·정보 교환 간섭에 대한 FFI 분석을 수행하고 결과를 안전 사례에 포함해야 한다.", "C", "안전 분석 리뷰"),
        ("QM SWC가 ASIL 파티션 메모리에 쓰기를 시도하면 MPU가 차단하고 ProtectionHook이 SAFE 상태로 천이해야 한다.", "C", "고장 주입 (TRACE32)"),
        ("ASIL 파티션은 QM 파티션 태스크가 정지·지연되어도 정상 동작을 유지해야 한다.", "C", "고장 주입")])
    D.br()

    D.h("9.10 변형 관리 및 보안 BSW", 2)
    D.table("변형 관리 방식", [["항목", "방식", "결정 시점", "비고"], ["차량 변형 (AWD / Off-road / Sport)", "Post-build selectable + 캘리브레이션 세트", "EOL 코딩", "NvBlk_VariantCoding"],
                              ["CAN 매트릭스 변경", "Post-build loadable (Com, PduR, CanIf)", "SW 배포", "System Extract 갱신"], ["진단 사양 변경", "Pre-compile (Dcm, Dem)", "빌드", "Diagnostic Extract"],
                              ["기능 사용 여부 (런치, DRIFT)", "Variation Point (RTE)", "Post-build", "변형별 비활성"]], widths=[4.6, 5, 2.6, 3.8])
    D.RT("AR", "변형·보안 BSW 요구사항", [
        ("차량 변형은 하나의 SW 바이너리로 지원해야 하며 변형별 차이는 Post-build 구성과 캘리브레이션 세트로 처리해야 한다.", "QM", "구성 리뷰"),
        ("Variation Point로 비활성화된 기능의 Runnable은 실행되지 않아야 하며 관련 Dem 이벤트도 비활성이어야 한다.", "QM", "HIL"),
        ("암호 기능은 Csm·CryIf·Crypto Driver(HSM) 계층으로 구현하고 키는 KeyM으로 관리해야 한다.", "QM", "설계 리뷰"),
        ("SecOC 신선도 값은 FvM 모듈로 관리하고 IG OFF 시 NvBlk_SecOcFv에 저장해야 한다.", "QM", "CANoe + HIL"),
        ("보안 이벤트(SecOC 실패, SecurityAccess 실패, 서명 실패)는 IdsM으로 보고해야 한다.", "QM", "보안 시험")])
    D.br()

    # 10 ---------------------------------------------------------------- 보안
    D.h("10 사이버 보안")
    D.RT("SEC", "사이버 보안 요구사항", [
        ("eLSD 제어기는 ESC_Coord 메시지에 SecOC(AES-128 CMAC, 64bit MAC, 신선도 값)를 적용해 검증해야 한다.", "QM", "CANoe + 침투 시험"),
        ("SecOC 검증 실패가 3회 연속 발생하면 해당 메시지를 폐기하고 DTC U1101을 저장해야 한다.", "QM", "CANoe"),
        ("HSM 기반 보안 부팅으로 부트로더와 어플리케이션 서명을 검증해야 한다.", "QM", "보안 시험"),
        ("UDS SecurityAccess는 레벨별 비대칭 키 기반이어야 하며 3회 실패 시 10초간 잠가야 한다.", "QM", "진단기"),
        ("양산 상태에서 디버그 포트와 XCP 쓰기 접근은 잠금되어야 한다.", "QM", "보안 시험"),
        ("암호 키는 HSM 보안 영역에만 저장해야 한다.", "QM", "보안 감사")])

    # 11 ---------------------------------------------------------------- 업데이트·메모리·캘리브레이션
    D.h("11 SW 업데이트 · 메모리 · 캘리브레이션")
    D.RT("UPD", "업데이트·캘리브레이션 요구사항", [
        ("eLSD 제어기는 UDS 재프로그래밍과 OTA 업데이트를 지원하고 A/B 이중 뱅크로 실패 시 이전 SW로 복귀해야 한다.", "QM", "OTA 시험"),
        ("SW 업데이트는 차속 0 km/h, P단, KL30 12.5V 이상에서만 시작해야 하며 업데이트 중 클러치를 개방 상태로 유지해야 한다.", "B", "OTA 시험"),
        ("캘리브레이션 데이터는 어플리케이션과 분리된 영역에 저장하고 서명 검증 후 활성화해야 한다.", "QM", "보안 시험"),
        ("개발 단계에서 XCP on CAN-FD로 측정 50개 신호(1ms 래스터)와 온라인 캘리브레이션을 지원해야 한다.", "QM", "INCA/CANape 측정"),
        ("NvM 쓰기는 IG OFF 후 2초 이내에 완료해야 하며 쓰기 중 전원 차단 시 데이터 일관성을 보장해야 한다.", "QM", "벤치 (전원 차단)")])
    D.br()

    # 12 ---------------------------------------------------------------- 전기/HW
    D.h("12 전기적 인터페이스 및 하드웨어")
    D.fig("l_conn", "eLSD 제어기 커넥터 배치 (하네스 측)", width=13)
    pins = [["커넥터", "핀", "신호", "방향", "전압/전류", "비고"], ["C1", "1", "KL30", "IN", "12V, 40A 피크", "4mm²"], [None, "2", "GND", "—", "40A 피크", "4mm²"],
            ["C2", "1", "MOT_U", "OUT", "40A 피크", "2.5mm²"], [None, "2", "MOT_V", "OUT", "40A 피크", "2.5mm²"], [None, "3", "MOT_W", "OUT", "40A 피크", "2.5mm²"],
            [None, "4", "KL15", "IN", "12V", ""], [None, "5", "CAN1_H (Chassis)", "I/O", "CAN-FD", ""], [None, "6", "CAN1_L (Chassis)", "I/O", "CAN-FD", ""],
            [None, "7", "CAN2_H (PT)", "I/O", "CAN-FD", ""], [None, "8", "CAN2_L (PT)", "I/O", "CAN-FD", ""], [None, "9", "TMR_VCC", "OUT", "5V, 20mA", ""], [None, "10", "TMR_SPI_CS/CLK", "OUT", "5V", "실드"],
            [None, "11", "TMR_SPI_MISO", "IN", "5V", "실드"], [None, "12", "HALL_A", "IN", "5V", ""], [None, "13", "HALL_B", "IN", "5V", ""], [None, "14", "HALL_C", "IN", "5V", ""],
            [None, "15", "HALL_VCC / GND", "—", "5V", ""], [None, "16", "OIL_NTC", "IN", "아날로그", "10kΩ"], [None, "17", "OIL_NTC_GND", "—", "", ""], [None, "18~20", "NC", "—", "", ""]]
    D.table("커넥터 핀 배열", pins, widths=[1.6, 1.2, 4, 1.4, 3, 4.8], merges=[(1, 0, 2, 0), (3, 0, 20, 0)])
    D.table("파워 스테이지 주요 정격", [["항목", "정격", "조건", "비고"], ["모터 상전류 (연속)", "15 A RMS", "주변 105 °C", ""], ["모터 상전류 (피크)", "40 A", "500 ms", "볼램프 급가압"],
                                      ["PWM 주파수", "20 kHz", "센터 정렬", "가청 대역 회피"], ["데드타임", "500 ns ± 10 %", "", "게이트 드라이버 설정"], ["MOSFET RDS(on)", "≤ 2.0 mΩ", "Tj 25 °C", "6개"],
                                      ["상 차단 스위치", "MOSFET 3개 (백투백)", "", "SAFE 시 개방"], ["역극성 보호", "MOSFET", "-14 V 60 s", ""], ["DC 링크 커패시터", "≥ 1,000 µF", "리플 ≥ 10 A RMS", "105 °C 2,000 h"],
                                      ["대기 전력", "≤ 1 mW", "SLEEP", "80 µA @12.6V"]], widths=[4.2, 4, 3.8, 4])
    D.table("핵심 부품 요구사항", [["부품", "요구사항", "등급"], ["MCU", "멀티코어 Lockstep, ≥ 300 MHz, Flash ≥ 4 MB, HSM, MPU, CAN-FD x2", "ASIL D 안전 매뉴얼"],
                                  ["PMIC", "윈도우 WDG, 전압 감시(OV/UV), Safe-state 출력", "ASIL D"], ["게이트 드라이버", "3상, VDS 감시, SPI 진단, 독립 Enable", "ASIL C 이상"],
                                  ["전류 감지", "션트 0.5 mΩ + CSA (대역 ≥ 500 kHz)", "AEC-Q100"], ["CAN-FD 트랜시버", "Partial Networking, 5 Mbps 지원", "AEC-Q100"], ["TMR 위치 센서", "14 bit, SPI CRC, 자기 진단", "ASIL C 이상"]],
            widths=[3.2, 9.4, 3.4])
    D.RT("ELEC", "하드웨어 요구사항", [
        ("eLSD 제어기의 모든 능동 부품은 AEC-Q100/Q101 인증을 받아야 한다.", "QM", "부품 승인"),
        ("MCU는 ASIL D 안전 매뉴얼을 갖춘 멀티코어 Lockstep 제품이어야 하며 HSM과 MPU를 지원해야 한다.", "C", "설계 리뷰"),
        ("MOSFET 접합 온도는 최악 조건(주변 105°C, 40A 500ms)에서 150°C를 넘지 않아야 한다.", "QM", "열 시뮬레이션 + 측정"),
        ("센서 전원(TMR·홀)은 단락 보호를 가져야 하며 12V 단락에 손상되지 않아야 한다.", "B", "벤치"),
        ("하드웨어 안전 메커니즘(과전류 비교기, 와치독 차단 경로)은 소프트웨어와 독립적으로 동작해야 한다.", "C", "회로 리뷰 + 고장 주입"),
        ("PCB는 6층 이상, IPC-6012 Class 3를 만족해야 한다.", "QM", "PCB 승인")])
    D.br()

    # 13 ---------------------------------------------------------------- 환경
    D.h("13 환경 및 EMC")
    D.table("환경 시험 조건 (차동장치 인근 장착)", [["시험", "조건", "판정", "규격"], ["고온 동작", "+105°C (주변), 1,000 h", "기능 정상", "AMS-1300 4.1"], ["저온 동작", "-40°C, 500 h", "기능 정상", "AMS-1300 4.2"],
                                           ["열충격", "-40°C ↔ +125°C, 1,000 cycle", "기능 정상", "AMS-1300 4.4"], ["진동", "랜덤 57.9 m/s² RMS (언스프렁 인근), 축당 22 h", "기능 정상", "AMS-1300 5.1"],
                                           ["기계 충격", "100 g, 6 ms, 축당 10회", "손상 없음", "AMS-1300 5.2"], ["방수·방진", "IP6K9K + IPX7", "침수 없음", "ISO 20653"], ["염수 분무", "720 h (하부 장착)", "부식 등급 2 이하", "AMS-1300 6.1"],
                                           ["화학 내성", "기어 오일, 브레이크액, 융설제", "외관·기능 이상 없음", "AMS-1300 6.3"]], widths=[3, 6, 3.6, 3.4])
    D.RT("ENV", "환경·EMC 요구사항", [
        ("eLSD 제어기는 주변 온도 -40°C ~ +105°C에서 모든 기능을 정격 성능으로 수행해야 한다.", "QM", "환경 챔버"),
        ("eLSD 제어기는 환경 시험 조건 표의 시험 후 기능 및 외관 판정 기준을 만족해야 한다.", "QM", "환경 시험소"),
        ("eLSD 제어기는 AMS-1200 방사·전도 방출 등급 3을 만족해야 한다.", "QM", "EMC 시험소"),
        ("BCI 200mA, ALSE 100V/m 내성 시험에서 기능 상태 A를 만족해야 하며 잠금 토크 변동은 ±50 N·m 이내여야 한다.", "C", "EMC 시험소 (토크 모니터링)"),
        ("eLSD 제어기의 설계 수명은 15년 또는 300,000 km이며 잠금 동작 300만 회를 만족해야 한다.", "QM", "내구 시험")])

    # 14 ---------------------------------------------------------------- 성능
    D.h("14 성능")
    D.table("성능 목표 (C3-Sport)", [["항목", "조건", "목표", "측정"], ["잠금 토크 응답", "0 → 1,500 N·m 스텝", "90% ≤ 120 ms", "토크 다이나모"], ["잠금 해제 응답", "1,500 → 100 N·m", "≤ 80 ms", "토크 다이나모"],
                                  ["정상 상태 정확도", "200 ~ 2,500 N·m", "±10 % / ±50 N·m", "토크 다이나모"], ["μ-split 출발", "μ 0.1 / 0.8, 50% 가속", "0→20 km/h ≤ 4.0 s", "차량 시험"],
                                  ["작동 소음", "정차, 액추에이터 풀스트로크", "≤ 45 dB(A) (실내)", "NVH"], ["트랙 내구", "서킷 20분 3세션", "기능 상실 없음", "차량 시험"]], widths=[3.4, 4.6, 3.8, 4.2])
    D.RT("PERF", "성능 요구사항", [
        ("eLSD 시스템은 μ-split(0.1/0.8) 노면에서 가속 페달 50%로 0→20 km/h를 4.0초 이내에 도달하게 해야 한다.", "QM", "차량 시험"),
        ("액추에이터 작동 소음은 실내 운전석 기준 45 dB(A) 이하여야 한다.", "QM", "NVH 시험"),
        ("서킷 20분 3세션 연속 주행에서 열 보호에 의한 잠금 토크 제한은 허용하되 기능 상실(SAFE 진입)이 없어야 한다.", "QM", "차량 시험"),
        ("잠금 토크 변화에 의한 차체 충격(Clunk)은 주관 평가 7점 이상이어야 한다.", "QM", "차량 평가")])
    D.br()

    # 15 ---------------------------------------------------------------- 생산
    D.h("15 생산 · 서비스 · 품질")
    D.RT("EOL", "생산·서비스·품질 요구사항", [
        ("eLSD 제어기는 EOL에서 일련번호, HW/SW 버전, 변형 코딩을 기록하고 UDS로 읽을 수 있어야 한다.", "QM", "EOL 시험"),
        ("EOL에서 모터 위치 오프셋과 초기 Kiss point를 학습해야 하며 각각 5초 이내에 완료해야 한다.", "QM", "EOL 시험"),
        ("서비스 센터에서 Kiss point 재학습, 마모량 초기화(클러치 교환 시), 액추에이터 시험을 진단기로 수행할 수 있어야 한다.", "QM", "진단기"),
        ("공급사는 Automotive SPICE 4.0 SWE·HWE·SYS·SUP·MAN.3 프로세스에서 CL2 이상을 달성해야 한다.", "QM", "ASPICE 평가"),
        ("공급사는 필드 불량 접수 후 8D 초안을 5 영업일 이내에 제출해야 한다.", "QM", "품질 감사"),
        ("양산 불량률은 출하 기준 10 ppm 이하로 유지해야 한다.", "QM", "품질 실적")])

    # 16 ---------------------------------------------------------------- 검증
    D.h("16 검증 및 납품")
    D.table("검증 환경 매핑", [["검증 환경", "주 대상", "ASPICE 공정", "제출물"], ["단위 시험 (MC/DC)", "ASIL C SW 유닛, CDD", "SWE.4", "커버리지 리포트"], ["SW 통합 시험 (vECU / SIL)", "SWC·RTE·BSW 통합, 타이밍", "SWE.5", "통합 시험 보고서"],
                              ["HIL (고장 주입)", "LOCK, YAW, MODE, COM, DIAG, SAFE, AR", "SWE.6 / SYS.4", "HIL 보고서 + 파형"], ["벤치 / 토크 다이나모", "CLU, ELEC, 하드웨어 안전 메커니즘", "HWE.3 / HWE.4", "측정 보고서"],
                              ["환경·EMC 시험소", "ENV", "HWE.4 / SYS.5", "시험 성적서"], ["차량 시험", "PERF, UC-01~12", "SYS.5", "평가 보고서"]], widths=[3.8, 5.6, 2.8, 3.8])
    D.table("샘플 단계별 납품물", [["단계", "시기", "SW 범위", "필수 납품물"], ["A 샘플", "2027-03", "개방·고정 잠금, CAN", "회로도, SW 아키텍처 초안(SWC·OS), 초기 ARXML"],
                                 ["B 샘플", "2027-08", "전체 기능 + 진단", "HW/SW 요구사항, 추적 매트릭스, ARXML·A2L, HIL 보고서"], ["C 샘플", "2028-01", "안전 메커니즘 + 보안", "FMEDA, 안전 사례 초안, 환경·EMC 성적서"],
                                 ["D 샘플 (PPAP)", "2028-05", "양산 SW", "안전 사례, 침투 시험, ARXML·A2L 최종본, PPAP"]], widths=[2.4, 1.8, 4.2, 7.6])
    D.R("SAFE", "공급사는 ASIL B 이상 요구사항마다 고장 주입 시험을 수행하고 FDTI·FRTI 측정 파형을 제출해야 한다.", "보고서 검토", "C")
    D.R("EOL", "공급사는 각 샘플 단계에서 요구사항–설계(ARXML 요소 포함)–시험 간 양방향 추적성 매트릭스를 제출해야 한다.", "납품물 검토")

    D.h("부록 A. 요구사항 변경 절차", 1)
    D.bullets(["OEM 또는 공급사가 변경 요청(CR)을 발행한다.", "공급사는 10 영업일 이내에 영향 분석(일정, 비용, 안전, 영향받는 ARXML·SWC·시험)을 회신한다.",
               "CCB가 승인하면 본 문서를 개정하고, 공급사는 추적성 도구에서 영향받는 하위 산출물을 재검토(Suspect 해제)한다."])
    D.h("부록 B. 준수 여부 회신 예", 1)
    D.table("준수 여부 회신 예", [["요구사항 ID", "회신", "공급사 요구사항 ID", "비고"], ["REQ-LOCK-001", "C", "SYS-LOCK-0001, SWE-LOCK-0004", ""], ["REQ-CLU-001", "PC", "SYS-CLU-0001", "90% 도달 135ms 예상, 모터 사양 상향 시 120ms"],
                                 ["REQ-AR-001", "C", "SWE-AR-0001", "R21-11 BSW 사용"], ["REQ-AR-014", "C", "SWE-AR-0014", "OS SC3, 2코어 구성"], ["REQ-SAFE-002", "C", "SYS-SAFE-0002, HWE-SAFE-0004", ""]], widths=[3.2, 1.4, 5.6, 5.8])
    D.h("부록 C. 신호 목록 요약", 1)
    D.table("eLSD 관련 신호", [["신호", "메시지", "방향", "주기", "ASIL", "사용 SWC"], ["WhlSpd_FL/FR/RL/RR", "ESC_WhlSpd", "RX", "10 ms", "C", "SWC_SignalIf → LockTqCalc"],
                              ["ESC_LsdTqMax", "ESC_Coord", "RX", "10 ms", "C", "SWC_LsdCoord, SafetyMon"], ["ESC_Active / ESC_Off", "ESC_Coord", "RX", "10 ms", "C", "SWC_LsdCoord"],
                              ["YawRate / LatAcc", "ESC_VehDyn", "RX", "10 ms", "B", "SWC_LockTqCalc"], ["TqRearAxle", "VCU_Torque", "RX", "10 ms", "B", "SWC_LockTqCalc"], ["DrvMode", "IDM_DrvMode", "RX", "100 ms", "QM", "SWC_ModeMgr"],
                              ["LSD_TqAct", "LSD_Status_01", "TX", "10 ms", "C", "SWC_SignalIf"], ["LSD_State", "LSD_Status_01", "TX", "10 ms", "C", "SWC_ModeMgr"], ["LSD_ClutchTemp", "LSD_Status_02", "TX", "100 ms", "QM", "SWC_ThermWear"]],
            widths=[3.6, 3, 1.4, 1.6, 1.2, 5.2])
    D.h("부록 D. 기준 잠금 토크 맵 (SPORT)", 1)
    dn = [5, 10, 20, 40, 60, 80, 100, 140, 180, 220]
    rows = [["차속 \\ Δn (rpm)"] + [str(x) for x in dn]]
    for v, g in [(0, 1.15), (20, 1.0), (40, 0.95), (80, 0.85), (120, 0.75), (160, 0.62), (200, 0.5)]:
        rows.append([f"{v} km/h"] + [f"{min(2500, g * 7.0 * max(0, x - 5) ** 1.35):.0f}" for x in dn])
    D.table("목표 잠금 토크 (N·m), SPORT 모드, 구동 토크 피드포워드 제외", rows, widths=[2.6] + [1.34] * 10)
    D.h("부록 E. 주요 캘리브레이션 파라미터", 1)
    D.table("캘리브레이션 파라미터", [["파라미터", "기본값", "범위", "단위", "비고"], ["Lock_DnDeadBand", "5", "2 ~ 15", "rpm", "Δn 불감대"], ["Lock_FfRatioMax", "0.4", "0 ~ 0.6", "—", "피드포워드 비율"],
                                     ["Lock_RateUp", "20000", "5000 ~ 30000", "N·m/s", "증가율"], ["Lock_RateDown", "40000", "10000 ~ 60000", "N·m/s", "감소율"], ["Lock_ParkLimit", "50", "0 ~ 100", "N·m", "주차 선회"],
                                     ["Yaw_OsThresh", "5", "2 ~ 10", "deg/s", "오버스티어 임계"], ["Launch_Preload", "600", "0 ~ 1000", "N·m", "런치 프리로드"], ["Therm_LimStart", "130", "110 ~ 150", "°C", "★ 제한 시작"],
                                     ["Therm_LimMin", "20", "0 ~ 40", "%", "★ 최소 허용"], ["Therm_Cutoff", "175", "160 ~ 190", "°C", "★ 0% 온도"], ["Safe_TqPlausDiff", "300", "200 ~ 500", "N·m", "★ 타당성 임계"],
                                     ["Safe_TqPlausTime", "50", "20 ~ 100", "ms", "★ 타당성 시간"], ["Safe_UnintLock", "200", "100 ~ 300", "N·m", "★ 의도치 않은 잠금"], ["Kiss_Range", "12 ~ 28", "—", "%", "학습 허용 범위"],
                                     ["Esc_TimeoutLim", "200", "0 ~ 300", "N·m", "★ ESC 협조 무효 시"]], widths=[4, 2, 3, 2.4, 4.6])
    D.h("부록 F. 요구사항–검증 환경 매핑 요약", 1)
    env = {"LOCK": "HIL, 차량", "YAW": "HIL, 차량", "MODE": "HIL, CANoe", "CLU": "벤치(토크 다이나모)", "THERM": "벤치, HIL", "SENS": "HIL, 벤치", "COM": "CANoe",
           "DIAG": "진단기, HIL", "SAFE": "HIL 고장 주입, 벤치", "AR": "구성 리뷰, TRACE32, ARXML 검증", "NVM": "HIL, 내구", "SEC": "보안·침투 시험", "UPD": "OTA, 벤치",
           "ELEC": "벤치, 회로 리뷰", "ENV": "환경·EMC 시험소", "PERF": "차량 시험", "EOL": "EOL, 감사"}
    rows = [["도메인", "요구사항 수", "주 검증 환경"]] + [[k, str(D.cnt.get(k, 0)), v] for k, v in env.items()] + [["합계", str(D.reqs), ""]]
    D.table("도메인별 요구사항 수와 검증 환경", rows, widths=[3.6, 2.6, 9.8])
    D.p("요구사항 수는 개정 1.0 기준이며 개정 시 공급사의 추적성 도구에서 자동 집계한 값으로 갱신한다.")
    D.h("부록 G. ASPICE 작업 산출물 제출 목록", 1)
    D.table("작업 산출물 제출 목록", [["공정", "작업 산출물", "B 샘플", "C 샘플", "D 샘플"], ["SYS.2", "시스템 요구사항 명세, 고객 요구사항 추적 매트릭스", "O", "O", "O"],
                                    ["SYS.3", "시스템 아키텍처 (HW/SW 할당)", "O", "O", "O"], ["SYS.4 / SYS.5", "시스템 통합·검증 명세 및 결과", "△", "O", "O"],
                                    ["HWE.1 / HWE.2", "HW 요구사항 명세, HW 설계 (회로도, 블록도)", "O", "O", "O"], ["HWE.3 / HWE.4", "HW 검증 명세 및 결과", "△", "O", "O"],
                                    ["SWE.1", "SW 요구사항 명세 (AUTOSAR 요구 포함)", "O", "O", "O"], ["SWE.2", "SW 아키텍처 (SWC·OS·BSW, ARXML)", "O", "O", "O"],
                                    ["SWE.3 / SWE.4", "상세 설계, 단위 검증 결과 (MC/DC)", "△", "O", "O"], ["SWE.5 / SWE.6", "SW 통합·검증 결과", "△", "O", "O"],
                                    ["SUP.8 / SUP.10", "형상 관리 기록, 변경 요청 기록", "O", "O", "O"], ["안전 (ISO 26262)", "안전 계획, FMEDA, FFI 분석, 안전 사례", "△", "O", "O"]], widths=[3.2, 8, 1.6, 1.6, 1.6])
    D.p("O: 완료본 제출, △: 초안 제출. 모든 산출물은 요구사항 ID 기준으로 상호 추적 가능해야 한다.")
    D.h("부록 H. 미결 사항", 1)
    D.table("미결 사항 (TBD)", [["번호", "항목", "담당", "목표 일자"], ["TBD-01", "DRIFT 모드 잠금 프리로드 값", "OEM 차량성능팀", "2027-02"], ["TBD-02", "BSW 버전(R20-11 / R22-11) 최종 확정", "OEM SW 플랫폼팀", "2026-12"],
                               ["TBD-03", "SecOC 적용 메시지 범위 확대 여부 (VCU_Torque)", "OEM 차량보안팀", "2026-12"]], widths=[1.8, 8.4, 3.4, 2.4])
    p = OUT / f"CRS_eLSD_ECU_rev{rev}.docx"
    d.save(p)
    print(f"requirements: {D.reqs}, figures: {D.n['fig']}, tables: {D.n['tbl']}")
    return p


if __name__ == "__main__":
    out = build("1.0")
    print(out)
    pdf = to_pdf(out)
    if pdf:
        print(pdf)
