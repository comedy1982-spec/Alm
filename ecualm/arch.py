"""Architecture canvas (diagram-as-code), interfaces, test results and artifact JSON.

* A block on a canvas IS a work item (SYS3 / HWE2 / SWE2). Its position lives in attrs.canvas_layout
  and moving it never creates a new version (layout is not content).
* A line between two blocks IS a work item of type IF (its own ID, versioned, verifiable). It
  `connects` both blocks, so a change of either block marks the interface suspect.
* Test results (CI / HIL / bench) are attached to TC items without a version bump. Each result
  records the version of every item the TC verifies, so the audit can tell when a PASS is stale.
* export_arch / import_arch round-trip a canvas as plain JSON so it can live in Git next to the code.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import ops
from .db import Repo

CANVAS_TYPES = {"SYS3": "SYS3", "HWE2": "HWE2", "SWE2": "SWE2"}
RESULT_STATES = ("PASS", "FAIL", "BLOCKED", "NOT_RUN")
SAMPLE = Path(__file__).parent / "data" / "hw_arch_bldc.json"


def _block_type(canvas: str) -> str:
    if canvas not in CANVAS_TYPES:
        raise ValueError(f"블록도가 없는 단계: {canvas} (가능: {', '.join(CANVAS_TYPES)})")
    return CANVAS_TYPES[canvas]


# ------------------------------------------------------------------ layout / blocks / interfaces
def set_layout(repo: Repo, positions: dict) -> int:
    n = 0
    for iid, pos in positions.items():
        it = repo.get(iid)
        if not it:
            continue
        a = dict(it["attrs"])
        a["canvas_layout"] = {"x": round(float(pos["x"])), "y": round(float(pos["y"]))}
        repo.update(iid, {"attrs": a}, bump_version=False)
        n += 1
    repo.commit()
    return n


def create_block(repo: Repo, cfg: dict, canvas: str, title: str, text: str = "", domain: str = "GEN",
                 x: float = 40, y: float = 40, attrs: dict | None = None, user: str = "") -> dict:
    typ = _block_type(canvas)
    a = {"block_kind": {"HWE2": "HW block", "SYS3": "system element", "SWE2": "SW component"}[canvas],
         "asil": "QM", "canvas_layout": {"x": round(x), "y": round(y)}}
    if canvas == "HWE2":
        a["hw"] = {"part_number": "", "interfaces": "", "safety_mechanism": ""}
    a.update(attrs or {})
    return ops.create_item(repo, cfg, typ, text or title, domain=domain, title=title, attrs=a, user=user)


def create_interface(repo: Repo, cfg: dict, canvas: str, src: str, dst: str, name: str, signal_class: str = "digital",
                     signals: list | str | None = None, user: str = "") -> dict:
    a, b = repo.get(src), repo.get(dst)
    if not a or not b:
        raise KeyError(f"블록 없음: {src if not a else dst}")
    if src == dst:
        raise ValueError("같은 블록끼리는 연결할 수 없습니다")
    if signal_class not in cfg.get("signal_classes", {}):
        raise ValueError(f"알 수 없는 신호 분류: {signal_class}")
    if isinstance(signals, str):
        signals = [s.strip() for s in signals.replace(";", ",").split(",") if s.strip()]
    name = name.strip() or f"{a['title']} → {b['title']}"
    it = ops.create_item(repo, cfg, "IF", f"{name}: {a['title']} → {b['title']}", domain="GEN", title=name,
                         doc=a["doc"], attrs={"canvas": canvas, "from": src, "to": dst, "signal_class": signal_class,
                                              "signals": signals or []}, user=user)
    ops.link(repo, cfg, it["id"], "connects", src)
    ops.link(repo, cfg, it["id"], "connects", dst)
    return repo.get(it["id"])


# ------------------------------------------------------------------ test results
def _norm_status(s: str) -> str:
    s = str(s or "").strip().upper().replace("-", "_").replace(" ", "_")
    s = {"OK": "PASS", "PASSED": "PASS", "NG": "FAIL", "FAILED": "FAIL", "ERROR": "FAIL", "SKIP": "BLOCKED",
         "SKIPPED": "BLOCKED", "NOTRUN": "NOT_RUN"}.get(s, s)
    if s not in RESULT_STATES:
        raise ValueError(f"결과 상태는 {RESULT_STATES} 중 하나여야 합니다: {s}")
    return s


def ingest_results(repo: Repo, cfg: dict, payload, user: str = "ci") -> dict:
    """payload: {"results":[{tc, status, run_id?, tool?, at?, metrics?, note?, waveform?}]} or a bare list.
    `tc` is an ECU-ALM ID or the TC's native_id."""
    rows = payload.get("results", []) if isinstance(payload, dict) else payload
    by_native = {i["attrs"].get("native_id"): i for i in repo.items() if i["attrs"].get("native_id")}
    updated, unknown = [], []
    for r in rows:
        tc = repo.get(str(r.get("tc", ""))) or by_native.get(r.get("tc"))
        if not tc or not tc["type"].endswith("_TC"):
            unknown.append(r.get("tc")); continue
        verified = {l["dst"]: (repo.get(l["dst"]) or {}).get("version") for l in repo.links(tc["id"])
                    if l["src"] == tc["id"] and l["role"] == "verifies"}
        rec = {"status": _norm_status(r.get("status")), "run_id": str(r.get("run_id", "")), "tool": r.get("tool", ""),
               "at": r.get("at") or time.time(), "by": user, "metrics": r.get("metrics") or {}, "note": r.get("note", ""),
               "verified_versions": verified}
        if r.get("waveform"):
            rec["waveform"] = r["waveform"]
        a = dict(tc["attrs"])
        hist = [{k: v for k, v in x.items() if k != "waveform"} for x in a.get("results", [])]
        a["result"] = rec
        a["results"] = (hist + [{k: v for k, v in rec.items() if k != "waveform"}])[-20:]
        repo.update(tc["id"], {"attrs": a}, bump_version=False)
        updated.append(tc["id"])
    repo.commit()
    return {"updated": updated, "unknown": [u for u in unknown if u]}


