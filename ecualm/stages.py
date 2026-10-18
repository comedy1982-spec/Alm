"""ASPICE stage model.

* stage_doc()  builds the live document of a stage in PAM 4.0 structure (an SRS for SYS.2, an SWRS
               for SWE.1, ...) from the work items, grouped either by domain or by source section.
* derive()     deploys items of one stage into draft items of the next stage, with trace links:
               CRS → SYS.2 → SYS.3/HSI → SWE.1 → SWE.2 → SWE.3, the HW branch SYS.2 → HWE.1 → HWE.2
               (and SYS.3 → HWE.2), and every spec stage → its test stage.
Everything derived is rule-based and lands in 'draft' with a `derived_from` attribute, so a human
reviews it before it counts. The optional AI step can refine the same items afterwards.
"""
from __future__ import annotations

import re
from collections import defaultdict

from .classify import Analyzer, quantities
from .db import Repo
from .importer import REQ_TYPES, fingerprint
from .ops import _fmt

PART_RE = re.compile(r"\b([A-Z]{2,}[0-9]{3,}[A-Z0-9/-]*)\b")
TRIGGER_RE = re.compile(r"^(?P<pre>.*?)(?P<trig>[^,，]*?(?:이면|되면|하면|시에|경우|때|동안|이후|후에|수신 시|요청 시|검출 시)\s*[,，]?\s*)(?P<rest>.+)$")
STATE_RE = re.compile(r"(IG\s*ON|IG\s*OFF|NORMAL|INIT|SLEEP|FAIL-?SAFE|확장 세션|기본 세션|정상 상태|초기화)", re.I)


def stage_of_type(cfg: dict, typ: str) -> dict | None:
    for s in cfg["stages"]:
        if typ in s["types"]:
            return s
    return None


def get_stage(cfg: dict, sid: str) -> dict:
    for s in cfg["stages"]:
        if s["id"] == sid:
            return s
    raise ValueError(f"알 수 없는 단계: {sid}")


def _carry(a: dict) -> dict:
    """ASIL and verification method from the customer requirement (own attrs or its table row fields)."""
    f = {str(k).replace(" ", "").lower(): v for k, v in (a.get("fields") or {}).items()}
    out = {}
    asil = a.get("asil") or f.get("asil")
    if asil:
        out["asil"] = str(asil).replace("ASIL", "").strip() or str(asil)
    vm = a.get("verification_method") or f.get("검증방법") or f.get("verification") or f.get("verificationmethod")
    if vm:
        out["verification_method"] = vm
    return out


def stage_counts(repo: Repo, cfg: dict) -> dict:
    items = repo.items()
    links = repo.links()
    by_type: dict[str, list] = defaultdict(list)
    for i in items:
        by_type[i["type"]].append(i)
    ids = {i["id"]: i for i in items}
    up = defaultdict(list)
    for l in links:
        up[l["src"]].append(l)
    out = {}
    for s in cfg["stages"]:
        its = [i for t in s["types"] for i in by_type.get(t, [])]
        st = defaultdict(int)
        for i in its:
            st[i["status"]] += 1
        suspect = sum(1 for l in links if l["suspect"] and ids.get(l["src"], {}).get("type") in s["types"])
        linked_up = 0
        for i in its:
            if any(l["state"] == "confirmed" and l["role"] != "relates" for l in up[i["id"]]):
                linked_up += 1
        out[s["id"]] = {"total": len(its), "status": dict(st), "suspect": suspect, "linked_up": linked_up,
                        "lint": sum(1 for i in its if i["lint"])}
    return out


