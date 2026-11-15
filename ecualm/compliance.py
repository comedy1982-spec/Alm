"""Compliance matrix: the supplier's answer to every customer requirement (SYS.1).

One row per customer requirement with a status (Accept / Accept with Deviation / Not Accept / Clarification
Needed / Not Applicable), a comment, the deviation or alternative offered, an owner and the customer's reply.
The answers live on the requirement (attrs.compliance, .comment, .deviation, .compliance_owner,
.customer_response), so the SYS.1 table, the ReqIF reply and this matrix always show the same thing.
"""
from __future__ import annotations

import time
from pathlib import Path

STATUSES = [
    {"label": "Accept", "ko": "수용", "cls": "ok", "needs": "", "fill": "E3F4E8"},
    {"label": "Accept with Deviation", "ko": "편차 조건부 수용", "cls": "warn", "needs": "deviation", "fill": "FFF1D6"},
    {"label": "Not Accept", "ko": "수용 불가", "cls": "err", "needs": "comment", "fill": "FBE3E0"},
    {"label": "Clarification Needed", "ko": "확인 필요", "cls": "warn", "needs": "comment", "fill": "FFF7DB"},
    {"label": "Not Applicable", "ko": "해당 없음", "cls": "", "needs": "comment", "fill": "ECEFF3"},
]
LEGACY = {"C": "Accept", "PC": "Accept with Deviation", "NC": "Not Accept", "검토중": "Clarification Needed"}
FIELDS = {"status": "compliance", "comment": "comment", "deviation": "deviation", "owner": "compliance_owner",
          "customer_response": "customer_response"}
OPEN = "Open"


def statuses(cfg: dict) -> list[dict]:
    """Default list, or the project's own from alm.json: "compliance_statuses": ["Accept", {"label": ..., "needs": "comment"}]."""
    own = cfg.get("compliance_statuses")
    if not own:
        return STATUSES
    out = []
    for s in own:
        s = {"label": s} if isinstance(s, str) else dict(s)
        base = next((d for d in STATUSES if d["label"].lower() == s["label"].lower()), {"ko": "", "cls": "", "needs": "", "fill": "ECEFF3"})
        out.append({**base, **s})
    return out


def normalize(v: str) -> str:
    """Stored value -> status label (also the older 'C (준수)' style values)."""
    v = (v or "").strip()
    head = v.split(" ")[0].split("(")[0].upper()
    return LEGACY.get(head, LEGACY.get(v, v))


def _needs(st: dict | None, row: dict) -> str:
    need = (st or {}).get("needs", "")
    if need == "deviation" and not (row["deviation"] or "").strip():
        return "편차 내용을 적으세요"
    if need == "comment" and not (row["comment"] or "").strip():
        return "사유(코멘트)를 적으세요"
    return ""


def matrix(repo, cfg: dict, doc: str = "") -> dict:
    sts = statuses(cfg)
    by_label = {s["label"]: s for s in sts}
    types = set(next(s for s in cfg["stages"] if s["id"] == "SYS1")["types"])
    items = sorted((i for i in repo.items() if i["type"] in types), key=lambda i: (i["doc"], i["ord"]))
    docs = list(dict.fromkeys(i["doc"] or "(문서 없음)" for i in items))
    down: dict = {}
    for l in repo.links():
        if l["role"] != "refers" and l["state"] != "proposed":
            down.setdefault(l["dst"], []).append(l["src"])
    rows = []
    for i in items:
        if doc and (i["doc"] or "(문서 없음)") != doc:
            continue
        a = i["attrs"]
        f = a.get("fields") or {}
        r = {"id": i["id"], "native_id": a.get("native_id", ""), "doc": i["doc"], "section": i["section"], "text": i["text"],
             "asil": a.get("asil") or f.get("ASIL", ""), "status": normalize(a.get("compliance", "")),
             "comment": a.get("comment", ""), "deviation": a.get("deviation", ""), "owner": a.get("compliance_owner", ""),
             "customer_response": a.get("customer_response", ""), "by": a.get("compliance_by", ""),
             "at": a.get("compliance_at", ""), "trace": sorted(down.get(i["id"], []))}
        r["issue"] = _needs(by_label.get(r["status"]), r)
        rows.append(r)
    counts = {s["label"]: 0 for s in sts}
    counts[OPEN] = 0
    for r in rows:
        counts[r["status"] if r["status"] in counts else OPEN] += 1
    answered = len(rows) - counts[OPEN]
    revs = {d["doc"]: d["rev"] for d in repo.docs()}
    return {"statuses": sts, "docs": docs, "doc": doc, "rev": revs.get(doc, "") if doc else "", "rows": rows,
            "summary": {"total": len(rows), "answered": answered, "open": counts[OPEN], "counts": counts,
                        "rate": round(answered * 100 / len(rows), 1) if rows else 0.0,
                        "issues": sum(1 for r in rows if r["issue"])}}


