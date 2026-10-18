"""Traceability + semantic consistency audit (SUP.1 evidence) and link suggestions."""
from __future__ import annotations

from collections import defaultdict

from .classify import quantities
from .db import Repo
from .importer import bigrams


def allowed_roles(cfg: dict, src_type: str, dst_type: str) -> list[str]:
    roles = []
    for r in cfg["link_rules"]:
        if (r["src"] in (src_type, "*")) and ("*" in r["dst"] or dst_type in r["dst"]):
            roles.append(r["role"])
    return roles


def validate_link(cfg: dict, src_type: str, role: str, dst_type: str) -> bool:
    return role in allowed_roles(cfg, src_type, dst_type)


def run_audit(repo: Repo, cfg: dict) -> dict:
    items = {i["id"]: i for i in repo.items(include_deleted=True)}
    active = {k: v for k, v in items.items() if v["status"] != "deleted"}
    links = repo.links()
    findings = []

    def add(sev, rule, item, msg, related=None):
        findings.append({"sev": sev, "rule": rule, "item": item, "msg": msg, "related": related or []})

    up = defaultdict(list)    # src -> links
    down = defaultdict(list)  # dst -> links
    for l in links:
        up[l["src"]].append(l)
        down[l["dst"]].append(l)
        s, d = items.get(l["src"]), items.get(l["dst"])
        if not s or not d:
            add("error", "dangling", l["src"], f"존재하지 않는 아이템으로의 링크: {l['src']} -{l['role']}-> {l['dst']}")
            continue
        if s["status"] == "deleted" or d["status"] == "deleted":
            if s["status"] != "deleted":
                add("error", "link_to_deleted", l["src"], f"삭제된 {l['dst']} 를 참조 ({l['role']})", [l["dst"]])
            continue
        if not validate_link(cfg, s["type"], l["role"], d["type"]):
            add("error", "link_schema", l["src"],
                f"허용되지 않는 링크: {s['type']} -{l['role']}-> {d['type']} (PAM 4.0 스키마 위반, 예: SWE.5 TC 가 SWE.1 검증)",
                [l["dst"]])
        if l["suspect"]:
            add("warn", "suspect", l["src"], f"상위 {l['dst']} 변경됨 → {l['src']} 재검토 필요 (Suspect)", [l["dst"]])
        if l["state"] == "proposed":
            add("info", "proposed_link", l["src"], f"자동 제안 링크 미확정: {l['role']} → {l['dst']}", [l["dst"]])

    types_present = {i["type"] for i in active.values()}
    coverage = {}
    for rule in cfg["coverage_rules"]:
        if rule.get("only_if_exists") and not (set(rule["types"]) & types_present):
            continue
        targets = [i for i in active.values() if i["type"] == rule["type"]]
        ok = 0
        for it in targets:
            if rule["direction"] == "upstream":
                hit = any(l["role"] == rule["role"] and l["state"] == "confirmed" and items.get(l["dst"], {}).get("type") in rule["types"]
                          and items[l["dst"]]["status"] != "deleted" for l in up[it["id"]])
            else:
                hit = any(l["role"] == rule["role"] and l["state"] == "confirmed" and items.get(l["src"], {}).get("type") in rule["types"]
                          and items[l["src"]]["status"] != "deleted" for l in down[it["id"]])
            if hit:
                ok += 1
            else:
                add(rule["severity"], "coverage", it["id"], rule["msg"])
        key = f"{rule['type']} {rule['direction']} {rule['role']} {'/'.join(rule['types'])}"
        coverage[key] = {"total": len(targets), "covered": ok,
                         "pct": round(100 * ok / len(targets), 1) if targets else 100.0}

    # semantic consistency on numbers/units along confirmed links
    for l in links:
        s, d = active.get(l["src"]), active.get(l["dst"])
        if not s or not d or l["state"] != "confirmed":
            continue
        qs, qd = quantities(s["text"]), quantities(d["text"])
        if not qs or not qd:
            continue
        dims_d = defaultdict(set)
        for q in qd:
            dims_d[q["dim"]].add(q["value"])
        dims_s = defaultdict(set)
        for q in qs:
            dims_s[q["dim"]].add(q["value"])
        for dim in set(dims_s) & set(dims_d):
            if l["role"] == "verifies":
                missing = dims_d[dim] - dims_s[dim]
                if missing:
                    add("warn", "consistency", l["src"],
                        f"{dim}: 상위 {l['dst']} 의 값 {_fmt(missing, qd, dim)} 이(가) 테스트에 없음 (경계값 미검증 의심)", [l["dst"]])
            else:
                extra = dims_s[dim] - dims_d[dim]
                if extra and not (dims_s[dim] & dims_d[dim]):
                    add("warn", "consistency", l["src"],
                        f"{dim} 불일치: {l['src']}={_fmt(dims_s[dim], qs, dim)} vs 상위 {l['dst']}={_fmt(dims_d[dim], qd, dim)}",
                        [l["dst"]])

    # duplicates
    seen = defaultdict(list)
    nids = defaultdict(list)
    for i in active.values():
        if i["type"] in ("CRS", "SYS2", "SWE1", "HSI"):
            seen[(i["type"], i["fingerprint"])].append(i["id"])
            if i["attrs"].get("native_id"):
                nids[(i["type"], i["doc"], i["attrs"]["native_id"])].append(i["id"])
    for ids in seen.values():
        if len(ids) > 1:
            add("warn", "duplicate", ids[0], f"동일 문장 요구사항 중복: {', '.join(ids)}", ids[1:])
    for (_t, doc, nid), ids in nids.items():
        if len(ids) > 1:
            add("warn", "duplicate_native_id", ids[0], f"원문 ID {nid} 중복 ({doc}): {', '.join(ids)}", ids[1:])

    # quality lint carried by the items
    for i in active.values():
        for f in i["lint"]:
            add(f["sev"], "lint:" + f["rule"], i["id"], f["msg"])

    status_count = defaultdict(lambda: defaultdict(int))
    for i in active.values():
        status_count[i["type"]][i["status"]] += 1

    sev_count = defaultdict(int)
    for f in findings:
        sev_count[f["sev"]] += 1
    return {"summary": {"items": len(active), "links": len(links), "errors": sev_count["error"],
                        "warnings": sev_count["warn"], "infos": sev_count["info"]},
            "coverage": coverage, "status": {k: dict(v) for k, v in status_count.items()},
            "findings": sorted(findings, key=lambda f: ({"error": 0, "warn": 1, "info": 2}[f["sev"]], f["item"]))}


