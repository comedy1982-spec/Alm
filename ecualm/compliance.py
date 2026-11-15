"""Compliance matrix: the supplier's answer to every customer requirement (SYS.1).

One row per customer requirement with a status (Accept / Accept with Deviation / Not Accept / Clarification
Needed / Not Applicable), a comment, the deviation or alternative offered, an owner and the customer's reply.
The answers live on the requirement (attrs.compliance, .comment, .deviation, .compliance_owner,
.customer_response), so the SYS.1 table, the ReqIF reply and this matrix always show the same thing.
"""
from __future__ import annotations

import time
from pathlib import Path

# color: [light, dark] — fixed per status (validated as a set for colour-vision separation in this order)
STATUSES = [
    {"label": "Accept", "ko": "수용", "needs": "", "final": True, "color": ["#008300", "#0ca30c"]},
    {"label": "Accept with Comment", "ko": "코멘트 조건 수용", "needs": "comment", "final": True, "color": ["#2a78d6", "#3987e5"]},
    {"label": "Accept with Deviation", "ko": "편차 조건 수용", "needs": "deviation", "final": True, "color": ["#eb6834", "#d95926"]},
    {"label": "Partially Accept", "ko": "부분 수용", "needs": "comment", "final": True, "color": ["#6250d6", "#9085e9"]},
    {"label": "Not Accept", "ko": "수용 불가", "needs": "comment", "final": True, "color": ["#e34948", "#e66767"]},
    {"label": "Clarification Needed", "ko": "확인 필요 (고객 질의)", "needs": "comment", "final": False, "color": ["#1baf7a", "#199e70"]},
    {"label": "Under Review", "ko": "내부 검토 중", "needs": "", "final": False, "color": ["#eda100", "#c98500"]},
    {"label": "Noted", "ko": "참고 (정보성 문장)", "needs": "", "final": True, "color": ["#e87ba4", "#d55181"]},
    {"label": "Not Applicable", "ko": "해당 없음", "needs": "comment", "final": True, "color": ["#898781", "#898781"]},
]
OPEN_COLOR = ["#c3c2b7", "#52514e"]
LEGACY = {"C": "Accept", "PC": "Partially Accept", "NC": "Not Accept", "검토중": "Under Review"}
FIELDS = {"status": "compliance", "comment": "comment", "deviation": "deviation", "owner": "compliance_owner",
          "customer_response": "customer_response"}
OPEN = "Open"


SCHEMA = """CREATE TABLE IF NOT EXISTS compliance_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, user TEXT NOT NULL, item TEXT NOT NULL,
  field TEXT NOT NULL, old TEXT, new TEXT, via TEXT DEFAULT '');
CREATE INDEX IF NOT EXISTS compliance_log_item ON compliance_log(item);"""
_ready: set = set()


def init(repo) -> None:
    key = str(repo.dir)
    if key not in _ready:
        repo.con.executescript(SCHEMA)
        repo.con.commit()
        _ready.add(key)


def version(repo) -> int:
    """Grows with every saved answer: clients poll it to pick up other people's edits."""
    init(repo)
    return repo.con.execute("SELECT coalesce(max(id), 0) FROM compliance_log").fetchone()[0]


def history(repo, item: str = "", limit: int = 300) -> list[dict]:
    """Who changed which answer, when, from what to what — newest first."""
    init(repo)
    q, args = "SELECT id, at, user, item, field, old, new, via FROM compliance_log", []
    if item:
        q += " WHERE item=?"; args.append(item)
    rows = repo.con.execute(q + " ORDER BY id DESC LIMIT ?", args + [max(1, min(int(limit), 2000))]).fetchall()
    return [dict(zip(("id", "at", "user", "item", "field", "old", "new", "via"), r)) for r in rows]