def set_rows(repo, cfg: dict, ids: list[str], values: dict, user: str) -> dict:
    """Write status / comment / deviation / owner / customer_response on one or many requirements."""
    from . import ops
    labels = {s["label"] for s in statuses(cfg)}
    vals = {k: ("" if v is None else str(v)) for k, v in values.items() if k in FIELDS}
    if not vals:
        raise ValueError("바꿀 값이 없습니다")
    if "status" in vals:
        vals["status"] = "" if vals["status"] == OPEN else vals["status"]
        if vals["status"] and vals["status"] not in labels:
            raise ValueError(f"상태는 {', '.join(sorted(labels))} 중에서 고르세요")
    types = set(next(s for s in cfg["stages"] if s["id"] == "SYS1")["types"])
    n = 0
    for iid in ids:
        it = repo.get(iid)
        if not it or it["type"] not in types or it["status"] == "deleted":
            raise KeyError(f"고객 요구사항이 아닙니다: {iid}")
        a = it["attrs"]
        new = {FIELDS[k]: v for k, v in vals.items() if (normalize(a.get(FIELDS[k], "")) if k == "status" else a.get(FIELDS[k], "")) != v}
        if not new:
            continue
        if "compliance" in new:
            new.update(compliance_by=user, compliance_at=time.strftime("%Y-%m-%d"))
        ops.edit_item(repo, cfg, iid, attrs=new, user=user, suspect=False)     # an answer is not a change of the requirement
        n += 1
    return {"updated": n}


def export_xlsx(repo, cfg: dict, out: Path, doc: str = "") -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation
    m = matrix(repo, cfg, doc)
    s = m["summary"]
    wb = Workbook(); ws = wb.active; ws.title = "Compliance Matrix"
    ws["A1"] = "Compliance Matrix"; ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = (f"Project: {cfg.get('project', '')}   Document: {doc or ', '.join(m['docs'])}" + (f" rev {m['rev']}" if m["rev"] else "")
                + f"   Date: {time.strftime('%Y-%m-%d')}")
    ws["A3"] = (f"Requirements {s['total']} · Answered {s['answered']} ({s['rate']}%) · "
                + " · ".join(f"{k} {v}" for k, v in s["counts"].items() if v))
    cols = [("No", 6), ("Customer ID", 16), ("ALM ID", 16), ("Section", 26), ("Requirement", 62), ("ASIL", 7),
            ("Compliance Status", 24), ("Supplier Comment", 44), ("Deviation / Alternative", 44), ("Owner", 12),
            ("Customer Response", 36), ("Trace (SYS.2 …)", 24), ("Answered", 12)]
    thin = Side(style="thin", color="C9D1DB"); bd = Border(left=thin, right=thin, top=thin, bottom=thin)
    H = 5
    for j, (name, w) in enumerate(cols, 1):
        c = ws.cell(H, j, name)
        c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="1F5FBF")
        c.alignment = Alignment(wrap_text=True, vertical="center"); c.border = bd
        ws.column_dimensions[get_column_letter(j)].width = w
    fill = {x["label"]: PatternFill("solid", fgColor=x["fill"]) for x in m["statuses"]}
    for n, r in enumerate(m["rows"], 1):
        vals = [n, r["native_id"], r["id"], r["section"], r["text"], r["asil"], r["status"], r["comment"], r["deviation"],
                r["owner"], r["customer_response"], ", ".join(r["trace"]), r["at"]]
        for j, v in enumerate(vals, 1):
            c = ws.cell(H + n, j, v)
            c.alignment = Alignment(wrap_text=True, vertical="top"); c.border = bd
        if r["status"] in fill:
            ws.cell(H + n, 7).fill = fill[r["status"]]
    last = H + max(1, len(m["rows"]))
    dv = DataValidation(type="list", formula1='"' + ",".join(x["label"] for x in m["statuses"]) + '"', allow_blank=True)
    dv.error, dv.errorTitle = "목록에서 고르세요", "Compliance Status"
    ws.add_data_validation(dv); dv.add(f"G{H + 1}:G{last}")
    ws.freeze_panes = ws.cell(H + 1, 4)
    ws.auto_filter.ref = f"A{H}:{get_column_letter(len(cols))}{last}"
    ws.page_setup.orientation = "landscape"; ws.page_setup.fitToWidth = 1; ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{H}:{H}"

    w2 = wb.create_sheet("Summary")
    w2["A1"] = "Compliance Summary"; w2["A1"].font = Font(bold=True, size=13)
    w2.append([]); w2.append(["Status", "Count", "%"])
    for k, v in s["counts"].items():
        w2.append([k, v, round(v * 100 / s["total"], 1) if s["total"] else 0])
    w2.append(["Total", s["total"], 100 if s["total"] else 0])
    for c in w2[3]:
        c.font = Font(bold=True)
    w2.column_dimensions["A"].width = 28
    secs: dict = {}
    for r in m["rows"]:
        top = (r["section"] or "—").split(" > ")[0]
        secs.setdefault(top, {}).setdefault(r["status"] or OPEN, 0)
        secs[top][r["status"] or OPEN] += 1
    labels = [x["label"] for x in m["statuses"]] + [OPEN]
    w2.append([]); w2.append(["Chapter"] + labels)
    for c in w2[w2.max_row]:
        c.font = Font(bold=True)
    for k, v in secs.items():
        w2.append([k] + [v.get(x, 0) for x in labels])
    wb.save(out)
    return out
