"""SYS.1 -> SYS.2 derivation that applies the SYS.2 rules instead of copying the customer's sentences.

1. Compliance decides what is derived: agreed requirements are derived, a deviation / partial acceptance is derived
   from the *agreed deviation*, rejected / not applicable / informational ones are left out, open questions wait.
2. Each customer requirement becomes one or more atomic, verifiable system requirements with a verification
   criterion, a method and a type; vague wording and missing values are raised as questions, never invented.
3. Topics the customer did not write about (modes, safe state, diagnostics, power, EMC, security, update, EOL …)
   are checked and proposed as additional requirements of internal origin.

Step 2 and 3 are done by the connected LLM ("AI mode"); without one, rules do a reduced version. Nothing is
written until the reviewed plan is applied; everything created is a draft that carries how it was derived.
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from .classify import Analyzer, quantities
from .compliance import normalize, statuses
from .llm import chat_call
from .importer import fingerprint
from .stages import _carry, _fmt, _has_target, _new, _verification_criteria, get_stage

DERIVE = {"Accept", "Accept with Comment"}
DEVIATION = {"Accept with Deviation", "Partially Accept"}
SKIP = {"Not Accept": "수용 불가 — SYS.2 로 전개하지 않음", "Not Applicable": "해당 없음",
        "Noted": "참고(정보성 문장) — 요구사항 아님"}
HOLD = {"Clarification Needed": "고객 확인 대기", "Under Review": "내부 검토 중", "": "컴플라이언스 미회신(Open)"}
TYPES = ["functional", "interface", "performance", "safety", "diagnostic", "environment", "constraint"]
TYPE_KO = {"functional": "기능", "interface": "인터페이스", "performance": "성능", "safety": "안전", "diagnostic": "진단",
           "environment": "환경", "constraint": "제약"}
# topics a system requirement specification is expected to cover: (key, label, evidence in the customer text, domain)
TOPICS = [
    ("modes", "운용 모드 · 상태 전이 (초기화/정상/저하/슬립)", r"모드|상태 전이|초기화|슬립|sleep|wake|웨이크|degrad|저하", "GEN"),
    ("safe_state", "고장 시 안전 상태 · 검출/반응 시간", r"안전 상태|safe state|FTTI|고장.{0,12}(반응|검출)|fail.?safe", "SAFE"),
    ("diag", "진단 (DTC · UDS · 고장 기록)", r"DTC|UDS|진단|freeze frame", "DIAG"),
    ("comm", "통신 인터페이스 · 타임아웃", r"CAN|LIN|Ethernet|FlexRay|메시지|타임아웃", "COM"),
    ("power", "전원 · 전압 범위 · 암전류", r"전압|전원|암전류|KL30|KL15|배터리", "PWR"),
    ("timing", "응답 시간 · 주기 · 기동 시간", r"\d+\s*ms|주기|응답 시간|기동 시간", "GEN"),
    ("env", "환경 · EMC · 내구", r"EMC|온도|방수|진동|ISO 16750|CISPR|내구", "ENV"),
    ("security", "사이버보안", r"SecOC|보안|secure|인증|HSM|UN R155|21434", "SEC"),
    ("update", "리프로그래밍 · OTA", r"리프로그래밍|OTA|부트로더|플래시|업데이트|UN R156", "GEN"),
    ("eol", "생산 · EOL · 서비스 · 코딩", r"EOL|생산|서비스|코딩|variant", "GEN"),
    ("nvm", "데이터 저장 (NVM)", r"NVM|EEPROM|비휘발|저장", "GEN"),
    ("hmi", "운전자 알림 · 경고", r"경고등|클러스터|알림|warning", "GEN"),
]

SYSTEM = """당신은 자동차 ECU 시스템 엔지니어다. 고객 요구사항(ASPICE SYS.1)을 시스템 요구사항(SYS.2)으로 전개한다.
규칙:
- 시스템을 블랙박스로 보고 "시스템은 …해야 한다" 형태로 쓴다. SW/HW 구현 방법은 쓰지 않는다.
- 한 문장에 요구 하나. 고객 문장에 요구가 여럿이면 여러 개로 나눈다. 불필요하게 쪼개지 않는다.
- 고객이 준 수치·단위·조건·신호 이름은 그대로 유지한다. 없는 수치를 지어내지 않는다. 값이 필요한데 없으면 문장에 "[TBD: 무엇]" 을 쓰고 questions 에 고객에게 물을 질문을 넣는다.
- "빠르게, 적절히, 충분히" 같은 모호한 표현은 측정 가능한 조건으로 바꾸되, 값이 없으면 [TBD] 로 둔다.
- basis 가 "deviation" 이면 고객 문장이 아니라 deviation(합의된 편차·대안)과 comment 에 맞춰 쓴다.
- criteria: 합격/불합격을 판정할 수 있는 검증 기준 한 문장. method: 시험/분석/검토/시뮬레이션 중 맞는 방법과 환경(예: HIL, 차량 시험).
- type: functional | interface | performance | safety | diagnostic | environment | constraint 중 하나.
- 원문과 같은 언어로 쓴다.
출력은 JSON 하나만: {"items": {"<id>": {"reqs": [{"text": "...", "criteria": "...", "method": "...", "type": "..."}], "questions": ["..."]}}}"""

GAP_SYSTEM = """당신은 자동차 ECU 시스템 엔지니어다. 고객 요구사양서에서 빠져 있지만 시스템 요구사항(SYS.2)에 있어야 하는 내용을 찾는다.
입력: 제품 문서의 장 제목, 주제별 고객 요구사항 수(covered), 요구사항 예시.
covered 가 0 이거나 매우 적은 주제를 중심으로, 이 제품에 실제로 필요한 추가 시스템 요구사항만 제안한다 (최대 12개, 주제당 최대 2개).
수치를 지어내지 말고 값이 필요하면 "[TBD: 무엇]" 으로 둔다. 이미 고객 요구사항에 있는 내용은 제안하지 않는다.
출력은 JSON 하나만: {"gaps": [{"topic": "<주제 key>", "text": "시스템은 …해야 한다", "criteria": "...", "rationale": "왜 필요한지 한 문장"}]}"""


def _decide(status: str, include_open: bool) -> tuple[str, str]:
    if status in DERIVE:
        return "derive", ""
    if status in DEVIATION:
        return "deviation", ""
    if status in SKIP:
        return "skip", SKIP[status]
    if status == "" and include_open:
        return "derive", ""
    return "hold", HOLD.get(status, "확정되지 않은 상태")


def plan_local(repo, cfg: dict, ids: list[str] | None = None, include_open: bool | None = None) -> dict:
    """Decisions and a rule-based draft for every customer requirement not derived yet (reads only)."""
    st = get_stage(cfg, "SYS1")
    an = Analyzer(cfg)
    labels = {s["label"] for s in statuses(cfg)}
    srcs = sorted((i for i in repo.items() if i["type"] in st["types"] and (not ids or i["id"] in ids)),
                  key=lambda i: (i["doc"], i["ord"]))
    answered = sum(1 for i in srcs if normalize(i["attrs"].get("compliance", "")) in labels)
    if include_open is None:          # nobody filled the matrix: treat everything as agreed, and say so
        include_open = answered == 0
    rows, text_all = [], []
    for s in srcs:
        a = s["attrs"]
        text_all.append(s["text"])
        status = normalize(a.get("compliance", ""))
        status = status if status in labels else ""
        if _has_target(repo, s["id"], "derives", {"SYS2"}, "down"):
            rows.append({"src": s["id"], "decision": "done", "reason": "이미 전개됨", "status": status, "text": s["text"],
                         "native_id": a.get("native_id", ""), "section": s["section"], "reqs": [], "questions": []})
            continue
        decision, reason = _decide(status, include_open)
        basis = (a.get("deviation") or a.get("comment") or "").strip() if decision == "deviation" else ""
        r = {"src": s["id"], "native_id": a.get("native_id", ""), "section": s["section"], "text": s["text"], "status": status,
             "decision": decision, "reason": reason, "deviation": a.get("deviation", ""), "comment": a.get("comment", ""),
             "asil": _carry(a).get("asil", ""), "reqs": [], "questions": [], "mode": "rule"}
        if decision == "deviation" and not basis:
            r["decision"], r["reason"] = "hold", "편차·부분 수용인데 편차 내용/코멘트가 비어 있음 — 무엇을 기준으로 전개할지 알 수 없음"
        if r["decision"] in ("derive", "deviation"):
            parts = [p for p in an.split_atomic(s["text"]) if p.strip()] or [s["text"]]
            dom = s["domain"] if s["domain"] != "HSI" else "GEN"
            for p in parts:
                r["reqs"].append({"text": p, "criteria": _verification_criteria(p, dom),
                                  "method": _carry(a).get("verification_method", ""), "type": _type(p, dom)})
            for l in an.lint(s["text"], "SYS2"):
                msg = l.get("msg") or l.get("message") or str(l)
                if msg not in r["questions"]:
                    r["questions"].append(msg)
            if r["decision"] == "deviation":
                r["questions"].insert(0, f"합의된 편차를 문장에 반영하세요: {basis}")
        rows.append(r)
    blob = "\n".join(text_all)
    topics = [{"key": k, "label": lab, "covered": len(re.findall(rx, blob, re.I)), "domain": dom} for k, lab, rx, dom in TOPICS]
    return {"rows": rows, "topics": topics, "gaps": [], "include_open": include_open, "answered": answered,
            "mode": "rule", "ai_status": "", "summary": _summary(rows, [])}


def _type(text: str, dom: str) -> str:
    if dom in ("SAFE",) or re.search(r"안전 상태|ASIL|fail.?safe", text, re.I):
        return "safety"
    if dom == "DIAG" or re.search(r"DTC|UDS|진단", text):
        return "diagnostic"
    if dom == "COM" or re.search(r"CAN|LIN|메시지|신호|커넥터|핀", text):
        return "interface"
    if dom in ("ENV", "MECH") or re.search(r"EMC|온도|진동|방수", text):
        return "environment"
    if quantities(text) and re.search(r"ms|이내|정확도|오차|응답", text):
        return "performance"
    return "functional"


def _summary(rows: list[dict], gaps: list[dict]) -> dict:
    c = {"derive": 0, "deviation": 0, "hold": 0, "skip": 0, "done": 0}
    for r in rows:
        c[r["decision"]] += 1
    return {**c, "sources": len(rows), "new_reqs": sum(len(r["reqs"]) for r in rows if r["decision"] in ("derive", "deviation")),
            "split": sum(1 for r in rows if r["decision"] in ("derive", "deviation") and len(r["reqs"]) > 1),
            "questions": sum(len(r["questions"]) for r in rows), "gaps": len(gaps)}


def _json(raw: str) -> dict:
    m = re.search(r"\{.*\}", raw, re.S)
    return json.loads(m.group(0)) if m else {}


def enrich(cfg: dict, plan: dict, progress=None, batch: int = 10, workers: int = 4) -> dict:
    """The AI part: rewrite / split / criteria per requirement, then the missing-topic proposals. No database access."""
    from .assistant import status
    st = status(cfg)
    if st["mode"] != "llm":
        plan["ai_status"] = "AI 가 연결되어 있지 않아 규칙 기반으로만 전개안을 만들었습니다 (문장 분해·검증 기준 초안만, 누락 제안 없음)."
        return plan
    todo = [r for r in plan["rows"] if r["decision"] in ("derive", "deviation")]
    chunks = [todo[i:i + batch] for i in range(0, len(todo), batch)]
    done, failed, lock = [0], [], threading.Lock()

    def run(chunk):
        payload = [{"id": r["src"], "customer_id": r["native_id"], "section": r["section"][:80], "text": r["text"][:1500],
                    "asil": r["asil"], "basis": "deviation" if r["decision"] == "deviation" else "customer",
                    **({"deviation": r["deviation"][:600], "comment": r["comment"][:600]} if r["decision"] == "deviation"
                       else ({"comment": r["comment"][:400]} if r["comment"] else {}))} for r in chunk]
        try:
            j = _json(chat_call(cfg, SYSTEM, [{"role": "user", "content": json.dumps({"requirements": payload}, ensure_ascii=False)}],
                                max_tokens=6000, timeout=240))
            items = j.get("items") or {}
            for r in chunk:
                x = items.get(r["src"]) or {}
                reqs = [{"text": str(q.get("text", "")).strip()[:2000], "criteria": str(q.get("criteria", "")).strip()[:600],
                         "method": str(q.get("method", "")).strip()[:200],
                         "type": q.get("type") if q.get("type") in TYPES else "functional"}
                        for q in (x.get("reqs") or []) if isinstance(q, dict) and str(q.get("text", "")).strip()][:8]
                if reqs:
                    for q in reqs:          # the customer's own verification method wins when the AI gave none
                        q["method"] = q["method"] or (r["reqs"][0]["method"] if r["reqs"] else "")
                    r["reqs"], r["mode"] = reqs, "ai"
                    r["questions"] = [str(q)[:300] for q in (x.get("questions") or []) if str(q).strip()][:6]
        except Exception as e:
            with lock:
                failed.append(str(e)[:120])
        with lock:
            done[0] += len(chunk)
            if progress:
                progress(done[0], len(todo), "요구사항 전개")

    if chunks:
        with ThreadPoolExecutor(max_workers=max(1, min(workers, len(chunks)))) as ex:
            list(ex.map(run, chunks))
    if progress:
        progress(len(todo), len(todo), "누락 주제 점검")
    try:
        heads = list(dict.fromkeys(r["section"].split(" > ")[0] for r in plan["rows"] if r["section"]))[:40]
        sample = [r["text"][:200] for r in plan["rows"][:: max(1, len(plan["rows"]) // 25)]][:25]
        j = _json(chat_call(cfg, GAP_SYSTEM, [{"role": "user", "content": json.dumps(
            {"chapters": heads, "topics": [{"key": t["key"], "label": t["label"], "covered": t["covered"]} for t in plan["topics"]],
             "examples": sample}, ensure_ascii=False)}], max_tokens=3000, timeout=180))
        keys = {t["key"]: t for t in plan["topics"]}
        plan["gaps"] = [{"topic": g.get("topic") if g.get("topic") in keys else "", "text": str(g.get("text", "")).strip()[:1500],
                         "criteria": str(g.get("criteria", "")).strip()[:600], "rationale": str(g.get("rationale", "")).strip()[:300]}
                        for g in (j.get("gaps") or []) if isinstance(g, dict) and str(g.get("text", "")).strip()][:12]
    except Exception as e:
        failed.append("누락 점검: " + str(e)[:100])
    ai_rows = sum(1 for r in todo if r["mode"] == "ai")
    plan["mode"] = "ai" if ai_rows or plan["gaps"] else "rule"
    plan["model"] = st["model"]
    if failed:
        plan["ai_status"] = (f"AI 호출 일부 실패 — {len(todo) - ai_rows}건은 규칙 기반 초안입니다 ({failed[0]})" if ai_rows
                             else f"AI 호출 실패 — 규칙 기반 초안만 표시합니다 ({failed[0]})")
    plan["summary"] = _summary(plan["rows"], plan["gaps"])
    return plan


def apply(repo, cfg: dict, rows: list[dict], gaps: list[dict], user: str, mode: str = "ai") -> dict:
    """Create the reviewed SYS.2 drafts and their links. rows: [{src, reqs: [{text, criteria, method, type}], questions}]"""
    st = get_stage(cfg, "SYS1")
    an = Analyzer(cfg)
    created, linked, skipped = [], 0, []
    now = time.strftime("%Y-%m-%d %H:%M")
    for r in rows:
        s = repo.get(r.get("src", ""))
        if not s or s["type"] not in st["types"] or s["status"] == "deleted":
            raise KeyError(f"고객 요구사항이 아닙니다: {r.get('src')}")
        if _has_target(repo, s["id"], "derives", {"SYS2"}, "down"):
            skipped.append(s["id"]); continue
        reqs = [q for q in (r.get("reqs") or []) if str(q.get("text", "")).strip()]
        if not reqs:
            continue
        a = s["attrs"]
        dom = s["domain"] if s["domain"] != "HSI" else "GEN"
        status = normalize(a.get("compliance", ""))
        qs = [str(q)[:300] for q in (r.get("questions") or [])][:6]
        for k, q in enumerate(reqs):
            text = str(q["text"]).strip()
            lvl, conf = an.level(text, s["section"])
            attrs = {"discipline": "SW" if lvl == "SWE1" else "HW/SYS", "level_confidence": conf,
                     "verification_criteria": str(q.get("criteria") or "").strip() or _verification_criteria(text, dom),
                     "native_id": a.get("native_id", ""), **_carry(a),
                     "req_type": q.get("type") if q.get("type") in TYPES else _type(text, dom),
                     "derive_mode": "ai" if r.get("mode", mode) == "ai" else "rule", "derived_at": now, "derived_by": user,
                     "derive_basis": "deviation" if status in DEVIATION else "customer"}
            if str(q.get("method") or "").strip():
                attrs["verification_method"] = str(q["method"]).strip()
            if status in DEVIATION:
                attrs["deviation"] = a.get("deviation", "") or a.get("comment", "")
            if len(reqs) > 1:
                attrs["split"] = f"{k + 1}/{len(reqs)}"
            if qs:
                attrs["open_questions"] = qs
            it = _new(repo, cfg, "SYS2", text, dom, s, attrs, user=user)
            repo.add_link(it["id"], "derives", s["id"])
            created.append(it["id"]); linked += 1
    topic = {t[0]: t for t in TOPICS}
    domains = set(cfg.get("domain_names") or {}) or None
    for g in gaps or []:
        text = str(g.get("text", "")).strip()
        if not text:
            continue
        t = topic.get(g.get("topic", ""))
        dom = t[3] if t and (domains is None or t[3] in domains) else "GEN"
        new_id = repo.next_id(_fmt(cfg, "SYS2", dom), cfg["types"]["SYS2"]["prefix"], dom, cfg)
        it = repo.insert({"id": new_id, "type": "SYS2", "domain": dom, "title": text[:80], "text": text,
                          "attrs": {"origin": "internal", "origin_note": "고객 요구사양서에 없는 주제 — 전개 시 누락 점검으로 추가",
                                    "topic": t[1] if t else "", "rationale": str(g.get("rationale", ""))[:300],
                                    "verification_criteria": str(g.get("criteria", "")).strip() or _verification_criteria(text, dom),
                                    "req_type": _type(text, dom), "derive_mode": "ai", "derived_at": now, "derived_by": user,
                                    "quantities": quantities(text)},
                          "lint": an.lint(text, "SYS2"), "doc": "", "doc_rev": "", "section": "추가 시스템 요구사항 (내부 도출)",
                          "source_loc": "derived:gap", "ord": 1e6 + len(created), "fingerprint": fingerprint(text)}, by=user)
        created.append(it["id"])
    repo.commit()
    return {"from": "SYS1", "to": "SYS2", "created": created, "links": linked, "skipped": skipped}


# ---------------------------------------------------------------- background jobs (the AI step takes minutes)
JOBS: dict = {}
_jl = threading.Lock()


def start(cfg: dict, plan: dict, use_ai: bool) -> str:
    jid = uuid.uuid4().hex[:12]
    job = {"id": jid, "done": False, "progress": [0, 0, "준비"], "plan": None, "error": "", "t": time.time()}
    with _jl:
        for k in [k for k, v in JOBS.items() if time.time() - v["t"] > 3600]:
            del JOBS[k]
        JOBS[jid] = job

    def run():
        try:
            job["plan"] = enrich(cfg, plan, lambda a, b, what: job.update(progress=[a, b, what])) if use_ai else plan
            if not use_ai:
                plan["ai_status"] = "AI 를 쓰지 않고 규칙 기반으로 전개안을 만들었습니다."
        except Exception as e:      # never lose the local plan
            plan["ai_status"] = f"AI 단계 실패 — 규칙 기반 초안만 표시합니다 ({e})"[:200]
            job["plan"] = plan
        job["done"] = True
    threading.Thread(target=run, daemon=True).start()
    return jid


def job(jid: str) -> dict:
    j = JOBS.get(jid)
    if not j:
        raise KeyError("전개 작업을 찾을 수 없습니다 (서버가 다시 시작됐을 수 있음) — 다시 분석하세요")
    return {"id": jid, "done": j["done"], "progress": j["progress"], "plan": j["plan"] if j["done"] else None}