# ------------------------------------------------------------------ stage document
def stage_doc(repo: Repo, cfg: dict, sid: str, mode: str = "pam") -> dict:
    st = get_stage(cfg, sid)
    items = [i for i in repo.items() if i["type"] in st["types"]]
    links = repo.links()
    up, down = defaultdict(list), defaultdict(list)
    for l in links:
        up[l["src"]].append(l)
        down[l["dst"]].append(l)
    docs = sorted({i["doc"] for i in items if i["doc"]})
    revs = {d["doc"]: d["rev"] for d in repo.docs()}
    sections: list[dict] = []

    if mode == "source":
        # keep the imported document's structure (headings, tables, figures) and show this stage's items in place
        for d in docs:
            all_items = repo.items(doc=d)
            keep = {"HDG", "INFO", "TBL", "FIG", *st["types"]}
            rows = [i for i in all_items if i["type"] in keep]
            sections.append({"number": "", "title": f"{d} (rev {revs.get(d, '')})", "items": rows, "kind": "source"})
        return {"stage": st, "mode": mode, "title": f"{st['name']} — 원문 구조", "sections": sections,
                "docs": docs, "stats": _stats(items)}

    # ---- PAM 4.0 layout ----
    overview = [i for d in docs for i in repo.items(doc=d, type_="INFO") if "개요" in i["section"] or i["ord"] < 60][:6]
    sections.append({"number": "1", "title": "목적 및 범위", "kind": "text",
                     "text": [i["text"] for i in overview] or [f"[{st['name']} 문서의 목적과 적용 범위를 기술하세요]"]})
    refs = [f"{d} rev {revs.get(d, '')}" for d in docs]
    upstream_types = {l["dst"] for i in items for l in up[i["id"]]}
    up_items = {k: v for k, v in ((x, repo.get(x)) for x in upstream_types) if v}
    up_docs = sorted({v["doc"] for v in up_items.values() if v["doc"]})
    sections.append({"number": "2", "title": "참조 문서", "kind": "text",
                     "text": refs + [f"{d} (상위 단계)" for d in up_docs if d not in docs] or ["[참조 문서 없음]"]})
    sections.append({"number": "3", "title": "용어 및 약어", "kind": "text",
                     "text": ["ASIL — Automotive Safety Integrity Level", "HSI — Hardware-Software Interface",
                              "TC — Test Case", "[프로젝트 용어를 추가하세요]"]})

    by_dom: dict[str, list] = defaultdict(list)
    for i in items:
        by_dom[i["domain"]].append(i)
    order = [d for d in cfg["domain_names"] if d in by_dom] + [d for d in by_dom if d not in cfg["domain_names"]]
    main_title = {"SYS1": "고객 요구사항", "SYS2": "시스템 요구사항", "SYS3": "시스템 요소 및 HW-SW 인터페이스",
                  "SWE1": "소프트웨어 요구사항", "SWE2": "소프트웨어 아키텍처 요소", "SWE3": "소프트웨어 유닛 설계",
                  "HWE1": "하드웨어 요구사항", "HWE2": "하드웨어 블록 및 인터페이스"}.get(sid, "테스트 케이스")
    n = 4
    sub = []
    for k, d in enumerate(order, 1):
        rows = sorted(by_dom[d], key=lambda i: (i["doc"], i["ord"]))
        for i in rows:
            i["_up"] = [l for l in up[i["id"]]]
            i["_down"] = [l for l in down[i["id"]]]
        sub.append({"number": f"{n}.{k}", "title": cfg["domain_names"].get(d, d), "items": rows, "kind": "items"})
    sections.append({"number": str(n), "title": main_title, "kind": "group", "sub": sub})

    if sid in ("SYS2", "SWE1", "SYS1", "HSI", "HWE1"):
        n += 1
        vc = [{"id": i["id"], "criteria": i["attrs"].get("verification_criteria") or "[검증 기준 작성 필요]",
               "method": i["attrs"].get("verification_method") or (i["attrs"].get("fields") or {}).get("검증방법") or "",
               "tc": [l["src"] for l in down[i["id"]] if l["role"] == "verifies"]} for i in items]
        sections.append({"number": str(n), "title": "검증 기준", "kind": "verification", "rows": vc})
    n += 1
    trace = [{"id": i["id"], "up": [f"{l['role']} {l['dst']}" + (" (제안)" if l["state"] == "proposed" else "") for l in up[i["id"]]],
              "down": [f"{l['src']} {l['role']}" for l in down[i["id"]]]} for i in items]
    sections.append({"number": str(n), "title": "추적 매트릭스", "kind": "trace", "rows": trace})
    return {"stage": st, "mode": mode, "title": f"{st['name']} ({st['aspice']})", "sections": sections, "docs": docs,
            "stats": _stats(items)}


