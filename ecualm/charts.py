"""Native Office charts (DrawingML <c:chartSpace>) embedded in DOCX: read the data and draw a simple SVG.

Word keeps no picture of a chart, only its data, so without this a chart in a customer spec would vanish on
import. The data (series, categories, values, axis titles) is kept on the figure item, so a later revision
whose curve moved is detected as a change, and the drawing is an SVG made here (no plotting library needed).
"""
from __future__ import annotations

import math
import re
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
KINDS = {"barChart": "bar", "bar3DChart": "bar", "lineChart": "line", "line3DChart": "line", "areaChart": "area",
         "area3DChart": "area", "pieChart": "pie", "pie3DChart": "pie", "doughnutChart": "pie", "scatterChart": "scatter",
         "radarChart": "line", "stockChart": "line", "bubbleChart": "scatter"}
LABEL = {"bar": "막대", "line": "선", "area": "영역", "pie": "원형", "scatter": "분산형"}
PALETTE = ["#2F6FB2", "#D9822B", "#3A9A5B", "#B4466A", "#7A5BB5", "#5E8C99", "#A68A2D", "#6B7280"]


def _q(ns, t):
    return f"{{{ns}}}{t}"


def _text(el) -> str:
    return "".join(t.text or "" for t in el.iter(_q(A, "t"))).strip() if el is not None else ""


def _cache(ref) -> list:
    """Values of a c:cat / c:val / c:tx (strRef/numRef caches or literal lists), in point order."""
    if ref is None:
        return []
    pts = {}
    n = 0
    for cache in list(ref.iter(_q(C, "strCache"))) + list(ref.iter(_q(C, "numCache"))) + \
            list(ref.iter(_q(C, "strLit"))) + list(ref.iter(_q(C, "numLit"))):
        pc = cache.find(_q(C, "ptCount"))
        n = max(n, int(pc.get("val", "0")) if pc is not None else 0)
        for pt in cache.findall(_q(C, "pt")):
            v = pt.find(_q(C, "v"))
            pts[int(pt.get("idx", "0"))] = v.text if v is not None else ""
        if pts:
            break
    n = max(n, max(pts) + 1 if pts else 0)
    return [pts.get(i, "") for i in range(n)]


def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def parse_chart(xml: bytes) -> dict | None:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None
    chart = root.find(_q(C, "chart"))
    if chart is None:
        return None
    title = _text(chart.find(_q(C, "title")))
    plot = chart.find(_q(C, "plotArea"))
    if plot is None:
        return None
    kind, series, cats = "", [], []
    for el in plot:
        tag = el.tag.rsplit("}", 1)[-1]
        if tag not in KINDS:
            continue
        kind = kind or KINDS[tag]
        bd = el.find(_q(C, "barDir"))
        horizontal = bd is not None and bd.get("val") == "bar"
        for ser in el.findall(_q(C, "ser")):
            txe = ser.find(_q(C, "tx"))
            direct = txe.find(_q(C, "v")) if txe is not None else None
            name = (direct.text if direct is not None else "") or (_cache(txe) or [""])[0] or _text(txe)
            if KINDS[tag] == "scatter":
                xs, ys = _cache(ser.find(_q(C, "xVal"))), _cache(ser.find(_q(C, "yVal")))
                series.append({"name": name or f"계열 {len(series) + 1}", "x": [_num(v) for v in xs],
                               "values": [_num(v) for v in ys], "kind": "scatter"})
            else:
                c = _cache(ser.find(_q(C, "cat")))
                if c and not cats:
                    cats = c
                series.append({"name": name or f"계열 {len(series) + 1}", "values": [_num(v) for v in _cache(ser.find(_q(C, "val")))],
                               "kind": KINDS[tag]})
        if horizontal:
            kind = "barh"
    if not series:
        return None
    axes = []
    for ax in list(plot.findall(_q(C, "catAx"))) + list(plot.findall(_q(C, "valAx"))) + list(plot.findall(_q(C, "dateAx"))):
        t = _text(ax.find(_q(C, "title")))
        axes.append(t)
    return {"kind": kind or "bar", "title": title, "categories": cats, "series": series,
            "x_title": axes[0] if axes else "", "y_title": axes[1] if len(axes) > 1 else ""}


def data_text(ch: dict) -> str:
    """Plain-text data table (what the change analysis compares between revisions)."""
    lines = [f"[{LABEL.get(ch['kind'].rstrip('h'), ch['kind'])} 차트] {ch.get('title', '')}".strip()]
    if ch.get("x_title") or ch.get("y_title"):
        lines.append(f"X: {ch.get('x_title', '')} / Y: {ch.get('y_title', '')}")
    fmt = lambda v: "" if v is None else (f"{v:g}")
    for s in ch["series"]:
        if s.get("x"):
            pts = ", ".join(f"({fmt(x)}, {fmt(y)})" for x, y in zip(s["x"], s["values"]))
        else:
            cats = ch.get("categories") or [str(i + 1) for i in range(len(s["values"]))]
            pts = ", ".join(f"{c}={fmt(v)}" for c, v in zip(cats, s["values"]))
        lines.append(f"{s['name']}: {pts}")
    return "\n".join(lines)


