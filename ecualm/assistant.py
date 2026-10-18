"""AI assistant behind the chat panel.

* LLM mode (alm.json llm.provider = anthropic | openai_compatible): the question is sent together with a
  compact, grounded context — project status, the stage on screen, the selected item with its trace,
  and the items that best match the question. The model answers in Korean and may PROPOSE actions
  (derive / link / create / edit / status / open / audit). Nothing is executed here: the web UI shows
  each proposal as a button and runs it only when the user clicks.
* Local mode (no provider or the call failed): rule-based commands over the same data, so the panel is
  useful offline — status summary, "explain <ID>", "SYS2→SWE1 전개", Suspect / FAIL / 고아 lists, search.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict

from .audit import run_audit
from .db import Repo
from .importer import bigrams
from .llm import api_key, chat_call
from .stages import stage_counts

ACTION_TYPES = ("derive", "link", "create", "edit", "status", "open", "audit")
ID_RE = re.compile(r"\b(?:[A-Z]{2,5}\d?(?:-TC)?-(?:[A-Z]{2,5}-)?\d{4}|[A-Z][A-Z0-9]{1,10}-[A-Z]{2,8}-\d{3})\b")

SYSTEM = """당신은 자동차 ECU 개발 조직의 요구사항·추적성 전문가이자 ECU-ALM 도구의 어시스턴트입니다.
ASPICE PAM 4.0 (SYS.1~5, HWE.1~4, SWE.1~6), ISO 26262, AUTOSAR 관점에서 답합니다.
규칙:
- 한국어로, 짧고 구체적으로 답합니다. 아이템을 말할 때는 반드시 ID 를 씁니다 (예: SYS2-MOT-0003).
- 아래 [문맥] 에 있는 데이터만 사실로 사용합니다. 문맥에 없는 내용은 추측하지 말고 "문맥에 없음"이라고 말합니다.
- 도구에서 실행할 수 있는 일을 제안할 때는 actions 에 넣습니다. 사용자가 버튼을 눌러야 실행되므로 확실한 것만 제안합니다.
- 반드시 JSON 한 개로만 답합니다: {"reply": "마크다운 답변", "actions": [ ... ]}
actions 형식 (필요할 때만, 최대 6개):
  {"type":"derive","from":"SYS2","to":"SWE1","label":"..."}                 단계 전개 (단계 ID: SYS1 SYS2 SYS3 HWE1 HWE2 SWE1 SWE2 SWE3 SWE4 SWE5 SWE6 HWE3 HWE4 SYS4 SYS5)
  {"type":"link","src":"하위ID","role":"refines|verifies|satisfies|allocates|derives|uses|controls|connects","dst":"상위ID","label":"..."}
  {"type":"create","item_type":"SWE1","text":"요구사항 문장","domain":"MOT","label":"..."}
  {"type":"edit","id":"ID","text":"수정된 문장","label":"..."}                요구사항 문장 개선 제안
  {"type":"status","id":"ID","status":"review|approved|draft","label":"..."}
  {"type":"open","id":"ID","label":"..."}                                    아이템 열기
  {"type":"audit","label":"감사 콘솔 열기"}"""

HELP = """**로컬 명령 모드** (AI 공급자가 연결되지 않았을 때)
- `현황` · `요약` — 단계별 건수, 승인, Suspect, 시험 결과
- `SYS2-MOT-0003` 처럼 **ID** — 아이템 설명과 상·하위 추적
- `SYS2 → SWE1 전개` — 전개 버튼 제안
- `감사` — 오류·경고 상위 항목, `Suspect`, `FAIL`, `고아`(상위 미연결), `모호`(품질 경고)
- 그 밖의 문장 — 관련 요구사항 검색