def _stats(items):
    st = defaultdict(int)
    for i in items:
        st[i["status"]] += 1
    return {"total": len(items), "status": dict(st), "lint": sum(1 for i in items if i["lint"]),
            "domains": dict(sorted(((d, sum(1 for i in items if i["domain"] == d)) for d in {i["domain"] for i in items})))}


# ------------------------------------------------------------------ derivation
def _has_target(repo: Repo, src_id: str, role: str, dst_types: set, direction: str) -> bool:
    for l in repo.links(src_id):
        if l["role"] != role:
            continue
        other = l["dst"] if direction == "up" and l["src"] == src_id else (l["src"] if direction == "down" and l["dst"] == src_id else None)
        if other:
            o = repo.get(other)
            if o and o["type"] in dst_types and o["status"] != "deleted":
                return True
    return False


def _new(repo: Repo, cfg: dict, typ: str, text: str, domain: str, src: dict, attrs: dict, title: str = "",
         lint=None, user: str = "derive") -> dict:
    an = Analyzer(cfg)
    new_id = repo.next_id(_fmt(cfg, typ, domain), cfg["types"][typ]["prefix"], domain, cfg)
    a = {"derived_from": src["id"], "quantities": quantities(text), **attrs}
    it = repo.insert({"id": new_id, "type": typ, "domain": domain, "title": title or text[:80], "text": text,
                      "attrs": a, "lint": lint if lint is not None else (an.lint(text, typ) if typ in REQ_TYPES else []),
                      "doc": src["doc"], "doc_rev": src["doc_rev"], "section": src["section"],
                      "source_loc": f"derived:{src['id']}", "ord": src["ord"] + 0.5, "fingerprint": fingerprint(text)}, by=user)
    return it


def spec_template(text: str, section: str = "") -> dict:
    """Split a requirement sentence into the PAM 4.0 SWE.1 template fields (heuristic)."""
    m = TRIGGER_RE.match(text)
    pre = STATE_RE.findall(f"{section} {text}")
    out = {"pre_condition": ", ".join(dict.fromkeys(p.strip() for p in pre)) or "[전제 조건]",
           "trigger": "", "processing": "", "output": "", "timing": ""}
    if m and m.group("trig").strip():
        out["trigger"] = (m.group("pre") + m.group("trig")).strip(" ,，")
        out["output"] = m.group("rest").strip()
    else:
        out["output"] = text
    t = [q for q in quantities(text) if q["dim"] == "time"]
    if t:
        out["timing"] = " / ".join(q["raw"] for q in t)
    cyc = re.search(r"(\d+\s*(?:ms|us|μs|µs))\s*(?:주기|cycle|마다)", text, re.I)
    out["task_cycle"] = cyc.group(1).replace(" ", "") if cyc else ""
    return out


def _verification_criteria(text: str, dom: str) -> str:
    qs = quantities(text)
    if qs:
        return "측정: " + ", ".join(f"{q['raw']} 경계 포함" for q in qs[:3]) + " — 정상/경계/에러 조건에서 합격 판정"
    hint = {"COM": "CANoe/CAPL 로그로 메시지·신호 확인", "DIAG": "UDS 진단기로 요청/응답(NRC 포함) 확인",
            "SAFE": "고장 주입 후 Fail-safe 동작 및 DTC 확인", "MOT": "다이나모/엔코더로 위치·토크 응답 측정",
            "PWR": "전원 공급기로 전압 프로파일 인가 후 동작 확인", "ENV": "환경 챔버/EMC 시험 규격 적용"}
    return hint.get(dom, "시험 절차로 요구사항 충족 여부 확인")