def grid(ch: dict) -> list:
    """Data as a table grid (rows of cells) for the item view / export."""
    cell = lambda t: {"t": str(t), "rs": 1, "cs": 1}
    fmt = lambda v: "" if v is None else f"{v:g}"
    if any(s.get("x") for s in ch["series"]):
        rows = [[cell("계열"), cell(ch.get("x_title") or "X"), cell(ch.get("y_title") or "Y")]]
        for s in ch["series"]:
            for x, y in zip(s.get("x") or [], s["values"]):
                rows.append([cell(s["name"]), cell(fmt(x)), cell(fmt(y))])
        return rows
    cats = ch.get("categories") or [str(i + 1) for i in range(max(len(s["values"]) for s in ch["series"]))]
    rows = [[cell(ch.get("x_title") or "항목")] + [cell(s["name"]) for s in ch["series"]]]
    for i, c in enumerate(cats):
        rows.append([cell(c)] + [cell(fmt(s["values"][i]) if i < len(s["values"]) else "") for s in ch["series"]])
    return rows


def _nice(lo, hi):
    if lo == hi:
        hi = lo + 1
    span = hi - lo
    step = 10 ** math.floor(math.log10(span / 5))
    for m in (1, 2, 2.5, 5, 10):
        if span / (step * m) <= 6:
            step *= m
            break
    return math.floor(lo / step) * step, math.ceil(hi / step) * step, step


