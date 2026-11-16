"""Requirements traceability matrix (RTM).

chain   one row per item of a starting stage (default: customer requirements), one column per V-model stage; a
        cell lists everything of that stage that is reachable through trace links — downstream (derived, refined,
        allocated, verified by) and upstream. Shows where a requirement was not carried on and whether it is verified.
cross   the classic grid for two stages: rows x columns with a mark where two items are linked, directly or
        through intermediate items.
Both come from the same links the rest of the tool uses (refers / relates are not trace links).
"""
from __future__ import annotations

import time
from pathlib import Path

NOT_TRACE = {"refers", "relates"}
CONTENT = {"HDG", "INFO", "TBL", "FIG"}


def _graph(repo, cfg):
    items = {i["id"]: i for i in repo.items() if i["type"] not in CONTENT}
    stage_of = {t: s["id"] for s in cfg["stages"] for t in s["types"]}
    down, up = {}, {}
    for l in repo.links():
        if l["role"] in NOT_TRACE or l["src"] not in items or l["dst"] not in items or l.get("state") == "rejected":
            continue
        e = {"suspect": bool(l["suspect"]), "proposed": l.get("state") == "proposed", "role": l["role"]}
        down.setdefault(l["dst"], []).append((l["src"], e))
        up.setdefault(l["src"], []).append((l["dst"], e))
    return items, stage_of, down, up


def _reach(start: str, adj: dict) -> dict:
    """Everything reachable from start: {id: {dist, suspect, proposed}} (flags: any link on the way)."""
    seen = {start: {"dist": 0, "suspect": False, "proposed": False}}
    queue = [start]
    while queue:
        cur = queue.pop(0)
        for nxt, e in adj.get(cur, []):
            if nxt in seen:
                continue
            seen[nxt] = {"dist": seen[cur]["dist"] + 1, "suspect": seen[cur]["suspect"] or e["suspect"],
                         "proposed": seen[cur]["proposed"] or e["proposed"]}
            queue.append(nxt)
    del seen[start]
    return seen


def _result(it: dict) -> str:
    return ((it["attrs"].get("result") or {}).get("status") or "") if it["type"].endswith("_TC") else ""


def chain(repo, cfg: dict, root: str = "SYS1", doc: str = "", domain: str = "") -> dict:
    items, stage_of, down, up = _graph(repo, cfg)
    stages = {s["id"]: s for s in cfg["stages"]}
    if root not in stages:
        raise KeyError(f"단계 {root} 없음")
    rt = stages[root]
    all_roots = sorted((i for i in items.values() if i["type"] in rt["types"]), key=lambda i: (not i["doc"], i["doc"], i["ord"], i["id"]))
    roots = [i for i in all_roots if (not doc or i["doc"] == doc) and (not domain or i["domain"] == domain)]
    used = {stage_of.get(i["type"]) for i in items.values()}
    cols = [s for s in cfg["stages"] if s["id"] in used or s["id"] == root]
    required = [n for n in rt.get("next", []) if stages[n]["side"] == "spec"][:1] if root == "SYS1" else []
    verify_ids = {s["id"] for s in cfg["stages"] if s["side"] == "verify"}
    rows = []
    cover = {s["id"]: 0 for s in cols}
    kp = {"total": len(roots), "derived": 0, "tested": 0, "passed": 0, "failed": 0, "suspect": 0, "no_test": 0}
    for r in roots:
        dn, upw = _reach(r["id"], down), _reach(r["id"], up)
        cells: dict = {}
        for rid, f in list(dn.items()) + list(upw.items()):
            it = items[rid]
            sid = stage_of.get(it["type"])
            if sid is None or sid == root:
                continue
            cells.setdefault(sid, []).append({"id": rid, "status": it["status"], "suspect": f["suspect"], "proposed": f["proposed"],
                                              "direct": f["dist"] == 1, "result": _result(it), "up": rid in upw})
        for sid in cells:
            cells[sid].sort(key=lambda c: c["id"])
            if any(not c["proposed"] for c in cells[sid]):
                cover[sid] += 1
        cover[root] += 1
        tests = [c for sid in cells if sid in verify_ids for c in cells[sid] if not c["proposed"]]
        has_down = any(not f["proposed"] for f in dn.values())
        suspect = any(c["suspect"] for v in cells.values() for c in v)
        if any(t["result"] == "FAIL" for t in tests):
            verdict = "fail"
        elif tests and all(t["result"] == "PASS" for t in tests):
            verdict = "pass"
        elif tests:
            verdict = "tested"          # tests are linked, not all have a passing result yet
        elif has_down:
            verdict = "no_test"
        else:
            verdict = "open"            # nothing derived from it at all
        kp["derived"] += has_down
        kp["tested"] += bool(tests)
        kp["passed"] += verdict == "pass"
        kp["failed"] += verdict == "fail"
        kp["suspect"] += suspect
        kp["no_test"] += verdict in ("no_test", "open")
        rows.append({"id": r["id"], "native_id": r["attrs"].get("native_id", ""), "text": r["text"], "status": r["status"],
                     "doc": r["doc"], "domain": r["domain"], "section": r["section"], "asil": r["attrs"].get("asil", ""),
                     "cells": cells, "verdict": verdict, "suspect": suspect,
                     "missing": [s for s in required if not any(not c["proposed"] for c in cells.get(s, []))]})
    orphans = {}
    for s in cfg["stages"]:      # items that trace back to nothing (no upstream link), per stage
        if s["id"] == "SYS1":
            continue
        n = [i["id"] for i in items.values() if i["type"] in s["types"] and not any(not e["proposed"] for _, e in up.get(i["id"], []))
             and i["attrs"].get("origin") != "internal"]
        if n:
            orphans[s["id"]] = sorted(n)
    return {"root": root, "doc": doc, "domain": domain, "required": required,
            "columns": [{"id": s["id"], "aspice": s["aspice"], "name": s["name"], "side": s["side"],
                         "covered": cover[s["id"]], "pct": round(cover[s["id"]] * 100 / len(roots), 1) if roots else 0.0}
                        for s in cols],
            "rows": rows, "kpi": kp, "orphans": orphans,
            "docs": list(dict.fromkeys(i["doc"] for i in all_roots if i["doc"])),
            "domains": sorted({i["domain"] for i in all_roots}),
            "roots": [{"id": s["id"], "aspice": s["aspice"], "name": s["name"]} for s in cfg["stages"]
                      if s["side"] == "spec" and (s["id"] in used or s["id"] == "SYS1")]}