def derive(repo: Repo, cfg: dict, src_stage: str, dst_stage: str, ids: list[str] | None = None,
           user: str = "derive") -> dict:
    src = get_stage(cfg, src_stage)
    dst = get_stage(cfg, dst_stage)
    if dst_stage not in src.get("next", []) and dst.get("verifies") != src_stage:
        raise ValueError(f"{src['aspice']} → {dst['aspice']} 전개는 정의되어 있지 않습니다 (alm.json stages.next)")
    an = Analyzer(cfg)
    srcs = [i for i in repo.items() if i["type"] in src["types"] and (not ids or i["id"] in ids)]
    created, linked, skipped = [], [], []
    cache: dict[str, dict] = {}   # name -> element item (SYS3/SWE2 dedupe)

    def element(typ: str, name: str, domain: str, s: dict, attrs: dict) -> dict:
        if name in cache:
            return cache[name]
        ex = next((i for i in repo.items(type_=typ) if i["title"] == name), None)
        if ex is None:
            ex = _new(repo, cfg, typ, name, domain, s, attrs, title=name, lint=[], user=user)
            created.append(ex["id"])
        cache[name] = ex
        return ex

    for s in srcs:
        dom = s["domain"] if s["domain"] != "HSI" else "GEN"
        pair = (src_stage, dst_stage)

        if pair == ("SYS1", "SYS2"):
            if _has_target(repo, s["id"], "derives", {"SYS2"}, "down"):
                skipped.append(s["id"]); continue
            lvl, conf = an.level(s["text"], s["section"])
            it = _new(repo, cfg, "SYS2", s["text"], dom, s,
                      {"discipline": "SW" if lvl == "SWE1" else "HW/SYS", "level_confidence": conf,
                       "verification_criteria": _verification_criteria(s["text"], dom), "native_id": s["attrs"].get("native_id", ""),
                       **_carry(s["attrs"])}, user=user)
            repo.add_link(it["id"], "derives", s["id"]); created.append(it["id"]); linked.append((it["id"], s["id"]))

        elif pair == ("SYS2", "SWE1"):
            lvl, conf = an.level(s["text"], s["section"])
            # pure HW / mechanical / environmental system requirements stay at SYS.2 (verified by SYS.5)
            if lvl == "SYS2" and (conf >= 0.6 or dom in ("ENV", "MECH")):
                skipped.append(s["id"]); continue
            if _has_target(repo, s["id"], "refines", {"SWE1"}, "down"):
                skipped.append(s["id"]); continue
            spec = spec_template(s["text"], s["section"])
            it = _new(repo, cfg, "SWE1", s["text"], dom, s,
                      {"spec": spec, "task_cycle": spec.get("task_cycle", ""), "asil": (s["attrs"].get("fields") or {}).get("ASIL", ""),
                       "target_layer": "CDD" if re.search(r"PWM|전류|ADC|GTM|EVADC", s["text"]) else "ASW",
                       "verification_criteria": _verification_criteria(s["text"], dom)}, user=user)
            repo.add_link(it["id"], "refines", s["id"]); created.append(it["id"]); linked.append((it["id"], s["id"]))
            # HSI entries that mention the same signal family are proposed as `uses`
            for h in repo.items(type_="HSI"):
                if _signal_match(h, s["text"]):
                    repo.add_link(it["id"], "uses", h["id"], state="proposed", note="signal match")

        elif pair == ("SYS2", "SYS3"):
            names = cfg["sys3_allocation"].get(dom, cfg["sys3_allocation"]["GEN"])
            for name in names:
                el = element("SYS3", name, dom, s, {"element_kind": "system element"})
                if not any(l["src"] == el["id"] and l["dst"] == s["id"] for l in repo.links(s["id"])):
                    repo.add_link(el["id"], "satisfies", s["id"]); linked.append((el["id"], s["id"]))
            for h in repo.items(type_="HSI"):
                if _signal_match(h, s["text"]) and not any(l["src"] == h["id"] and l["dst"] == s["id"] for l in repo.links(s["id"])):
                    repo.add_link(h["id"], "satisfies", s["id"], state="proposed", note="signal match"); linked.append((h["id"], s["id"]))

        elif pair == ("SYS2", "HWE1"):
            if not _hw_relevant(an, cfg, s, dom):
                skipped.append(s["id"]); continue
            if _has_target(repo, s["id"], "refines", {"HWE1"}, "down"):
                skipped.append(s["id"]); continue
            it = _new(repo, cfg, "HWE1", s["text"], dom, s,
                      {"discipline": "HW", "asil": s["attrs"].get("asil") or (s["attrs"].get("fields") or {}).get("ASIL", ""),
                       "verification_method": s["attrs"].get("verification_method", ""),
                       "verification_criteria": s["attrs"].get("verification_criteria") or _verification_criteria(s["text"], dom)}, user=user)
            repo.add_link(it["id"], "refines", s["id"]); created.append(it["id"]); linked.append((it["id"], s["id"]))
            for h in repo.items(type_="HSI"):
                if _signal_match(h, s["text"]):
                    repo.add_link(it["id"], "uses", h["id"], state="proposed", note="signal match")

        elif pair == ("SYS3", "HWE2"):
            if s["type"] != "SYS3" or not _hw_block_name(s["title"]):
                skipped.append(s["id"]); continue
            el = element("HWE2", s["title"], dom, s, _block_attrs(s["title"]))
            if not any(l["src"] == el["id"] and l["dst"] == s["id"] for l in repo.links(s["id"])):
                repo.add_link(el["id"], "refines", s["id"]); linked.append((el["id"], s["id"]))

        elif pair == ("HWE1", "HWE2"):
            if _has_target(repo, s["id"], "satisfies", {"HWE2"}, "down"):
                skipped.append(s["id"]); continue
            names = [n for n in cfg["sys3_allocation"].get(dom, cfg["sys3_allocation"]["GEN"]) if _hw_block_name(n)]
            for name in names:
                el = element("HWE2", name, dom, s, _block_attrs(name))
                repo.add_link(el["id"], "satisfies", s["id"]); linked.append((el["id"], s["id"]))
                sys3 = next((i for i in repo.items(type_="SYS3") if i["title"] == name), None)
                if sys3 and not any(l["dst"] == sys3["id"] and l["role"] == "refines" for l in repo.links(el["id"])):
                    repo.add_link(el["id"], "refines", sys3["id"])
            if s["attrs"].get("asil"):
                for name in names:
                    el = cache[name]
                    if el["attrs"].get("asil", "QM") in ("", "QM"):
                        el = repo.update(el["id"], {"attrs": {**el["attrs"], "asil": s["attrs"]["asil"]}}, bump_version=False)
                        cache[name] = el

        elif pair == ("SWE1", "SWE2"):
            if _has_target(repo, s["id"], "allocates", {"SWE2"}, "down"):
                skipped.append(s["id"]); continue
            comps = cfg["swe2_allocation"].get(dom, cfg["swe2_allocation"]["GEN"])
            for c in comps:
                if c.get("if") and not any(w.lower() in s["text"].lower() for w in c["if"]):
                    continue
                el = element("SWE2", c["name"], dom, s, {"autosar_layer": c["layer"], "runnable_cycle": s["attrs"].get("task_cycle", ""),
                                                        "rte_ports": [], "plantuml": f"@startuml\ncomponent {c['name']}\n@enduml"})
                repo.add_link(el["id"], "allocates", s["id"]); linked.append((el["id"], s["id"]))

        elif pair == ("SWE2", "SWE3"):
            if _has_target(repo, s["id"], "refines", {"SWE3"}, "down"):
                skipped.append(s["id"]); continue
            base = re.sub(r"^(SWC|CDD|BSW)_", "", s["title"])
            for fn in (f"{base}_Init", f"{base}_MainFunction"):
                it = _new(repo, cfg, "SWE3", f"{fn}(): {s['title']} 의 {'초기화' if fn.endswith('Init') else '주기 처리'} 유닛", dom, s,
                          {"c_file": f"{base}.c", "function_signature": f"void {fn}(void)", "complexity_target": 10,
                           "cycle": s["attrs"].get("runnable_cycle", "")}, title=fn, lint=[], user=user)
                repo.add_link(it["id"], "refines", s["id"]); created.append(it["id"]); linked.append((it["id"], s["id"]))

        elif dst.get("verifies") == src_stage:
            tc_type = dst["types"][0]
            if _has_target(repo, s["id"], "verifies", {tc_type}, "down"):
                skipped.append(s["id"]); continue
            for tc in _test_cases(s, dom, dst_stage):
                it = _new(repo, cfg, tc_type, tc["text"], dom, s, tc["attrs"], title=tc["title"], lint=[], user=user)
                repo.add_link(it["id"], "verifies", s["id"]); created.append(it["id"]); linked.append((it["id"], s["id"]))
        else:
            raise ValueError(f"{src_stage} → {dst_stage} 전개 규칙이 없습니다")

    repo.commit()
    return {"from": src_stage, "to": dst_stage, "sources": len(srcs), "created": created, "links": len(linked), "skipped": skipped}


