"""Generate ecualm/data/hw_arch_bldc.json — the HWE.2 block diagram of the BLDC position ECU used in
SRS_BLDC_Full (TC364 + DRV8305 + TLF35584 + TJA1043 + AS5047), with interfaces, HWE.3 test cases
and bench results including fault-injection waveforms.

Block titles match the SYS.3 elements produced by `derive SYS2 SYS3`, so importing this file after
deriving merges into the same blocks instead of duplicating them.

  python samples/make_hw_arch.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "ecualm" / "data" / "hw_arch_bldc.json"


def r(v, n=3):
    return round(v, n)


def overcurrent_wave():
    xs = [r(-10 + k * 0.25, 2) for k in range(161)]           # µs
    t_trip, t_off = 4.0, 6.2
    cur, comp, en = [], [], []
    for t in xs:
        if t < 0:
            i = 8 + 0.4 * math.sin(t * 1.3)
        elif t < t_off:
            i = 8 + 3.0 * t
        else:
            i = (8 + 3.0 * t_off) * math.exp(-(t - t_off) / 2.0)
        cur.append(r(i, 2))
        comp.append(1 if t >= t_trip and i >= 1.0 else 0)
        en.append(0 if t >= t_off else 1)
    return {"x_unit": "µs", "x": xs,
            "panels": [{"title": "상전류", "unit": "A", "series": [{"name": "상전류 U (션트)", "y": cur}],
                        "thresholds": [{"y": 20, "label": "비교기 임계 20A"}]},
                       {"title": "디지털", "kind": "digital", "series": [{"name": "COMP_OUT", "y": comp}, {"name": "EN_GATE", "y": en}]}],
            "markers": [{"x": 0, "label": "단락 주입"}, {"x": t_trip, "label": "비교기 트립"}, {"x": t_off, "label": "EN_GATE 차단"}]}


def watchdog_wave():
    xs = [r(k * 0.5, 1) for k in range(161)]                 # ms
    t_stop, t_err, t_ss = 30.0, 40.5, 41.2
    wdi, err, ss1, cur = [], [], [], []
    for t in xs:
        wdi.append((int(t // 5) % 2) if t < t_stop else 0)
        err.append(0 if t >= t_err else 1)                  # ERR is active low
        ss1.append(0 if t >= t_ss else 1)
        cur.append(r(6 + 0.3 * math.sin(t) if t < t_ss else 6 * math.exp(-(t - t_ss) / 1.5), 2))
    return {"x_unit": "ms", "x": xs,
            "panels": [{"title": "상전류", "unit": "A", "series": [{"name": "모터 상전류", "y": cur}]},
                       {"title": "디지털", "kind": "digital", "series": [{"name": "WDI", "y": wdi}, {"name": "ERR (active low)", "y": err},
                                                                          {"name": "SS1 Safe State", "y": ss1}]}],
            "markers": [{"x": t_stop, "label": "WDI 정지 (SW 행)"}, {"x": t_ss, "label": "Shut-off"}]}


DATA = {
    "format": "ecualm-arch/1",
    "canvas": "HWE2",
    "note": "BLDC 위치제어 ECU HW 블록도 (SRS_BLDC_Full rev A 기준 샘플)",
    "blocks": [
        {"key": "pmic", "title": "전원 IC (PMIC) 및 전원 회로", "domain": "PWR", "asil": "B",
         "text": "KL30에서 5V/3.3V 레일을 생성하고 윈도우 와치독·전압 감시로 Shut-off Path 를 제어한다.",
         "hw": {"part_number": "Infineon TLF35584", "interfaces": "SPI(WDG), WDI, ERR, SS1/SS2, VDD 5V/3.3V",
                "safety_mechanism": "윈도우 와치독 10ms + OV/UV 감시 → SS1 Shut-off"},
         "layout": {"x": 30, "y": 30}, "refines_title": ["전원 IC (PMIC) 및 전원 회로"]},
        {"key": "can", "title": "CAN 트랜시버", "domain": "COM", "asil": "QM",
         "text": "차량 CAN(500kbps)과 MCU MCMCAN 사이의 물리 계층. WUP 로 기동한다.",
         "hw": {"part_number": "NXP TJA1043", "interfaces": "CANH/CANL, TXD/RXD, STB, EN, INH",
                "safety_mechanism": "TXD dominant timeout, 버스 오프 복구"},
         "layout": {"x": 30, "y": 330}, "refines_title": ["CAN 트랜시버"]},
        {"key": "mcu", "title": "TC364 MCU", "domain": "GEN", "asil": "B",
         "text": "FOC 전류 제어(100µs)·위치 제어(1ms)·진단을 수행하는 주 MCU.",
         "hw": {"part_number": "Infineon AURIX TC364 (SAK-TC364DP-64F300F)", "interfaces": "GTM PWM 20kHz, EVADC, QSPI0/1, MCMCAN, DAP",
                "safety_mechanism": "Lockstep 코어 + SMU + ECC"},
         "layout": {"x": 330, "y": 180}, "refines_title": ["TC364 MCU"], "controlled_by_title": ["SWC_PowerMgr"]},
        {"key": "gd", "title": "게이트 드라이버 IC", "domain": "MOT", "asil": "B",
         "text": "PWM 6채널로 3상 MOSFET 인버터를 구동하고 VDS 감시 결과를 nFAULT 로 알린다.",
         "hw": {"part_number": "TI DRV8305", "interfaces": "SPI, PWM x6, EN_GATE, nFAULT",
                "safety_mechanism": "VDS 과전류 감시, 게이트 UVLO, nFAULT"},
         "layout": {"x": 640, "y": 30}, "refines_title": ["게이트 드라이버 IC"], "controlled_by_title": ["CDD_BldcDrv"]},
        {"key": "shut", "title": "과전류 하드웨어 차단 경로 (Shut-off Path)", "domain": "SAFE", "asil": "B",
         "text": "상 전류 20A 이상을 비교기로 검출해 10µs 이내에 EN_GATE 를 차단한다 (SW 개입 없음).",
         "hw": {"part_number": "션트 1mΩ + 비교기 + EN_GATE 래치", "interfaces": "션트 전압 → 비교기 → EN_GATE, EVADC",
                "safety_mechanism": "20A 비교기 → 10µs 이내 게이트 차단"},
         "layout": {"x": 640, "y": 330}, "refines_title": ["과전류 하드웨어 차단 경로 (Shut-off Path)"]},
        {"key": "motor", "title": "BLDC 모터 및 위치 센서", "domain": "MOT", "asil": "B",
         "text": "3상 BLDC 모터와 홀 센서 3개, AS5047 절대 각도 센서(14bit).",
         "hw": {"part_number": "BLDC 3상 + 홀 x3 + AS5047", "interfaces": "U/V/W, HALL_A/B/C, SPI(AS5047)",
                "safety_mechanism": "센서 이중화 (홀 / 절대각)"},
         "layout": {"x": 940, "y": 180}, "refines_title": ["BLDC 모터 및 위치 센서"]},
    ],
    "interfaces": [
        {"key": "if_pwr", "name": "VDD 3.3V / 5V", "from": "pmic", "to": "mcu", "signal_class": "power", "signals": ["VDD_3V3", "VDD_5V"]},
        {"key": "if_wdg", "name": "와치독 SPI + WDI", "from": "mcu", "to": "pmic", "signal_class": "spi", "signals": ["QSPI1", "WDI"]},
        {"key": "if_ss1", "name": "SS1 Safe State", "from": "pmic", "to": "gd", "signal_class": "digital", "signals": ["SS1"]},
        {"key": "if_can", "name": "CAN TXD/RXD", "from": "can", "to": "mcu", "signal_class": "can", "signals": ["TXD", "RXD", "STB"]},
        {"key": "if_pwm", "name": "PWM x6 + SPI", "from": "mcu", "to": "gd", "signal_class": "pwm", "signals": ["GTM_TOM0_CH0..5", "QSPI0"]},
        {"key": "if_uvw", "name": "U/V/W 3상 출력", "from": "gd", "to": "motor", "signal_class": "mech", "signals": ["U", "V", "W"]},
        {"key": "if_pos", "name": "HALL + AS5047 SPI", "from": "motor", "to": "mcu", "signal_class": "digital", "signals": ["HALL_A/B/C", "QSPI2"]},
        {"key": "if_cur", "name": "상전류 (션트)", "from": "motor", "to": "shut", "signal_class": "analog", "signals": ["SHUNT_U/V/W"]},
        {"key": "if_en", "name": "EN_GATE 차단", "from": "shut", "to": "gd", "signal_class": "digital", "signals": ["EN_GATE"]},
        {"key": "if_adc", "name": "전류 ADC", "from": "shut", "to": "mcu", "signal_class": "analog", "signals": ["EVADC_G0CH0..2"]},
    ],
    "tests": [
        {"key": "tc_oc", "type": "HWE3_TC", "title": "과전류 하드웨어 차단 반응 시간 (20A, 10µs)", "domain": "SAFE",
         "text": "[고장주입] 상 U 를 GND 로 단락하고 비교기 트립과 EN_GATE 차단까지의 시간을 오실로스코프로 측정한다. 10µs 이내여야 한다.",
         "kind": "fault_injection", "tool": "오실로스코프 4ch + 단락 지그", "pass_criteria": "단락 주입 → EN_GATE 차단 < 10µs",
         "verifies": ["shut", "if_en"]},
        {"key": "tc_wdg", "type": "HWE3_TC", "title": "PMIC 윈도우 와치독 → Shut-off Path 차단", "domain": "SAFE",
         "text": "[고장주입] WDI 서비스를 중단(SW 행 모사)하고 PMIC 가 SS1 으로 게이트를 차단하는지, 차단까지의 시간을 측정한다.",
         "kind": "fault_injection", "tool": "TRACE32 브레이크 + 오실로스코프", "pass_criteria": "WDI 정지 → Shut-off < 50ms",
         "verifies": ["pmic", "if_ss1"]},
        {"key": "tc_can", "type": "HWE3_TC", "title": "CAN 버스 단락 후 복구 시간", "domain": "COM",
         "text": "[설계검증] CANH-CANL 단락을 1s 인가 후 해제하고 통신 복구까지의 시간을 측정한다. 50ms 이내여야 한다.",
         "kind": "design_verification", "tool": "CANoe + 단락 박스", "pass_criteria": "복구 ≤ 50ms", "verifies": ["can", "if_can"]},
        {"key": "tc_mcu", "type": "HWE3_TC", "title": "TC364 전원 레일·클럭 설계 검증", "domain": "PWR",
         "text": "[설계검증] VDD 3.3V/5V 리플, 리셋 타이밍, 20MHz 크리스털 기동 시간을 측정해 데이터시트 이내인지 확인한다.",
         "kind": "design_verification", "tool": "오실로스코프 + 파워서플라이", "pass_criteria": "모든 측정 항목 데이터시트 이내",
         "verifies": ["mcu", "if_pwr"]},
    ],
    "results": [
        {"tc": "tc_oc", "status": "PASS", "run_id": "BENCH-2026-10-17-03", "tool": "Keysight DSOX4024A",
         "metrics": {"reaction": 6.2, "limit": 10, "unit": "µs", "label": "단락 주입 → EN_GATE 차단"}, "waveform": overcurrent_wave()},
        {"tc": "tc_wdg", "status": "PASS", "run_id": "HIL-NIGHTLY-1288", "tool": "TRACE32 + NI DAQ",
         "metrics": {"reaction": 11.2, "limit": 50, "unit": "ms", "label": "WDI 정지 → Shut-off"}, "waveform": watchdog_wave()},
        {"tc": "tc_can", "status": "FAIL", "run_id": "BENCH-2026-10-16-11", "tool": "CANoe 17",
         "metrics": {"reaction": 55, "limit": 50, "unit": "ms", "label": "단락 해제 → 통신 복구"},
         "note": "복구 55ms 측정 (요구 ≤ 50ms). TJA1043 STB 핀 처리 확인 필요"},
    ],
}

if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(DATA, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")