# ------------------------------------------------------------------ artifact JSON (one item, all its trace)
def artifact_json(repo: Repo, cfg: dict, iid: str) -> dict:
    it = repo.get(iid)
    if not it:
        raise KeyError(iid)
    a = it["attrs"]
    t = cfg["types"].get(it["type"], {})
    up, sw, ver, ifs, other = [], [], [], [], []
    for l in repo.links(iid):
        if l["src"] == iid:
            d = repo.get(l["dst"]) or {}
            if it["type"] == "IF" and l["role"] == "connects":
                continue
            up.append({"role": l["role"], "id": l["dst"], "type": d.get("type"), "state": l["state"], "suspect": bool(l["suspect"])})
        else:
            s = repo.get(l["src"]) or {}
            if s.get("status") == "deleted":
                continue
            if l["role"] == "controls":
                sw.append({"id": l["src"], "type": s.get("type"), "title": s.get("title"), "suspect": bool(l["suspect"])})
            elif l["role"] == "verifies":
                res = (s.get("attrs") or {}).get("result") or {}
                ver.append({"tc_id": l["src"], "status": res.get("status", "NOT_RUN"), "run_id": res.get("run_id", ""),
                            "metrics": res.get("metrics", {}), "suspect": bool(l["suspect"])})
            elif l["role"] == "connects":
                sa = s.get("attrs") or {}
                ifs.append({"id": l["src"], "name": s.get("title"), "signal_class": sa.get("signal_class"),
                            "peer": sa.get("to") if sa.get("from") == iid else sa.get("from"),
                            "direction": "out" if sa.get("from") == iid else "in", "signals": sa.get("signals", [])})
            else:
                other.append({"role": l["role"], "id": l["src"], "type": s.get("type")})
    baseline = None
    for b in reversed(repo.baselines()):
        snap = repo.baseline(b["name"]) or {}
        hit = next((x for x in snap.get("items", []) if x["id"] == iid), None)
        if hit:
            baseline = {"name": b["name"], "version": hit["version"]}
            break
    out = {"artifact_id": iid, "aspice_process": t.get("aspice", ""), "artifact_type": t.get("name", it["type"]),
           "title": it["title"], "text": it["text"], "status": it["status"], "version": it["version"],
           "baseline": baseline, "safety_classification": a.get("asil") or "QM", "domain": it["domain"]}
    if a.get("hw"):
        out["hw_attributes"] = a["hw"]
    if it["type"] == "IF":
        out["interface"] = {k: a.get(k) for k in ("canvas", "from", "to", "signal_class", "signals")}
    if a.get("canvas_layout"):
        out["canvas_layout"] = {**a["canvas_layout"], "canvas": next((k for k, v in CANVAS_TYPES.items() if v == it["type"]), "")}
    if a.get("result"):
        out["latest_result"] = {k: v for k, v in a["result"].items() if k != "waveform"}
    out["traceability"] = {"upstream": up, "allocated_to_sw": sw, "verified_by_downstream": ver, "interfaces": ifs,
                           "other_downstream": other}
    return out