def _hw_relevant(an: Analyzer, cfg: dict, s: dict, dom: str) -> bool:
    if dom in ("MECH", "MFG") or re.match(r"^\s*(SW|S/W|소프트웨어|software)(?![A-Za-z0-9])", s["text"], re.I):
        return False   # mechanical / production stay at SYS.2; a sentence whose subject is the SW goes to SWE.1
    kw = any(k.lower() in s["text"].lower() for k in cfg.get("hwe1_keywords", []))
    if dom in cfg.get("hwe1_domains", []):
        lvl, conf = an.level(s["text"], s["section"])
        return kw or not (lvl == "SWE1" and conf >= 0.6)
    return kw


def _hw_block_name(name: str) -> bool:
    return not any(w in name for w in ("기구", "SW", "소프트웨어", "하우징"))


def _block_attrs(name: str) -> dict:
    m = PART_RE.search(name)
    return {"block_kind": "HW block", "asil": "QM",
            "hw": {"part_number": m.group(1) if m else "", "interfaces": "", "safety_mechanism": ""}}


def _signal_match(hsi: dict, text: str) -> bool:
    f = hsi["attrs"].get("fields") or {}
    hay = " ".join(f.values()).upper()
    t = text.upper()
    fam = [("PWM", "PWM"), ("CAN", "CAN"), ("ADC", "전류"), ("EVADC", "전류"), ("ADC", "ADC"), ("HALL", "홀"), ("ENC", "엔코더")]
    return any(a in hay and b in t for a, b in fam)