def cross(repo, cfg: dict, a: str, b: str, domain: str = "", limit: int = 400) -> dict:
    items, stage_of, down, up = _graph(repo, cfg)
    stages = {s["id"]: s for s in cfg["stages"]}
    if a not in stages or b not in stages:
        raise KeyError("단계 없음")
    pick = lambda sid: sorted((i for i in items.values() if i["type"] in stages[sid]["types"] and (not domain or i["domain"] == domain)),
                              key=lambda i: (not i["doc"], i["doc"], i["ord"], i["id"]))
    ra, cb = pick(a), pick(b)
    cut = len(ra) > limit or len(cb) > limit
    ra, cb = ra[:limit], cb[:limit]
    col_ids = {i["id"] for i in cb}
    cells, col_n = {}, {i["id"]: 0 for i in cb}
    for r in ra:
        reach = {**_reach(r["id"], down), **_reach(r["id"], up)}
        row = {}
        for cid in col_ids & set(reach):
            f = reach[cid]
            row[cid] = ("p" if f["proposed"] else "s" if f["suspect"] else "d" if f["dist"] == 1 else "t")
            if not f["proposed"]:
                col_n[cid] += 1
        if row:
            cells[r["id"]] = row
    brief = lambda i: {"id": i["id"], "native_id": i["attrs"].get("native_id", ""), "text": i["text"][:160], "domain": i["domain"]}
    n_links = sum(1 for r in cells.values() for v in r.values() if v != "p")
    return {"a": a, "b": b, "domain": domain, "rows": [brief(i) for i in ra], "cols": [brief(i) for i in cb], "cells": cells,
            "truncated": cut, "links": n_links,
            "rows_linked": sum(1 for r in ra if any(v != "p" for v in cells.get(r["id"], {}).values())),
            "cols_linked": sum(1 for c in cb if col_n[c["id"]]),
            "stages": [{"id": s["id"], "aspice": s["aspice"], "name": s["name"]} for s in cfg["stages"]
                       if any(i["type"] in s["types"] for i in items.values())]}


VERDICT = {"pass": "검증 완료 (PASS)", "fail": "시험 실패", "tested": "시험 연결됨 (결과 미완)", "no_test": "시험 미연결", "open": "전개 안 됨"}