def svg(ch: dict, w: int = 640, h: int = 360) -> bytes:
    """A light-background SVG of the chart (bar / horizontal bar / line / area / scatter / pie)."""
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
           f'font-family="Segoe UI, Malgun Gothic, Apple SD Gothic Neo, sans-serif" font-size="12">',
           f'<rect width="{w}" height="{h}" fill="#FFFFFF"/>']
    t = escape(ch.get("title") or "")
    top = 34 if t else 14
    if t:
        out.append(f'<text x="{w / 2}" y="22" text-anchor="middle" font-size="14" font-weight="600" fill="#1F2937">{t}</text>')
    series = ch["series"]
    legend_h = 22 if len(series) > 1 or ch["kind"] == "pie" else 0
    kind = ch["kind"]
    if kind == "pie":
        s = series[0]
        vals = [max(0.0, v or 0.0) for v in s["values"]]
        tot = sum(vals) or 1.0
        cx, cy, r = w * 0.36, (top + h - 10) / 2, min(w * 0.3, (h - top - 20) / 2)
        a0 = -math.pi / 2
        cats = ch.get("categories") or [str(i + 1) for i in range(len(vals))]
        for i, v in enumerate(vals):
            a1 = a0 + 2 * math.pi * v / tot
            large = 1 if a1 - a0 > math.pi else 0
            x0, y0, x1, y1 = cx + r * math.cos(a0), cy + r * math.sin(a0), cx + r * math.cos(a1), cy + r * math.sin(a1)
            col = PALETTE[i % len(PALETTE)]
            if v >= tot:
                out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{col}"/>')
            elif v > 0:
                out.append(f'<path d="M{cx:.1f},{cy:.1f} L{x0:.1f},{y0:.1f} A{r:.1f},{r:.1f} 0 {large} 1 {x1:.1f},{y1:.1f} Z" '
                           f'fill="{col}" stroke="#FFFFFF" stroke-width="1.5"/>')
            ly = top + 10 + i * 20
            out.append(f'<rect x="{w * 0.7:.0f}" y="{ly - 9}" width="11" height="11" rx="2" fill="{col}"/>'
                       f'<text x="{w * 0.7 + 17:.0f}" y="{ly}" fill="#374151">{escape(str(cats[i] if i < len(cats) else i + 1))} '
                       f'({v / tot * 100:.0f}%)</text>')
            a0 = a1
        out.append("</svg>")
        return "".join(out).encode("utf-8")

    L, R, B = 64, 30, 46 + legend_h
    pw, ph = w - L - R, h - top - B
    allv = [v for s in series for v in s["values"] if v is not None]
    scatter = any(s.get("x") for s in series)
    lo, hi = min(allv + [0.0]) if kind in ("bar", "barh", "area") else min(allv or [0.0]), max(allv or [1.0])
    lo, hi, step = _nice(lo, hi)
    cats = ch.get("categories") or [str(i + 1) for i in range(max(len(s["values"]) for s in series))]
    n = max(1, len(cats))
    if kind == "barh":     # categories down the side, values across
        fx = lambda v: L + (v - lo) / (hi - lo) * pw
        v = lo
        while v <= hi + step / 2:
            out.append(f'<line x1="{fx(v):.1f}" y1="{top}" x2="{fx(v):.1f}" y2="{top + ph}" stroke="#E5E7EB"/>'
                       f'<text x="{fx(v):.1f}" y="{top + ph + 16}" text-anchor="middle" fill="#6B7280">{v:g}</text>')
            v += step
        band = ph / n
        bh = band * 0.7 / len(series)
        for i, c in enumerate(cats):
            out.append(f'<text x="{L - 6}" y="{top + band * i + band / 2 + 4:.1f}" text-anchor="end" fill="#374151">{escape(str(c))[:14]}</text>')
            for k, s in enumerate(series):
                val = s["values"][i] if i < len(s["values"]) else None
                if val is None:
                    continue
                y = top + band * i + band * 0.15 + k * bh
                x0, x1 = fx(max(lo, 0)), fx(val)
                out.append(f'<rect x="{min(x0, x1):.1f}" y="{y:.1f}" width="{abs(x1 - x0):.1f}" height="{bh:.1f}" fill="{PALETTE[k % 8]}"/>')
    else:
        fy = lambda v: top + ph - (v - lo) / (hi - lo) * ph
        v = lo
        while v <= hi + step / 2:
            out.append(f'<line x1="{L}" y1="{fy(v):.1f}" x2="{L + pw}" y2="{fy(v):.1f}" stroke="#E5E7EB"/>'
                       f'<text x="{L - 6}" y="{fy(v) + 4:.1f}" text-anchor="end" fill="#6B7280">{v:g}</text>')
            v += step
        if scatter:
            xs = [x for s in series for x in (s.get("x") or []) if x is not None] or [0.0, 1.0]
            xlo, xhi, xstep = _nice(min(xs), max(xs))
            fx = lambda x: L + (x - xlo) / (xhi - xlo) * pw
            x = xlo
            while x <= xhi + xstep / 2:
                out.append(f'<text x="{fx(x):.1f}" y="{top + ph + 16}" text-anchor="middle" fill="#6B7280">{x:g}</text>')
                x += xstep
        else:
            band = pw / n
            fx = lambda i: L + band * i + band / 2
            every = max(1, math.ceil(n / 12))
            for i, c in enumerate(cats):
                if i % every == 0:
                    out.append(f'<text x="{fx(i):.1f}" y="{top + ph + 16}" text-anchor="middle" fill="#6B7280">{escape(str(c))[:10]}</text>')
        out.append(f'<line x1="{L}" y1="{top + ph}" x2="{L + pw}" y2="{top + ph}" stroke="#9CA3AF"/>')
        bars = [s for s in series if s["kind"] == "bar" and kind != "scatter"]
        for k, s in enumerate(series):
            col = PALETTE[k % 8]
            if s in bars:
                bw = (pw / n) * 0.7 / len(bars)
                j = bars.index(s)
                for i, val in enumerate(s["values"]):
                    if val is None:
                        continue
                    x = L + (pw / n) * i + (pw / n) * 0.15 + j * bw
                    y0, y1 = fy(max(lo, 0)), fy(val)
                    out.append(f'<rect x="{x:.1f}" y="{min(y0, y1):.1f}" width="{bw:.1f}" height="{abs(y1 - y0):.1f}" fill="{col}"/>')
                continue
            if s.get("x"):
                pts = [(fx(x), fy(y)) for x, y in zip(s["x"], s["values"]) if x is not None and y is not None]
            else:
                pts = [(fx(i), fy(v)) for i, v in enumerate(s["values"]) if v is not None]
            if not pts:
                continue
            path = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
            if s["kind"] == "area":
                out.append(f'<polygon points="{pts[0][0]:.1f},{fy(max(lo, 0)):.1f} {path} {pts[-1][0]:.1f},{fy(max(lo, 0)):.1f}" '
                           f'fill="{col}" fill-opacity="0.25" stroke="{col}" stroke-width="2"/>')
            elif s["kind"] == "scatter" and not re.search(r"line", s.get("style", "")):
                out.extend(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{col}"/>' for x, y in pts)
                if len(pts) > 1:
                    out.append(f'<polyline points="{path}" fill="none" stroke="{col}" stroke-width="1.5" stroke-opacity="0.6"/>')
            else:
                out.append(f'<polyline points="{path}" fill="none" stroke="{col}" stroke-width="2"/>')
                out.extend(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{col}"/>' for x, y in pts)
    if ch.get("y_title"):
        out.append(f'<text transform="translate(14 {top + ph / 2:.0f}) rotate(-90)" text-anchor="middle" fill="#374151">{escape(ch["y_title"])}</text>')
    if ch.get("x_title"):
        out.append(f'<text x="{L + pw / 2:.0f}" y="{top + ph + 34}" text-anchor="middle" fill="#374151">{escape(ch["x_title"])}</text>')
    if legend_h:
        x = L
        for k, s in enumerate(series):
            out.append(f'<rect x="{x}" y="{h - 16}" width="11" height="11" rx="2" fill="{PALETTE[k % 8]}"/>'
                       f'<text x="{x + 16}" y="{h - 6}" fill="#374151">{escape(s["name"])}</text>')
            x += 28 + sum(12 if ord(ch_) > 0x2000 else 7 for ch_ in s["name"])
    out.append("</svg>")
    return "".join(out).encode("utf-8")