def _test_cases(s: dict, dom: str, dst_stage: str) -> list[dict]:
    text = s["text"]
    qs = quantities(text)
    tool = {"SWE6": "CANoe/CAPL · 고장주입", "SYS5": "차량/벤치/환경 챔버", "SWE5": "SIL/TRACE32 · RTE 인터페이스",
            "SYS4": "오실로스코프/HIL", "SWE4": "GoogleTest/VectorCAST",
            "HWE3": "오실로스코프·파워서플라이·전자부하", "HWE4": "환경 챔버·EMC 챔버·HIL"}[dst_stage]
    if dst_stage == "HWE3" and s["type"] == "HWE2":
        out = [{"title": f"{s['id']} 설계 검증",
                "text": f"[설계검증] {s['title']}: 전원·인터페이스의 전기적 특성(전압 레벨, 타이밍, 부하)을 측정하여 설계값 이내인지 확인한다.",
                "attrs": {"kind": "design_verification", "tool": tool, "pre_condition": "벤치, 정격 전원 13.5V, 25°C",
                          "expected": "측정값이 부품 데이터시트·설계값 이내", "pass_criteria": "모든 측정 항목 합격"}}]
        if (s["attrs"].get("asil") or "QM") not in ("", "QM") or dom in ("SAFE", "PWR"):
            out.append({"title": f"{s['id']} 고장 주입 (FTTI)",
                        "text": f"[고장주입] {s['title']}: 단락·개방·과전류 조건을 인가하고 안전 메커니즘이 FTTI 이내에 안전 상태로 전환하는지 파형으로 확인한다.",
                        "attrs": {"kind": "fault_injection", "tool": tool, "expected": "FTTI 이내 Safe State 진입",
                                  "pass_criteria": "반응 시간 < FTTI, 파형 첨부"}})
        return out
    out = [{"title": f"{s['id']} 정상 조건",
            "text": f"[정상] {text} — 규정 조건을 충족하는 입력을 인가하고 기대 출력이 발생하는지 확인한다.",
            "attrs": {"kind": "nominal", "tool": tool, "pre_condition": "IG ON, 정상 상태",
                      "expected": "요구사항에 기술된 출력/상태", "pass_criteria": "기대 출력 100% 일치"}}]
    scale = {"ms": 1e3, "us": 1e6, "μs": 1e6, "µs": 1e6, "s": 1, "v": 1, "mv": 1e3, "a": 1, "ma": 1e3, "°c": 1, "deg": 1, "mm": 1e3, "%": 1}
    fmt = lambda x: f"{x:.10g}"
    groups: dict[str, list] = {}
    for q in qs:
        groups.setdefault(q["raw"], []).append(q)
    for raw, grp in list(groups.items())[:2]:
        unit = grp[0]["unit"]
        if raw.lower().endswith(unit.lower()):
            unit = raw[len(raw) - len(unit):]      # keep the document's spelling (A, mV, µs ...)
        sc = scale.get(unit.lower(), 1)
        vals = sorted({q["value"] * sc for q in grp})
        step = 10 if vals[0] >= 100 else (0.1 if vals[0] < 10 else 1)
        if len(vals) >= 2:   # a range "9V ~ 16V": 4-point BVA
            lo, hi = vals[0], vals[-1]
            pts = [lo - step, lo, hi, hi + step]
            text = (f"[경계값] {fmt(pts[0])}{unit} (범위 밖) 미충족, {fmt(pts[1])}{unit} 및 {fmt(pts[2])}{unit} (범위 끝) 충족, "
                    f"{fmt(pts[3])}{unit} (범위 밖) 미충족을 확인한다 (대상: {raw}).")
            crit = f"{fmt(pts[1])}~{fmt(pts[2])}{unit} 안: 요구 동작, 밖: 요구 동작 없음"
        else:                # a threshold "500ms 이상": both sides of the edge
            v = vals[0]
            pts = [v - step, v]
            text = f"[경계값] {fmt(pts[0])}{unit} 와 {fmt(pts[1])}{unit} 의 양측에서 판정이 달라지는지 확인한다 (대상: {raw})."
            crit = f"{fmt(pts[0])}{unit} / {fmt(pts[1])}{unit} 에서 판정 결과가 요구사항과 일치"
        out.append({"title": f"{s['id']} 경계값 {raw}", "text": text,
                    "attrs": {"kind": "boundary", "tool": tool, "boundary": [f"{fmt(p)}{unit}" for p in pts], "pass_criteria": crit}})
    if (dom in ("SAFE", "COM", "DIAG") and dst_stage in ("SWE6", "SYS5")) or \
       (dst_stage in ("HWE3", "HWE4") and (dom in ("SAFE", "PWR") or (s["attrs"].get("asil") or "QM") not in ("", "QM"))):
        hw = dst_stage in ("HWE3", "HWE4")
        out.append({"title": f"{s['id']} 고장 주입",
                    "text": ("[고장주입] 단락·개방·과전류·저전압 조건을 인가하고 하드웨어 안전 메커니즘의 반응 시간과 안전 상태를 파형으로 확인한다."
                             if hw else "[고장주입] 관련 신호 단선/타임아웃/CRC 오류를 주입하고 Fail-safe 동작과 DTC 발생을 확인한다."),
                    "attrs": {"kind": "fault_injection", "tool": tool, "expected": "Fail-safe 진입 + DTC 저장",
                              "pass_criteria": "규정 시간 내 안전 상태 진입"}})
    return out