# ------------------------------------------------------------------ canvas as code (Git)
def export_arch(repo: Repo, cfg: dict, canvas: str) -> dict:
    typ = _block_type(canvas)
    blocks = [i for i in repo.items(type_=typ)]
    ids = {b["id"] for b in blocks}
    ifs = [i for i in repo.items(type_="IF") if i["attrs"].get("canvas") == canvas
           and i["attrs"].get("from") in ids and i["attrs"].get("to") in ids]
    return {"format": "ecualm-arch/1", "project": cfg["project"], "canvas": canvas, "exported_at": time.time(),
            "blocks": [{"id": b["id"], "title": b["title"], "text": b["text"], "domain": b["domain"], "status": b["status"],
                        "asil": b["attrs"].get("asil", "QM"), "hw": b["attrs"].get("hw"),
                        "layout": b["attrs"].get("canvas_layout")} for b in blocks],
            "interfaces": [{"id": i["id"], "name": i["title"], "from": i["attrs"]["from"], "to": i["attrs"]["to"],
                            "signal_class": i["attrs"].get("signal_class"), "signals": i["attrs"].get("signals", [])} for i in ifs]}


def import_arch(repo: Repo, cfg: dict, data: dict, user: str = "arch") -> dict:
    canvas = data.get("canvas", "HWE2")
    typ = _block_type(canvas)
    keymap: dict[str, str] = {}
    created, updated = [], []
    existing = repo.items(type_=typ)
    for b in data.get("blocks", []):
        key = b.get("key") or b.get("id") or b["title"]
        cur = repo.get(b["id"]) if b.get("id") and repo.get(b["id"]) and repo.get(b["id"])["type"] == typ else None
        cur = cur or next((e for e in existing if e["title"] == b["title"]), None)
        attrs = {"asil": b.get("asil", "QM")}
        if b.get("hw"):
            attrs["hw"] = b["hw"]
        lay = b.get("layout") or {}
        if cur is None:
            cur = create_block(repo, cfg, canvas, b["title"], b.get("text", ""), b.get("domain", "GEN"),
                               lay.get("x", 40), lay.get("y", 40), attrs, user=user)
            created.append(cur["id"])
        else:
            changed = {k: v for k, v in attrs.items() if cur["attrs"].get(k) != v}
            text = b.get("text") if b.get("text") and b.get("text") != cur["text"] else None
            if changed or text:
                ops.edit_item(repo, cfg, cur["id"], text=text, attrs=changed or None, user=user)
                updated.append(cur["id"])
            if lay:
                set_layout(repo, {cur["id"]: lay})
        keymap[key] = cur["id"]
        # trace hints: realise a system element, be controlled by a SW component
        for title in b.get("refines_title", []):
            el = next((i for i in repo.items(type_="SYS3") if i["title"] == title), None)
            if el and typ == "HWE2":
                repo.add_link(cur["id"], "refines", el["id"])
        for title in b.get("controlled_by_title", []):
            sw = next((i for i in repo.items(type_="SWE2") if i["title"] == title), None)
            if sw and typ == "HWE2":
                repo.add_link(sw["id"], "controls", cur["id"])
    ifs_now = [i for i in repo.items(type_="IF") if i["attrs"].get("canvas") == canvas]
    n_if = 0
    for f in data.get("interfaces", []):
        src, dst = keymap.get(f["from"], f["from"]), keymap.get(f["to"], f["to"])
        if not repo.get(src) or not repo.get(dst):
            continue
        same = next((i for i in ifs_now if i["attrs"].get("from") == src and i["attrs"].get("to") == dst and i["title"] == f["name"]), None)
        if same is None:
            it = create_interface(repo, cfg, canvas, src, dst, f["name"], f.get("signal_class", "digital"), f.get("signals"), user=user)
            keymap[f.get("key") or it["id"]] = it["id"]
            n_if += 1
        else:
            keymap[f.get("key") or same["id"]] = same["id"]
    n_tc = 0
    for t in data.get("tests", []):
        tc_type = t.get("type", "HWE3_TC")
        cur = next((i for i in repo.items(type_=tc_type) if i["title"] == t["title"]), None)
        if cur is None:
            cur = ops.create_item(repo, cfg, tc_type, t["text"], domain=t.get("domain"), title=t["title"],
                                  attrs={k: t[k] for k in ("kind", "tool", "pass_criteria", "expected", "pre_condition") if k in t},
                                  user=user)
            n_tc += 1
        keymap[t.get("key") or cur["id"]] = cur["id"]
        for v in t.get("verifies", []):
            tgt = keymap.get(v, v)
            if repo.get(tgt):
                repo.add_link(cur["id"], "verifies", tgt)
    repo.commit()
    res = {"canvas": canvas, "created": created, "updated": updated, "interfaces": n_if, "tests": n_tc, "results": 0}
    if data.get("results"):
        rows = [{**r, "tc": keymap.get(r["tc"], r["tc"])} for r in data["results"]]
        res["results"] = len(ingest_results(repo, cfg, {"results": rows}, user=user)["updated"])
    return res


def load_sample(repo: Repo, cfg: dict, user: str = "sample") -> dict:
    return import_arch(repo, cfg, json.loads(SAMPLE.read_text(encoding="utf-8")), user=user)