def statuses(cfg: dict) -> list[dict]:
    """Default list, or the project's own from alm.json: "compliance_statuses": ["Accept", {"label": ..., "needs": "comment"}]."""
    own = cfg.get("compliance_statuses")
    if not own:
        return STATUSES
    out = []
    for s in own:
        s = {"label": s} if isinstance(s, str) else dict(s)
        base = next((d for d in STATUSES if d["label"].lower() == s["label"].lower()),
                    {"ko": "", "needs": "", "final": True, "color": ["#898781", "#898781"]})
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
             "customer_response": a.get("customer_response", ""), "meta": dict(a.get("compliance_meta") or {}),
             "trace": sorted(down.get(i["id"], []))}
        r["meta"].setdefault("status", {"by": a.get("compliance_by", ""), "at": a.get("compliance_at", "")})
        r["by"], r["at"] = r["meta"]["status"]["by"], r["meta"]["status"]["at"]
        r["issue"] = _needs(by_label.get(r["status"]), r)
        rows.append(r)
    counts = {s["label"]: 0 for s in sts}
    counts[OPEN] = 0
    for r in rows:
        counts[r["status"] if r["status"] in counts else OPEN] += 1
    answered = len(rows) - counts[OPEN]
    final = sum(counts[x["label"]] for x in sts if x.get("final", True))
    chapters: dict = {}
    for r in rows:
        ch = chapters.setdefault((r["section"] or "—").split(" > ")[0], {})
        k = r["status"] if r["status"] in by_label else OPEN
        ch[k] = ch.get(k, 0) + 1
    revs = {d["doc"]: d["rev"] for d in repo.docs()}
    return {"version": version(repo), "statuses": sts, "docs": docs, "doc": doc, "rev": revs.get(doc, "") if doc else "", "rows": rows,
            "open_color": OPEN_COLOR, "chapters": [{"name": k, "counts": v, "total": sum(v.values())} for k, v in chapters.items()],
            "summary": {"total": len(rows), "answered": answered, "final": final, "open": counts[OPEN], "counts": counts,
                        "rate": round(answered * 100 / len(rows), 1) if rows else 0.0,
                        "issues": sum(1 for r in rows if r["issue"])}}


