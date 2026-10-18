"""Project configuration: work item types, link rules, ID format, classifier dictionaries.

`ecualm init` writes these defaults to alm.json in the project folder; edit that file
to adapt types, prefixes, keywords and rules to your project. Values in alm.json
override the defaults below key by key.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

DEFAULT_CONFIG: dict = {
    "project": "ECU_PROJ",
    # ID format. Available fields: {prefix} {domain} {n}. IDs are never reused.
    # Set to "{prefix}-{n:05d}" if you prefer IDs without a domain part.
    "id_format": "{prefix}-{domain}-{n:04d}",
    "id_format_no_domain": "{prefix}-{n:04d}",
    # Work item types. aspice = process, polarion = recommended Polarion type name.
    "types": {
        "CRS":     {"prefix": "CRS",     "name": "Customer Requirement",  "aspice": "SYS.1", "polarion": "customerRequirement", "requirement": True},
        "SYS2":    {"prefix": "SYS2",    "name": "System Requirement",    "aspice": "SYS.2", "polarion": "systemRequirement",   "requirement": True},
        "SYS3":    {"prefix": "SYS3",    "name": "System Arch Element",   "aspice": "SYS.3", "polarion": "sysArchElement",      "requirement": False},
        "HSI":     {"prefix": "HSI",     "name": "HW-SW Interface",       "aspice": "SYS.3", "polarion": "hsiSpec",             "requirement": True},
        "SWE1":    {"prefix": "SWE1",    "name": "Software Requirement",  "aspice": "SWE.1", "polarion": "softwareRequirement", "requirement": True},
        "SWE2":    {"prefix": "SWE2",    "name": "SW Arch Element",       "aspice": "SWE.2", "polarion": "swArchElement",       "requirement": False},
        "SWE3":    {"prefix": "SWE3",    "name": "SW Unit Design",        "aspice": "SWE.3", "polarion": "swUnitDesign",        "requirement": False},
        "SWE4_TC": {"prefix": "SWE4-TC", "name": "SW Unit Test Case",     "aspice": "SWE.4", "polarion": "swUnitTestCase",      "requirement": False},
        "SWE5_TC": {"prefix": "SWE5-TC", "name": "SW Integration TC",     "aspice": "SWE.5", "polarion": "swIntTestCase",       "requirement": False},
        "SWE6_TC": {"prefix": "SWE6-TC", "name": "SW Verification TC",    "aspice": "SWE.6", "polarion": "swTestCase",          "requirement": False},
        "SYS4_TC": {"prefix": "SYS4-TC", "name": "System Integration TC", "aspice": "SYS.4", "polarion": "sysIntTestCase",      "requirement": False},
        "SYS5_TC": {"prefix": "SYS5-TC", "name": "System Verification TC","aspice": "SYS.5", "polarion": "sysTestCase",         "requirement": False},
        # Document structure items (keep the document readable like a LiveDoc)
        "HDG":     {"prefix": "HDG",     "name": "Heading",               "aspice": "",      "polarion": "heading",             "requirement": False},
        "INFO":    {"prefix": "INFO",    "name": "Information",           "aspice": "",      "polarion": "information",         "requirement": False},
        "TBL":     {"prefix": "TBL",     "name": "Table",                 "aspice": "",      "polarion": "table",               "requirement": False},
        "FIG":     {"prefix": "FIG",     "name": "Figure",                "aspice": "",      "polarion": "figure",              "requirement": False},
    },
    # Allowed links: src --role--> dst  (src depends on dst; a change in dst makes the link suspect)
    "link_rules": [
        {"src": "SYS2",    "role": "derives",    "dst": ["CRS"]},
        {"src": "SYS3",    "role": "satisfies",  "dst": ["SYS2"]},
        {"src": "HSI",     "role": "satisfies",  "dst": ["SYS2"]},
        {"src": "SWE1",    "role": "refines",    "dst": ["SYS2"]},
        {"src": "SWE1",    "role": "uses",       "dst": ["HSI"]},
        {"src": "SWE2",    "role": "allocates",  "dst": ["SWE1"]},
        {"src": "SWE3",    "role": "refines",    "dst": ["SWE2"]},
        {"src": "SWE4_TC", "role": "verifies",   "dst": ["SWE3"]},
        {"src": "SWE5_TC", "role": "verifies",   "dst": ["SWE2"]},
        {"src": "SWE6_TC", "role": "verifies",   "dst": ["SWE1"]},
        {"src": "SYS4_TC", "role": "verifies",   "dst": ["SYS3", "HSI"]},
        {"src": "SYS5_TC", "role": "verifies",   "dst": ["SYS2"]},
        {"src": "*",       "role": "relates",    "dst": ["*"]},
    ],
    # Audit coverage rules. upstream: the item must link to one of these types with this role.
    # downstream: some item of these types must link to this item with this role.
    "coverage_rules": [
        {"type": "SYS2", "direction": "upstream",   "role": "derives",   "types": ["CRS"],     "only_if_exists": True, "severity": "error", "msg": "SYS.2 가 고객 요구사항(SYS.1)에서 도출되지 않음"},
        {"type": "SWE1", "direction": "upstream",   "role": "refines",   "types": ["SYS2"],    "severity": "error", "msg": "SWE.1 이 시스템 요구사항(SYS.2)과 연결되지 않음 (고아 요구사항)"},
        {"type": "SWE1", "direction": "downstream", "role": "allocates", "types": ["SWE2"],    "only_if_exists": True, "severity": "error", "msg": "SWE.1 이 아키텍처 요소(SWE.2)에 할당되지 않음"},
        {"type": "SYS2", "direction": "downstream", "role": "verifies",  "types": ["SYS5_TC"], "only_if_exists": True, "severity": "warn",  "msg": "SYS.2 를 검증하는 시스템 시험(SYS.5) 없음"},
        {"type": "SWE1", "direction": "downstream", "role": "verifies",  "types": ["SWE6_TC"], "only_if_exists": True, "severity": "warn",  "msg": "SWE.1 을 검증하는 SW 검증 TC(SWE.6) 없음"},
        {"type": "SWE2", "direction": "downstream", "role": "verifies",  "types": ["SWE5_TC"], "only_if_exists": True, "severity": "warn",  "msg": "SWE.2 를 검증하는 통합 TC(SWE.5) 없음"},
        {"type": "HSI",  "direction": "downstream", "role": "verifies",  "types": ["SYS4_TC"], "only_if_exists": True, "severity": "warn",  "msg": "HSI 항목을 검증하는 시스템 통합 TC(SYS.4) 없음"},
    ],
    # ASPICE stages shown in the UI (left-to-right on the V). `next` = stages this one can be deployed to.
    "stages": [
        {"id": "SYS1", "aspice": "SYS.1", "name": "고객 요구사항",       "short": "CRS",  "types": ["CRS"],           "next": ["SYS2"],                 "side": "spec"},
        {"id": "SYS2", "aspice": "SYS.2", "name": "시스템 요구사항",     "short": "SRS",  "types": ["SYS2"],          "next": ["SYS3", "SWE1", "SYS5"], "side": "spec"},
        {"id": "SYS3", "aspice": "SYS.3", "name": "시스템 아키텍처·HSI", "short": "SAD",  "types": ["SYS3", "HSI"],   "next": ["SWE1", "SYS4"],         "side": "spec"},
        {"id": "SWE1", "aspice": "SWE.1", "name": "SW 요구사항",         "short": "SWRS", "types": ["SWE1"],          "next": ["SWE2", "SWE6"],         "side": "spec"},
        {"id": "SWE2", "aspice": "SWE.2", "name": "SW 아키텍처",         "short": "SWAD", "types": ["SWE2"],          "next": ["SWE3", "SWE5"],         "side": "spec"},
        {"id": "SWE3", "aspice": "SWE.3", "name": "SW 상세설계",         "short": "SWDD", "types": ["SWE3"],          "next": ["SWE4"],                 "side": "spec"},
        {"id": "SWE4", "aspice": "SWE.4", "name": "유닛 검증",           "short": "UT",   "types": ["SWE4_TC"],       "next": [],                       "side": "verify", "verifies": "SWE3"},
        {"id": "SWE5", "aspice": "SWE.5", "name": "SW 통합 검증",        "short": "IT",   "types": ["SWE5_TC"],       "next": [],                       "side": "verify", "verifies": "SWE2"},
        {"id": "SWE6", "aspice": "SWE.6", "name": "SW 검증",             "short": "SWT",  "types": ["SWE6_TC"],       "next": [],                       "side": "verify", "verifies": "SWE1"},
        {"id": "SYS4", "aspice": "SYS.4", "name": "시스템 통합 검증",    "short": "SIT",  "types": ["SYS4_TC"],       "next": [],                       "side": "verify", "verifies": "SYS3"},
        {"id": "SYS5", "aspice": "SYS.5", "name": "시스템 검증",         "short": "SYT",  "types": ["SYS5_TC"],       "next": [],                       "side": "verify", "verifies": "SYS2"},
    ],
    # Section names used when a stage document is laid out by domain (PAM 4.0 structure)
    "domain_names": {"PWR": "전원·운용 모드", "MOT": "모터 제어·캘리브레이션", "COM": "통신", "DIAG": "진단", "SAFE": "기능 안전·고장 검출",
                      "ENV": "환경·EMC", "MECH": "기구", "ARCH": "SW 아키텍처 제약", "TIME": "타이밍·성능", "NVM": "비휘발성 메모리",
                      "SEC": "보안", "MFG": "제조·EOL", "HSI": "HW-SW 인터페이스", "GEN": "일반"},
    # When a native ID carries a domain segment (REQ-CTRL-012), map it to our domain codes
    "native_domain_map": {"PWR": "PWR", "ENV": "ENV", "MECH": "MECH", "MOT": "MOT", "SAFE": "SAFE", "ARCH": "ARCH", "CTRL": "MOT", "CAL": "MOT",
                          "MODE": "PWR", "COM": "COM", "CAN": "COM", "DIAG": "DIAG", "UDS": "DIAG", "FDET": "SAFE", "NVM": "NVM", "UPD": "SEC",
                          "SEC": "SEC", "TIME": "TIME", "STAT": "DIAG", "EOL": "MFG", "MFG": "MFG", "ELEC": "PWR", "HSI": "HSI", "HW": "MECH", "SW": "GEN"},
    # Section titles that decide the level in an integrated SRS (strong hint)
    "level_section_hints": {"SYS2": ["시스템 요구사항", "system requirement", "하드웨어 요구사항", "기구", "환경"],
                            "SWE1": ["소프트웨어 요구사항", "software requirement", "SW 요구사항"]},
    # SYS.3 system elements a SYS.2 requirement of a domain is allocated to (derive SYS2 → SYS3)
    "sys3_allocation": {
        "PWR":  ["전원 IC (PMIC) 및 전원 회로", "TC364 MCU"],
        "MOT":  ["BLDC 모터 및 위치 센서", "게이트 드라이버 IC", "TC364 MCU"],
        "COM":  ["CAN 트랜시버", "TC364 MCU"],
        "DIAG": ["TC364 MCU"],
        "SAFE": ["TC364 MCU", "과전류 하드웨어 차단 경로 (Shut-off Path)"],
        "ENV":  ["PCB 및 하우징"],
        "MECH": ["기구부 및 커넥터"],
        "GEN":  ["TC364 MCU"],
    },
    # SWE.2 AUTOSAR components a SWE.1 requirement of a domain is allocated to (derive SWE1 → SWE2)
    "swe2_allocation": {
        "MOT":  [{"name": "SWC_PosCtrl", "layer": "ASW"}, {"name": "CDD_BldcDrv", "layer": "CDD", "if": ["PWM", "전류", "ADC", "GTM", "EVADC", "1ms", "100us"]}],
        "COM":  [{"name": "SWC_ComHandler", "layer": "ASW"}, {"name": "BSW_Com", "layer": "BSW"}],
        "DIAG": [{"name": "SWC_DiagMgr", "layer": "ASW"}, {"name": "BSW_Dcm_Dem", "layer": "BSW"}],
        "SAFE": [{"name": "SWC_SafetyMonitor", "layer": "ASW"}],
        "PWR":  [{"name": "SWC_PowerMgr", "layer": "ASW"}, {"name": "BSW_EcuM", "layer": "BSW"}],
        "GEN":  [{"name": "SWC_AppMain", "layer": "ASW"}],
    },
    # Requirement sentence detection (regex, case-insensitive)
    "requirement_patterns": [
        r"야\s*(한다|함|합니다|하며|하고|하는)",
        r"(할|될)\s*것\b",
        r"(가진다|갖는다|제공한다|지원한다|수행한다|출력한다|전송한다|송신한다|판단한다|검출한다|저장한다|설정한다|진입한다|제어한다|유지한다|차단한다|천이한다|금지한다|허용한다)\s*[.。]?\s*$",
        r"\b(shall|must)\b",
        r"\b(should|will)\b\s+\w+",
    ],
    # Sentences matching these are always information, never requirements
    "info_patterns": [r"^\s*(본|이)\s*(문서|규격|사양서)", r"^\s*(this|the present)\s+document", r"^\s*(적용\s*규격|참고\s*문서|약어|용어)\s*[:：]",
                      r"^\s*(예|예시|참고|note|e\.g\.)\s*[:：)]", r"^\s*['\"‘“]", r"^\s*(ASIL\s+\S+\s*·\s*)?(검증|근거|비고|출처)\s*[:：]",
                      r"^\s*(표|그림|Table|Figure)\s*\d+"],
    # Sentences starting like this depend on the previous one -> flagged after atomic split
    "anaphora_words": ["이때", "이 때", "이 경우", "그 결과", "그 후", "단,", "또한", "In this case", "Then"],
    # Native requirement IDs that may already exist in customer/legacy documents
    "native_id_pattern": r"\b([A-Z][A-Z0-9]{1,10}(?:[-_][A-Z0-9]{1,10}){0,3}[-_]\d{1,6})\b",
    # SYS.2 vs SWE.1 keyword scoring (integrated SRS split)
    "level_keywords": {
        "SYS2": ["전압", "작동 전압", "동작 전압", "암전류", "소비 전류", "EMC", "ESD", "내성", "온도 범위", "작동 온도", "보관 온도",
                  "진동", "충격", "방수", "IP6", "하우징", "커넥터", "기구", "중량", "치수", "스트로크", "토크", "소음", "내구",
                  "수명", "사이클", "환경", "부하", "차량", "시스템은", "제어기는", "액추에이터는", "ECU는", "PCB", "하드웨어"],
        "SWE1": ["소프트웨어", "SW는", "주기", "태스크", "Task", "ms", "μs", "us 주기", "알고리즘", "PID", "필터", "디바운스",
                  "debounce", "CAN 신호", "메시지", "Timeout", "타임아웃", "Alive", "CRC", "DTC", "UDS", "DID", "0x", "세션",
                  "NvM", "EEPROM", "저장", "상태 머신", "상태로 천이", "천이", "플래그", "카운터", "PWM 듀티", "듀티", "ADC",
                  "샘플링", "계산", "보정", "학습", "Homing", "영점", "프로파일", "RTE", "SWC", "CDD", "BSW"],
    },
    # Domain tags used inside IDs and for filtering
    "domain_keywords": {
        "PWR":  ["전압", "전원", "저전압", "과전압", "암전류", "소비 전류", "배터리", "IG", "슬립", "Sleep", "웨이크업", "Wake", "voltage", "power"],
        "MOT":  ["모터", "BLDC", "토크", "속도", "위치", "스트로크", "PWM", "PID", "프로파일", "영점", "Homing", "회전", "motor", "position"],
        "COM":  ["CAN", "메시지", "신호", "Timeout", "타임아웃", "Alive", "CRC", "DBC", "LIN", "통신", "message", "signal"],
        "DIAG": ["DTC", "UDS", "진단", "DID", "0x10", "0x19", "0x22", "0x2E", "0x31", "세션", "NRC", "diagnos"],
        "SAFE": ["Fail-safe", "페일세이프", "fail safe", "과전류", "과온", "구속", "Stall", "고장", "이상", "차단", "ASIL", "safe state", "안전"],
        "ENV":  ["온도 범위", "작동 온도", "EMC", "ESD", "진동", "충격", "방수", "습도", "environment"],
        "MECH": ["기구", "하우징", "커넥터", "중량", "치수", "장착", "mechanical"],
        "NVM":  ["NvM", "비휘발성", "플래시", "EEPROM", "캘리브레이션 블록"],
        "SEC":  ["보안", "SecurityAccess", "Seed", "서명", "ECDSA", "SecOC", "디버그 인터페이스"],
        "TIME": ["WCET", "데드라인", "엔드-투-엔드", "지연이", "실행 시간"],
        "ARCH": ["AUTOSAR", "BSW", "RTE", "OS 태스크", "CPU 부하", "MISRA", "스택"],
        "MFG":  ["EOL", "제조", "일련번호", "IPC-A", "코팅", "ppm", "양산"],
        "HSI":  ["핀", "Pin", "포트", "Port", "GTM", "EVADC", "QSPI", "MCMCAN", "채널", "Channel"],
        "GEN":  [],
    },
    # Ambiguous wording (PAM 4.0 verifiability)
    "ambiguous_words": ["빠르게", "신속", "신속히", "즉시", "안정적", "안정적으로", "적절", "적절히", "적절한", "충분", "충분히", "가능한 한",
                         "최소화", "최대화", "최적", "원활", "효율적", "약 ", "대략", "정도", "등의", "등을", "기타", "필요 시", "필요시",
                         "quickly", "fast", "appropriate", "sufficient", "as soon as possible", "user-friendly",
                         "robust", "approximately", "etc", "and/or", "if possible", "minimize", "maximize"],
    # Words that indicate a time/quantity requirement which then needs a number + unit
    "quantity_triggers": ["시간", "주기", "응답", "지연", "이내", "timeout", "타임아웃", "디바운스", "전압", "전류", "온도", "속도", "토크"],
    # Header words that mark a table as a requirement table (each row becomes an item)
    "req_table_headers": ["요구사항", "요구 사항", "requirement", "description", "설명", "내용", "사양", "specification"],
    "id_table_headers": ["id", "no", "no.", "번호", "req id", "요구사항 id", "식별자"],
    # Header words that mark a table as a pin map (each row becomes an HSI item)
    "pin_table_headers": ["pin", "핀", "port", "포트", "net", "넷", "peripheral", "주변장치"],
    # Similarity thresholds for stable ID matching on re-import
    "match_threshold": 0.62,
    # Optional AI refinement. provider: "none" | "anthropic" | "openai_compatible" (on-prem LLM)
    "llm": {"provider": "none", "model": "claude-sonnet-5-5", "base_url": "", "api_key_env": "ANTHROPIC_API_KEY"},
}


def load_config(root: Path) -> dict:
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    path = root / "alm.json"
    if path.exists():
        user = json.loads(path.read_text(encoding="utf-8"))
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    return cfg


def write_default_config(root: Path) -> Path:
    path = root / "alm.json"
    if not path.exists():
        path.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