def _fmt(values, qs, dim):
    raws = sorted({q["raw"] for q in qs if q["dim"] == dim and q["value"] in values})
    return "/".join(raws) if raws else str(sorted(values))


def suggest_links(repo: Repo, cfg: dict, src_type: str, dst_type: str, min_score: float = 0.2,
                  top: int = 2, apply: bool = True) -> list[dict]:
    roles = [r for r in allowed_roles(cfg, src_type, dst_type) if r != "relates"]
    if not roles:
        raise ValueError(f"{src_type} → {dst_type} 로 허용된 링크 역할이 없습니다 (alm.json link_rules)")
    role = roles[0]
    srcs = repo.items(type_=src_type)
    dsts = repo.items(type_=dst_type)
    dst_b = {d["id"]: bigrams(d["text"]) for d in dsts}
    dst_q = {d["id"]: {(q["dim"], q["value"]) for q in quantities(d["text"])} for d in dsts}
    existing = {(l["src"], l["dst"]) for l in repo.links()}
    out = []
    for s in srcs:
        sb = bigrams(s["text"])
        sq = {(q["dim"], q["value"]) for q in quantities(s["text"])}
        scored = []
        for d in dsts:
            j = len(sb & dst_b[d["id"]]) / max(1, len(sb | dst_b[d["id"]]))
            if s["section"] and s["section"] == d["section"]:
                j += 0.15
            if sq & dst_q[d["id"]]:
                j += 0.1 * len(sq & dst_q[d["id"]])
            if s["doc"] == d["doc"] and abs(s["ord"] - d["ord"]) <= 30:
                j += 0.05
            scored.append((round(j, 3), d))
        scored.sort(key=lambda x: -x[0])
        for sc, d in scored[:top]:
            if sc < min_score or (s["id"], d["id"]) in existing:
                continue
            out.append({"src": s["id"], "role": role, "dst": d["id"], "score": sc})
            if apply:
                repo.add_link(s["id"], role, d["id"], state="proposed", note=f"auto score={sc}")
    if apply:
        repo.commit()
    return out