def export_xlsx(repo, cfg: dict, out: Path, root: str = "SYS1", a: str = "", b: str = "", doc: str = "") -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    m = chain(repo, cfg, root, doc)
    wb = Workbook(); ws = wb.active; ws.title = "RTM"
    thin = Side(style="thin", color="C9D1DB"); bd = Border(left=thin, right=thin, top=thin, bottom=thin)
    head = PatternFill("solid", fgColor="1F5FBF"); miss = PatternFill("solid", fgColor="FBE3E0")
    vfill = {"pass": "E3F4E8", "fail": "FBE3E0", "tested": "FFF7DB", "no_test": "FFF1D6", "open": "FBE3E0"}
    k = m["kpi"]
    ws["A1"] = "Requirements Traceability Matrix"; ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"Project: {cfg.get('project', '')}   Start: {root}" + (f"   Document: {doc}" if doc else "") + f"   Date: {time.strftime('%Y-%m-%d')}"
    ws["A3"] = (f"{k['total']} requirements · derived {k['derived']} · test linked {k['tested']} · passed {k['passed']} · "
                f"failed {k['failed']} · suspect {k['suspect']}")
    others = [c for c in m["columns"] if c["id"] != root]
    heads = ["No", "ID", "Customer ID", "Requirement", "ASIL"] + [f"{c['aspice']} {c['name']}\n({c['pct']}%)" for c in others] + ["Verdict"]
    H = 5
    for j, h in enumerate(heads, 1):
        c = ws.cell(H, j, h); c.font = Font(bold=True, color="FFFFFF"); c.fill = head; c.border = bd
        c.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(j)].width = [6, 16, 15, 58, 7][j - 1] if j <= 5 else 22
    ws.row_dimensions[H].height = 44
    for n, r in enumerate(m["rows"], 1):
        vals = [n, r["id"], r["native_id"], r["text"], r["asil"]]
        for c in others:
            vals.append("\n".join(x["id"] + (" [" + x["result"] + "]" if x["result"] else "") + (" ⚠suspect" if x["suspect"] else "")
                                  + (" (제안)" if x["proposed"] else "") for x in r["cells"].get(c["id"], [])))
        vals.append(VERDICT[r["verdict"]])
        for j, v in enumerate(vals, 1):
            cell = ws.cell(H + n, j, v); cell.border = bd; cell.alignment = Alignment(wrap_text=True, vertical="top")
        for j, c in enumerate(others, 6):
            if c["id"] in r["missing"]:
                ws.cell(H + n, j).fill = miss
        ws.cell(H + n, len(heads)).fill = PatternFill("solid", fgColor=vfill[r["verdict"]])
    last = H + max(1, len(m["rows"]))
    ws.freeze_panes = ws.cell(H + 1, 5)
    ws.auto_filter.ref = f"A{H}:{get_column_letter(len(heads))}{last}"
    ws.page_setup.orientation = "landscape"; ws.page_setup.fitToWidth = 1; ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True; ws.print_title_rows = f"{H}:{H}"

    w2 = wb.create_sheet("Coverage")
    w2.append(["Stage", "Covered", "Total", "%"])
    for c in m["columns"]:
        w2.append([f"{c['aspice']} {c['name']}", c["covered"], k["total"], c["pct"]])
    w2.append([]); w2.append(["Verdict", "Count"])
    cnt = {}
    for r in m["rows"]:
        cnt[r["verdict"]] = cnt.get(r["verdict"], 0) + 1
    for key, lab in VERDICT.items():
        w2.append([lab, cnt.get(key, 0)])
    w2.append([]); w2.append(["Items without an upstream link (orphans)", "Count", "IDs"])
    for sid, ids in m["orphans"].items():
        w2.append([sid, len(ids), ", ".join(ids[:60]) + (" …" if len(ids) > 60 else "")])
    for row in (1, len(m["columns"]) + 3, len(m["columns"]) + len(VERDICT) + 5):
        for c in w2[row]:
            c.font = Font(bold=True)
    w2.column_dimensions["A"].width = 44; w2.column_dimensions["C"].width = 60

    used = [c["id"] for c in m["columns"] if c["id"] != root and c["covered"]]
    a, b = a or root, b or (used[0] if used else "")
    if b:
        x = cross(repo, cfg, a, b, limit=250)
        w3 = wb.create_sheet("Matrix")
        w3["A1"] = f"{a} × {b}   ● direct   ○ via other items   ▲ suspect   ◌ proposed"
        w3["A1"].font = Font(bold=True)
        mark = {"d": "●", "t": "○", "s": "▲", "p": "◌"}
        for j, c in enumerate(x["cols"], 3):
            cell = w3.cell(2, j, c["id"]); cell.alignment = Alignment(text_rotation=90, vertical="bottom", horizontal="center")
            cell.font = Font(bold=True, size=9); cell.border = bd
            w3.column_dimensions[get_column_letter(j)].width = 3.6
        w3.row_dimensions[2].height = 96
        w3.column_dimensions["A"].width = 18; w3.column_dimensions["B"].width = 46
        for i, r in enumerate(x["rows"], 3):
            w3.cell(i, 1, r["id"]).font = Font(bold=True, size=9)
            w3.cell(i, 2, r["text"][:90]).font = Font(size=9)
            row = x["cells"].get(r["id"], {})
            if not any(v != "p" for v in row.values()):
                w3.cell(i, 1).fill = miss
            for j, c in enumerate(x["cols"], 3):
                cell = w3.cell(i, j, mark.get(row.get(c["id"], ""), "")); cell.border = bd
                cell.alignment = Alignment(horizontal="center")
        w3.freeze_panes = "C3"
    wb.save(out)
    return out