AI 모드를 쓰려면 ⚙ 에서 공급자(Anthropic 또는 사내 LLM)와 키를 설정하세요."""


# ------------------------------------------------------------------ context
def _short(t: str, n: int = 160) -> str:
    t = (t or "").replace("\n", " ")
    return t if len(t) <= n else t[: n - 1] + "…"


def _item_line(it: dict) -> str:
    a = it["attrs"]
    extra = []
    if a.get("native_id"):
        extra.append(f"원문 {a['native_id']}")
    if a.get("asil") and a["asil"] != "QM":
        extra.append(f"ASIL {a['asil']}")
    if a.get("result"):
        extra.append(f"결과 {a['result'].get('status')}")
    return f"{it['id']} [{it['type']}/{it['domain']}/{it['status']}{'/' + ', '.join(extra) if extra else ''}] {_short(it['title'] if it['type'] in ('HWE2', 'SYS3', 'SWE2', 'IF') else it['text'])}"


def search(repo: Repo, q: str, limit: int = 10, types: set | None = None) -> list[dict]:
    qb = bigrams(q)
    if not qb:
        return []
    scored = []
    for it in repo.items():
        if it["type"] in ("HDG", "INFO", "TBL", "FIG") or (types and it["type"] not in types):
            continue
        hay = it["text"] + " " + it["title"] + " " + it["id"] + " " + str(it["attrs"].get("native_id", ""))
        b = bigrams(hay)
        s = len(qb & b) / (len(qb) or 1)
        if any(w and w.lower() in hay.lower() for w in re.findall(r"[A-Za-z0-9가-힣._-]{2,}", q)):
            s += 0.25
        if s > 0.18:
            scored.append((s, it))
    scored.sort(key=lambda x: -x[0])
    return [it for _, it in scored[:limit]]


def build_context(repo: Repo, cfg: dict, question: str, ctx: dict) -> str:
    sc = stage_counts(repo, cfg)
    lines = [f"프로젝트: {cfg['project']}", "단계별 현황 (전체/승인/Suspect):"]
    for s in cfg["stages"]:
        c = sc.get(s["id"], {})
        if c.get("total"):
            lines.append(f"  {s['id']} {s['aspice']} {s['name']}: {c['total']} / {c['status'].get('approved', 0)} / {c['suspect']}")
    tcs = [i for i in repo.items() if i["type"].endswith("_TC") and i["attrs"].get("result")]
    if tcs:
        cnt = Counter(i["attrs"]["result"]["status"] for i in tcs)
        lines.append("시험 결과: " + ", ".join(f"{k} {v}" for k, v in cnt.items()))
    if ctx.get("stage"):
        st = next((s for s in cfg["stages"] if s["id"] == ctx["stage"]), None)
        if st:
            lines.append(f"사용자가 보고 있는 화면: {st['aspice']} {st['name']} ({ctx.get('tab') or '문서'})")
    seen = set()
    sel = repo.get(ctx.get("selected") or "") if ctx.get("selected") else None
    mentioned = [repo.get(m) for m in dict.fromkeys(ID_RE.findall(question))]
    by_native = {}
    for nid in re.findall(r"\b[A-Z][A-Z0-9]{1,10}-[A-Z]{2,8}-\d{3}\b", question):
        hit = next((i for i in repo.items() if i["attrs"].get("native_id") == nid), None)
        if hit:
            by_native[nid] = hit
    focus = [x for x in [sel, *mentioned, *by_native.values()] if x]
    for it in focus:
        if it["id"] in seen:
            continue
        seen.add(it["id"])
        lines.append(f"\n[아이템 {it['id']}] 타입 {it['type']} 상태 {it['status']} v{it['version']} 도메인 {it['domain']}")
        lines.append(f"  문장: {it['text']}")
        a = it["attrs"]
        for k in ("native_id", "asil", "verification_method", "verification_criteria", "rationale", "spec", "hw", "result"):
            if a.get(k):
                v = a[k]
                if k == "result":
                    v = {x: a[k].get(x) for x in ("status", "run_id", "metrics", "note")}
                lines.append(f"  {k}: {json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v}")
        if it["lint"]:
            lines.append("  품질 경고: " + "; ".join(f["msg"] for f in it["lint"][:5]))
        links = repo.links(it["id"])
        for l in links[:25]:
            other = repo.get(l["dst"] if l["src"] == it["id"] else l["src"])
            if not other:
                continue
            arrow = f"↑ {l['role']}" if l["src"] == it["id"] else f"↓ {l['role']} (by)"
            lines.append(f"  {arrow} {_item_line(other)}{' [SUSPECT]' if l['suspect'] else ''}{' [제안]' if l['state'] == 'proposed' else ''}")
    hits = [h for h in search(repo, question, 10) if h["id"] not in seen]
    if hits:
        lines.append("\n질문과 관련 있어 보이는 아이템:")
        lines += ["  " + _item_line(h) for h in hits]
    text = "\n".join(lines)
    return text[:14000]


# ------------------------------------------------------------------ entry point
def status(cfg: dict) -> dict:
    llm = cfg.get("llm", {})
    prov = llm.get("provider", "none")
    has_key = bool(api_key(cfg))
    ready = (prov == "anthropic" and has_key) or (prov == "openai_compatible" and bool(llm.get("base_url")))
    return {"provider": prov, "model": llm.get("model", ""), "base_url": llm.get("base_url", ""), "has_key": has_key,
            "mode": "llm" if ready else "local"}


def chat(repo: Repo, cfg: dict, messages: list[dict], ctx: dict | None = None) -> dict:
    ctx = ctx or {}
    msgs = [m for m in messages if m.get("role") in ("user", "assistant") and str(m.get("content", "")).strip()][-12:]
    if not msgs or msgs[-1]["role"] != "user":
        raise ValueError("마지막 메시지는 사용자 질문이어야 합니다")
    question = msgs[-1]["content"]
    st = status(cfg)
    if st["mode"] == "llm" and not question.strip().startswith("/local"):
        context = build_context(repo, cfg, question, ctx)
        convo = msgs[:-1] + [{"role": "user", "content": f"[문맥]\n{context}\n\n[질문]\n{question}"}]
        try:
            raw = chat_call(cfg, SYSTEM, convo)
            reply, actions = _parse(raw)
            return {"mode": "llm", "model": st["model"], "reply": reply, "actions": _clean_actions(repo, cfg, actions)}
        except Exception as e:  # network / key / quota problems: answer locally and say why
            out = local(repo, cfg, question, ctx)
            out["reply"] = f"⚠ AI 호출 실패 — {e}\n로컬 명령으로 답합니다.\n\n" + out["reply"]
            return out
    return local(repo, cfg, question.replace("/local", "", 1).strip(), ctx)


def _parse(raw: str) -> tuple[str, list]:
    m = re.search(r"\{.*\}", raw, re.S)
    if m:
        try:
            j = json.loads(m.group(0))
            return str(j.get("reply", "")).strip() or raw, j.get("actions") or []
        except ValueError:
            pass
    return raw.strip(), []


def _clean_actions(repo: Repo, cfg: dict, actions: list) -> list:
    stages = {s["id"] for s in cfg["stages"]}
    out = []
    for a in actions[:6]:
        if not isinstance(a, dict) or a.get("type") not in ACTION_TYPES:
            continue
        t = a["type"]
        if t == "derive" and not (a.get("from") in stages and a.get("to") in stages):
            continue
        if t in ("link",) and not (repo.get(str(a.get("src"))) and repo.get(str(a.get("dst"))) and a.get("role")):
            continue
        if t in ("edit", "status", "open") and not repo.get(str(a.get("id"))):
            continue
        if t == "create" and not (a.get("item_type") in cfg["types"] and str(a.get("text", "")).strip()):
            continue
        a["label"] = str(a.get("label") or _label(a))[:80]
        out.append(a)
    return out


def _label(a: dict) -> str:
    return {"derive": lambda: f"{a['from']} → {a['to']} 전개", "link": lambda: f"{a['src']} —{a['role']}→ {a['dst']}",
            "create": lambda: f"{a['item_type']} 생성", "edit": lambda: f"{a['id']} 문장 수정", "status": lambda: f"{a['id']} → {a['status']}",
            "open": lambda: f"{a['id']} 열기", "audit": lambda: "감사 콘솔 열기"}[a["type"]]()


# ------------------------------------------------------------------ local (offline) commands
def local(repo: Repo, cfg: dict, q: str, ctx: dict) -> dict:
    ql = q.lower()
    acts: list[dict] = []
    stage_ids = [s["id"] for s in cfg["stages"]]
    norm = re.sub(r"(SYS|SWE|HWE)\.(\d)", r"\1\2", q.upper())

    if not q or ql in ("도움말", "help", "?", "명령"):
        return _out(HELP)

    pair = re.findall(r"\b(SYS[1-5]|SWE[1-6]|HWE[1-4])\b", norm)
    if ("전개" in q or "derive" in ql) and len(pair) >= 2 and pair[0] in stage_ids and pair[1] in stage_ids:
        a = {"type": "derive", "from": pair[0], "to": pair[1]}
        a["label"] = _label(a)
        return _out(f"**{pair[0]} → {pair[1]}** 전개를 실행할 수 있습니다. 이미 전개된 항목은 건너뜁니다.", [a])

    ids = list(dict.fromkeys(ID_RE.findall(q)))
    natives = re.findall(r"\b[A-Z][A-Z0-9]{1,10}-[A-Z]{2,8}-\d{3}\b", q)
    focus = [repo.get(i) for i in ids if repo.get(i)]
    for nid in natives:
        hit = next((i for i in repo.items() if i["attrs"].get("native_id") == nid), None)
        if hit and hit not in focus:
            focus.append(hit)
    if not focus and ctx.get("selected") and any(w in q for w in ("이것", "선택", "설명", "이 아이템", "현재")):
        it = repo.get(ctx["selected"])
        focus = [it] if it else []
    if focus:
        parts = []
        for it in focus[:3]:
            parts.append(_explain(repo, it))
            acts.append({"type": "open", "id": it["id"], "label": f"{it['id']} 열기"})
        return _out("\n\n".join(parts), acts)

    if any(w in q for w in ("현황", "요약", "상태", "summary", "다음 할 일", "할 일")):
        sc = stage_counts(repo, cfg)
        rows = [f"- **{s['aspice']} {s['name']}** {sc[s['id']]['total']}건 (승인 {sc[s['id']]['status'].get('approved', 0)}"
                f"{', Suspect ' + str(sc[s['id']]['suspect']) if sc[s['id']]['suspect'] else ''})" for s in cfg["stages"] if sc[s["id"]]["total"]]
        nxt = []
        for s in cfg["stages"]:
            if not sc[s["id"]]["total"]:
                continue
            for n in s.get("next", []):
                if not sc.get(n, {}).get("total"):
                    nxt.append({"type": "derive", "from": s["id"], "to": n, "label": f"{s['id']} → {n} 전개"})
        tcs = Counter(i["attrs"]["result"]["status"] for i in repo.items() if i["type"].endswith("_TC") and i["attrs"].get("result"))
        txt = "**프로젝트 현황**\n" + ("\n".join(rows) or "- 아직 아이템이 없습니다. 고객 요구사항 문서를 가져오세요.")
        if tcs:
            txt += "\n\n시험 결과: " + ", ".join(f"{k} {v}" for k, v in tcs.items())
        if nxt:
            txt += "\n\n아직 전개하지 않은 다음 단계가 있습니다."
        return _out(txt, nxt[:5])

    if "감사" in q or "audit" in ql or "오류" in q:
        A = run_audit(repo, cfg)
        s = A["summary"]
        top = [f for f in A["findings"] if f["sev"] == "error"][:8] or A["findings"][:8]
        by = Counter(f["rule"] for f in A["findings"] if f["sev"] in ("error", "warn"))
        txt = (f"**감사 결과** — Error {s['errors']} · Warning {s['warnings']} · Info {s['infos']}\n"
               + ("규칙별: " + ", ".join(f"{k} {v}" for k, v in by.most_common(6)) + "\n" if by else "")
               + "\n".join(f"- `{f['sev']}` {f['item']} — {_short(f['msg'], 110)}" for f in top))
        return _out(txt, [{"type": "audit", "label": "감사 콘솔 열기"}])

    if "suspect" in ql or "재검토" in q:
        sus = [l for l in repo.links() if l["suspect"]]
        if not sus:
            return _out("Suspect 링크가 없습니다.")
        txt = f"**Suspect 링크 {len(sus)}건** (상위가 바뀌어 하위 재검토 필요)\n" + "\n".join(
            f"- {l['src']} —{l['role']}→ {l['dst']}" for l in sus[:15]) + ("\n- …" if len(sus) > 15 else "")
        return _out(txt, [{"type": "open", "id": l["src"], "label": f"{l['src']} 열기"} for l in sus[:3]])

    if "fail" in ql or "실패" in q or "시험 결과" in q:
        tcs = [i for i in repo.items() if i["type"].endswith("_TC") and (i["attrs"].get("result") or {}).get("status") == "FAIL"]
        if not tcs:
            return _out("FAIL 인 시험 결과가 없습니다.")
        txt = f"**FAIL {len(tcs)}건**\n" + "\n".join(
            f"- {t['id']} {t['title']} — {_short(t['attrs']['result'].get('note') or '', 90)}" for t in tcs[:10])
        return _out(txt, [{"type": "open", "id": t["id"], "label": f"{t['id']} 열기"} for t in tcs[:3]])

    if "고아" in q or "미연결" in q or "orphan" in ql:
        st = ctx.get("stage")
        types = next((set(s["types"]) for s in cfg["stages"] if s["id"] == st), None)
        ups = defaultdict(int)
        for l in repo.links():
            if l["state"] == "confirmed" and l["role"] != "relates":
                ups[l["src"]] += 1
        cand = [i for i in repo.items() if i["type"] not in ("CRS", "HDG", "INFO", "TBL", "FIG") and (not types or i["type"] in types) and not ups[i["id"]]]
        if not cand:
            return _out("상위 링크가 없는 아이템이 없습니다." + (f" ({st})" if st else ""))
        return _out(f"**상위 미연결 {len(cand)}건**{' — ' + st if st else ''}\n" + "\n".join("- " + _item_line(i) for i in cand[:12]),
                    [{"type": "open", "id": i["id"], "label": f"{i['id']} 열기"} for i in cand[:3]])

    if "모호" in q or "품질" in q or "lint" in ql:
        bad = [i for i in repo.items() if i["lint"] and i["type"] not in ("HDG", "INFO", "TBL", "FIG")]
        if not bad:
            return _out("품질 경고가 있는 요구사항이 없습니다.")
        return _out(f"**품질 경고 {len(bad)}건** (예시)\n" + "\n".join(f"- {i['id']} — {i['lint'][0]['msg']}" for i in bad[:10]),
                    [{"type": "open", "id": i["id"], "label": f"{i['id']} 열기"} for i in bad[:3]])

    hits = search(repo, q, 8)
    if hits:
        return _out("**관련 아이템**\n" + "\n".join("- " + _item_line(h) for h in hits)
                    + "\n\n(로컬 모드: 검색 결과입니다. 자연어 분석·문장 개선은 AI 공급자를 연결하면 사용할 수 있습니다.)",
                    [{"type": "open", "id": h["id"], "label": f"{h['id']} 열기"} for h in hits[:3]])
    return _out("관련 아이템을 찾지 못했습니다. `도움말` 을 입력하면 사용할 수 있는 명령을 볼 수 있습니다.")


def _explain(repo: Repo, it: dict) -> str:
    a = it["attrs"]
    lines = [f"**{it['id']}** ({it['type']}, {it['status']}, v{it['version']}{', ASIL ' + a['asil'] if a.get('asil') and a['asil'] != 'QM' else ''})",
             f"> {_short(it['text'], 300)}"]
    if a.get("native_id"):
        lines.append(f"원문 ID: {a['native_id']}")
    if a.get("verification_criteria") or a.get("verification_method"):
        lines.append(f"검증: {a.get('verification_method') or ''} {a.get('verification_criteria') or ''}".strip())
    if a.get("result"):
        r = a["result"]
        lines.append(f"시험 결과: **{r.get('status')}** ({r.get('run_id') or '-'}) {r.get('note') or ''}")
    ups = [l for l in repo.links(it["id"]) if l["src"] == it["id"]]
    downs = [l for l in repo.links(it["id"]) if l["dst"] == it["id"]]
    if ups:
        lines.append("상위: " + ", ".join(f"{l['role']} {l['dst']}{' (SUSPECT)' if l['suspect'] else ''}" for l in ups[:8]))
    else:
        lines.append("상위: 없음")
    if downs:
        lines.append("하위: " + ", ".join(f"{l['src']} {l['role']}" for l in downs[:8]) + (" …" if len(downs) > 8 else ""))
    if it["lint"]:
        lines.append("품질: " + "; ".join(f["msg"] for f in it["lint"][:3]))
    return "\n".join(lines)


def _out(reply: str, actions: list | None = None) -> dict:
    return {"mode": "local", "reply": reply, "actions": actions or []}