def set_rows(repo, cfg: dict, ids: list[str], values: dict, user: str, via: str = "") -> dict:
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
    init(repo)
    n = 0
    for iid in ids:
        it = repo.get(iid)
        if not it or it["type"] not in types or it["status"] == "deleted":
            raise KeyError(f"고객 요구사항이 아닙니다: {iid}")
        a = it["attrs"]
        new = {FIELDS[k]: v for k, v in vals.items() if (normalize(a.get(FIELDS[k], "")) if k == "status" else a.get(FIELDS[k], "")) != v}
        if not new:
            continue
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        meta = dict(a.get("compliance_meta") or {})
        inv = {v: k for k, v in FIELDS.items()}
        for attr, val in list(new.items()):       # every field keeps who wrote it and when; every change is logged
            k = inv[attr]
            meta[k] = {"by": user, "at": now}
            old = normalize(a.get(attr, "")) if k == "status" else (a.get(attr, "") or "")
            repo.con.execute("INSERT INTO compliance_log(at, user, item, field, old, new, via) VALUES(?,?,?,?,?,?,?)",
                             (now, user, iid, k, old, val, via))
        new["compliance_meta"] = meta
        if "compliance" in new:
            new.update(compliance_by=user, compliance_at=now)
        ops.edit_item(repo, cfg, iid, attrs=new, user=user, suspect=False)     # an answer is not a change of the requirement
        n += 1
    repo.con.commit()
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
            ("Customer Response", 36), ("Trace (SYS.2 …)", 24), ("Status by", 10), ("Status at", 17),
            ("Comment by", 10), ("Comment at", 17)]
    thin = Side(style="thin", color="C9D1DB"); bd = Border(left=thin, right=thin, top=thin, bottom=thin)
    H = 5
    for j, (name, w) in enumerate(cols, 1):
        c = ws.cell(H, j, name)
        c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="1F5FBF")
        c.alignment = Alignment(wrap_text=True, vertical="center"); c.border = bd
        ws.column_dimensions[get_column_letter(j)].width = w
    def tint(hexc: str) -> str:      # status colour mixed 80% toward white: readable behind black text
        r, g, b = (int(hexc[i:i + 2], 16) for i in (1, 3, 5))
        return "".join("%02X" % round(c + (255 - c) * 0.8) for c in (r, g, b))
    fill = {x["label"]: PatternFill("solid", fgColor=tint(x["color"][0])) for x in m["statuses"]}
    for n, r in enumerate(m["rows"], 1):
        vals = [n, r["native_id"], r["id"], r["section"], r["text"], r["asil"], r["status"], r["comment"], r["deviation"],
                r["owner"], r["customer_response"], ", ".join(r["trace"]), r["by"], r["at"],
                (r["meta"].get("comment") or {}).get("by", ""), (r["meta"].get("comment") or {}).get("at", "")]
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
    # charts: share of each status (pie), count per status (bar), status per chapter (stacked bar)
    from openpyxl.chart import BarChart, PieChart, Reference
    from openpyxl.chart.label import DataLabelList
    from openpyxl.chart.series import DataPoint
    n_st = len(s["counts"])
    from openpyxl.utils import get_column_letter as _col
    anchor, anchor2 = _col(len(labels) + 3), _col(len(labels) + 11)      # right of the chapter table
    w2.page_setup.orientation = "landscape"
    colors = {x["label"]: x["color"][0][1:].upper() for x in m["statuses"]}
    colors[OPEN] = OPEN_COLOR[0][1:].upper()
    cats = Reference(w2, min_col=1, min_row=4, max_row=3 + n_st)
    vals = Reference(w2, min_col=2, min_row=3, max_row=3 + n_st)
    pie = PieChart(); pie.title = "Compliance Status"; pie.add_data(vals, titles_from_data=True); pie.set_categories(cats)
    pie.dataLabels = DataLabelList(); pie.dataLabels.showPercent = True; pie.dataLabels.showVal = False
    pie.dataLabels.showSerName = False; pie.dataLabels.showCatName = False; pie.dataLabels.showLeaderLines = False
    for k, lab in enumerate(s["counts"]):
        pt = DataPoint(idx=k); pt.graphicalProperties.solidFill = colors.get(lab, "898781"); pie.series[0].dPt.append(pt)
    pie.height, pie.width = 9, 13
    w2.add_chart(pie, f"{anchor}2")
    bar = BarChart(); bar.type = "bar"; bar.title = "Requirements per status"; bar.add_data(vals, titles_from_data=True)
    bar.set_categories(cats); bar.legend = None; bar.y_axis.title = "Requirements"
    bar.dataLabels = DataLabelList(); bar.dataLabels.showVal = True
    for name in ("showSerName", "showCatName", "showLegendKey", "showPercent"):
        setattr(bar.dataLabels, name, False)
    for k, lab in enumerate(s["counts"]):
        pt = DataPoint(idx=k); pt.graphicalProperties.solidFill = colors.get(lab, "898781"); bar.series[0].dPt.append(pt)
    bar.y_axis.delete = False; bar.x_axis.delete = False; bar.x_axis.scaling.orientation = "maxMin"
    bar.height, bar.width = 9, 13
    w2.add_chart(bar, f"{anchor2}2")
    if secs:
        h0 = 3 + n_st + 3                      # header row of the chapter table
        st = BarChart(); st.type = "bar"; st.grouping = "stacked"; st.overlap = 100; st.title = "Status per chapter"
        st.add_data(Reference(w2, min_col=2, max_col=1 + len(labels), min_row=h0, max_row=h0 + len(secs)), titles_from_data=True)
        st.set_categories(Reference(w2, min_col=1, min_row=h0 + 1, max_row=h0 + len(secs)))
        for ser, lab in zip(st.series, labels):
            ser.graphicalProperties.solidFill = colors.get(lab, "898781")
        st.y_axis.delete = False; st.x_axis.delete = False; st.x_axis.scaling.orientation = "maxMin"
        st.height, st.width = max(8, 0.55 * len(secs) + 3), 26.5
        w2.add_chart(st, f"{anchor}21")
    wb.save(out)
    return out


# ---------------------------------------------------------------- Excel -> matrix
HEADERS = {"id": ("alm id", "almid", "id"), "native_id": ("customer id", "고객 id", "원문 id", "req id"),
           "status": ("compliance status", "status", "상태", "준수 여부"),
           "comment": ("supplier comment", "comment", "코멘트", "공급사 의견"),
           "deviation": ("deviation / alternative", "deviation", "편차", "편차 · 대안"),
           "owner": ("owner", "담당"), "customer_response": ("customer response", "고객 회신")}
FIELD_LABEL = {"status": "Compliance Status", "comment": "코멘트", "deviation": "편차·대안", "owner": "담당",
               "customer_response": "고객 회신"}


def import_xlsx(repo, cfg: dict, path: Path, user: str, apply: bool = False) -> dict:
    """Read an edited matrix workbook back. Rows are found by ALM ID (or Customer ID); only the answer columns are
    taken (status, comment, deviation, owner, customer response) — requirement text in the file is ignored.
    apply=False only reports what would change."""
    from openpyxl import load_workbook
    try:
        wb = load_workbook(path, read_only=True, data_only=True)
    except Exception as e:
        raise ValueError(f"Excel 파일을 읽을 수 없습니다 ({e})")
    ws = wb["Compliance Matrix"] if "Compliance Matrix" in wb.sheetnames else wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    norm = lambda v: " ".join(str(v or "").replace("\n", " ").split()).lower()
    col, head = {}, -1
    for ri, r in enumerate(rows[:30]):
        cells = [norm(c) for c in r]
        found = {}
        for key, names in HEADERS.items():
            for j, c in enumerate(cells):
                if c in names and key not in found and j not in found.values():
                    found[key] = j
                    break
        if "status" in found and ("id" in found or "native_id" in found):
            col, head = found, ri
            break
    if head < 0:
        raise ValueError("머리글 행을 찾지 못했습니다 — 'ALM ID'(또는 'Customer ID')와 'Compliance Status' 열이 있어야 합니다")
    sts = statuses(cfg)
    label_of = {s["label"].lower(): s["label"] for s in sts}
    types = set(next(s for s in cfg["stages"] if s["id"] == "SYS1")["types"])
    items = {i["id"]: i for i in repo.items() if i["type"] in types}
    by_native = {}
    for i in items.values():
        if i["attrs"].get("native_id"):
            by_native.setdefault(i["attrs"]["native_id"], i["id"])
    out = {"file": Path(path).name, "rows": 0, "changes": [], "unknown": [], "invalid": [], "applied": 0,
           "columns": [FIELD_LABEL[k] for k in FIELD_LABEL if k in col]}
    todo: dict = {}
    cell = lambda r, k: ("" if k not in col or col[k] >= len(r) or r[col[k]] is None else str(r[col[k]]).strip())
    for ri, r in enumerate(rows[head + 1:], head + 2):
        iid, nid = cell(r, "id"), cell(r, "native_id")
        if not iid and not nid:
            continue
        out["rows"] += 1
        iid = iid if iid in items else by_native.get(nid, "")
        if not iid:
            out["unknown"].append({"row": ri, "id": cell(r, "id") or nid})
            continue
        if iid in todo:
            continue
        a = items[iid]["attrs"]
        vals = {}
        for k in FIELD_LABEL:
            if k not in col:
                continue
            new = cell(r, k)
            if k == "status":
                if new.lower() == OPEN.lower():
                    new = ""
                elif new:
                    lab = label_of.get(new.lower()) or (normalize(new) if normalize(new) in label_of.values() else None)
                    if not lab:
                        out["invalid"].append({"row": ri, "id": iid, "value": new})
                        continue
                    new = lab
                old = normalize(a.get("compliance", ""))
            else:
                old = a.get(FIELDS[k], "") or ""
            if new != old:
                vals[k] = new
                out["changes"].append({"id": iid, "native_id": a.get("native_id", ""), "field": k, "label": FIELD_LABEL[k],
                                       "old": old, "new": new})
        if vals:
            todo[iid] = vals
    out["items"] = len(todo)
    if apply:
        for iid, vals in todo.items():
            out["applied"] += set_rows(repo, cfg, [iid], vals, user, via=f"Excel: {Path(path).name}")["updated"]
    return out
