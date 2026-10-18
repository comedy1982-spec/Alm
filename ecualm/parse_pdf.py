"""PDF parser.

* Text: rebuilt from individual characters (pdfplumber) so Korean word spacing and words
  wrapped in the middle of a line are joined correctly; paragraphs are grouped by spacing,
  font size and bullets; headings detected by numbering / bold / size.
* Tables: pdfplumber cell geometry → true row/col spans; tables continued on the next page
  are merged (repeated header removed, split rows and vertical merges stitched together).
* Figures: raster images (PyMuPDF) and vector drawings rendered from the area above/below
  their caption; text labels inside a figure are attached to it instead of the body text.
* Repeated headers / footers and logos are dropped.
"""
from __future__ import annotations
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pdfplumber
import pymupdf

from .blocks import Block, CAPTION_FIG, CAPTION_TBL, HEADING_NUM, norm_text
from .parse_docx import attach_captions

BULLET = re.compile(r"^\s*([-•·▪■□○●◦※]|\(\d+\)|\d+\)|[a-z]\)|[①-⑳])\s*")
SENT_END = re.compile(r"[.。:;!?)\]]\s*$")
LATIN_END = re.compile(r"[A-Za-z0-9,;:)\]]$")
LATIN_START = re.compile(r"^[A-Za-z0-9(\[]")


# ------------------------------------------------------------------ characters -> lines
def chars_to_lines(chars: list[dict], ytol: float = 3.0) -> list[dict]:
    if not chars:
        return []
    rows: list[list[dict]] = []
    for ch in sorted(chars, key=lambda c: (round(c["top"], 1), c["x0"])):
        mid = (ch["top"] + ch["bottom"]) / 2
        for row in rows:
            if abs(row[0]["_mid"] - mid) <= ytol:
                row.append(ch); break
        else:
            ch = dict(ch); ch["_mid"] = mid
            rows.append([ch])
            continue
        row[-1] = dict(row[-1]); row[-1]["_mid"] = row[0]["_mid"]
    lines = []
    for row in rows:
        spaces = [c for c in row if not c["text"].strip()]
        glyphs = sorted([c for c in row if c["text"].strip()], key=lambda c: c["x0"])
        if not glyphs:
            continue
        out, prev = [], None
        for g in glyphs:
            if prev is not None:
                gap = g["x0"] - prev["x1"]
                has_space = any(prev["x0"] < s["x0"] < g["x0"] + 0.1 for s in spaces)
                if has_space or gap > 0.28 * max(prev.get("size", 10), 1):
                    out.append(" ")
            out.append(g["text"])
            prev = g
        last = glyphs[-1]
        sizes = [g.get("size", 10) for g in glyphs]
        bold = sum(1 for g in glyphs if "bold" in g.get("fontname", "").lower()) / len(glyphs) > 0.6
        lines.append({"text": norm_text("".join(out)), "x0": glyphs[0]["x0"], "x1": last["x1"],
                      "top": min(g["top"] for g in glyphs), "bottom": max(g["bottom"] for g in glyphs),
                      "size": max(set(sizes), key=sizes.count), "bold": bold,
                      "trail": any(s["x0"] >= last["x0"] for s in spaces)})
    lines.sort(key=lambda l: l["top"])
    return lines


def join_lines(lines: list[dict]) -> str:
    out = ""
    for i, l in enumerate(lines):
        if i == 0:
            out = l["text"]; continue
        prev = lines[i - 1]
        if prev["trail"] or (LATIN_END.search(out) and LATIN_START.search(l["text"])) or out.endswith((".", ",", ":")):
            out += " " + l["text"]
        else:
            out += l["text"]
    return norm_text(out)


def _inside(bbox, rect, tol=2.0) -> bool:
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    return rect[0] - tol <= cx <= rect[2] + tol and rect[1] - tol <= cy <= rect[3] + tol


def _hf_key(text: str) -> str:
    return re.sub(r"\d+", "#", text.strip())[:80]


# ------------------------------------------------------------------ tables
def table_struct(ppage, t) -> dict:
    """Return {'mat': [[cell_id]], 'cells': {id: text}} using real cell geometry."""
    boxes = [c for row in t.rows for c in row.cells if c]
    xs = sorted({round(v, 1) for b in boxes for v in (b[0], b[2])})
    ys = sorted({round(v, 1) for b in boxes for v in (b[1], b[3])})

    def idx(edges, v):
        return min(range(len(edges)), key=lambda i: abs(edges[i] - v))
    ncol, nrow = len(xs) - 1, len(ys) - 1
    tb = t.bbox
    pchars = [ch for ch in ppage.chars if tb[0] - 2 <= ch["x0"] and ch["x1"] <= tb[2] + 2 and tb[1] - 4 <= ch["top"] and ch["bottom"] <= tb[3] + 4]
    mat = [[None] * ncol for _ in range(nrow)]
    cells = {}
    for k, b in enumerate(boxes):
        c0, c1, r0, r1 = idx(xs, b[0]), idx(xs, b[2]), idx(ys, b[1]), idx(ys, b[3])
        if c1 <= c0 or r1 <= r0:
            continue
        # assign characters by their centre point: glyph boxes often overlap the cell borders
        inside = [ch for ch in pchars if b[0] <= (ch["x0"] + ch["x1"]) / 2 <= b[2] and b[1] <= (ch["top"] + ch["bottom"]) / 2 <= b[3]]
        cells[k] = join_lines(chars_to_lines(inside))
        for r in range(r0, r1):
            for c in range(c0, c1):
                if mat[r][c] is None:
                    mat[r][c] = k
    # drop empty grid lines produced by stray rules
    nid = -1
    for r in range(nrow):
        for c in range(ncol):
            if mat[r][c] is None:
                cells[nid] = ""; mat[r][c] = nid; nid -= 1
    return {"mat": mat, "cells": cells}


def merge_continuation(prev: dict, cur: dict) -> None:
    """Append table `cur` (next page) to `prev`, stitching a row split across the page break."""
    off = max(list(prev["cells"]) + [0]) + 1000
    cur_mat = [[c + off if c >= 0 else c - off for c in row] for row in cur["mat"]]
    cur_cells = {(k + off if k >= 0 else k - off): v for k, v in cur["cells"].items()}
    texts = lambda row: [cur_cells[c] for c in row]
    hdr = [prev["cells"][c] for c in prev["mat"][0]]
    if texts(cur_mat[0]) == hdr:                      # repeated header
        cur_mat = cur_mat[1:]
    if not cur_mat:
        return
    last = prev["mat"][-1]
    first = cur_mat[0]
    filled = [c for c in dict.fromkeys(first) if cur_cells[c].strip()]
    remap = {}
    if len(filled) <= max(1, len(set(first)) // 2):  # remainder of a row split by the page break
        for j, cid in enumerate(first):
            if cid in remap:
                continue
            remap[cid] = last[j]
            if cur_cells[cid].strip():
                prev["cells"][last[j]] = join_lines([{"text": prev["cells"][last[j]], "trail": False},
                                                     {"text": cur_cells[cid], "trail": False}])
        cur_mat = cur_mat[1:]
    else:
        # vertical merges continuing from the previous page (empty cell spanning down from row 0)
        for j, cid in enumerate(first):
            if not cur_cells[cid].strip() and sum(1 for row in cur_mat if row[j] == cid) > 1:
                remap[cid] = last[j]
    for row in cur_mat:
        prev["mat"].append([remap.get(c, c) for c in row])
    for k, v in cur_cells.items():
        if k not in remap:
            prev["cells"][k] = v


def struct_to_grid(s: dict) -> list[list[dict]]:
    mat, cells = s["mat"], s["cells"]
    seen = set()
    grid = []
    for r, row in enumerate(mat):
        g = []
        for c, cid in enumerate(row):
            if cid in seen:
                g.append({"t": cells[cid], "skip": True}); continue
            seen.add(cid)
            cs = 1
            while c + cs < len(row) and row[c + cs] == cid:
                cs += 1
            rs = 1
            while r + rs < len(mat) and mat[r + rs][c] == cid:
                rs += 1
            g.append({"t": cells[cid], "rs": rs, "cs": cs, "skip": False})
        grid.append(g)
    # remove columns that are empty in every row (artifacts of vertical rules)
    keep = [j for j in range(len(grid[0])) if any(row[j]["t"] or not row[j]["skip"] and row[j].get("cs", 1) > 1 for row in grid)]
    if len(keep) < len(grid[0]) and keep:
        grid = [[row[j] for j in keep] for row in grid]
    return grid


# ------------------------------------------------------------------ main
def parse_pdf(path: str | Path, render_dpi: int = 150) -> list[Block]:
    path = str(path)
    doc = pymupdf.open(path)
    plumber = pdfplumber.open(path)
    npages = len(doc)

    # pass 1: header/footer lines, body font size, logos
    page_lines = []
    hf = Counter()
    sizes = Counter()
    img_pages = Counter()
    for pno, ppage in enumerate(plumber.pages):
        lines = chars_to_lines(ppage.chars)
        page_lines.append(lines)
        h = float(ppage.height)
        keys = set()
        for l in lines:
            sizes[round(l["size"], 1)] += len(l["text"])
            if l["top"] < h * 0.08 or l["bottom"] > h * 0.92:
                keys.add(_hf_key(l["text"]))
        for k in keys:
            hf[k] += 1
        page = doc[pno]
        for img in page.get_images(full=True):
            try:
                if page.get_image_rects(img[0]):
                    img_pages[img[0]] += 1
            except Exception:
                pass
    hf_keys = {k for k, c in hf.items() if npages >= 2 and c >= max(2, npages * 0.5)}
    body = sizes.most_common(1)[0][0] if sizes else 10.0
    logos = {x for x, c in img_pages.items() if npages >= 3 and c >= npages * 0.6}

    blocks: list[Block] = []
    tables: dict[int, dict] = {}       # id(block) -> struct, finalized at the end
    for pno, ppage in enumerate(plumber.pages):
        page = doc[pno]
        h, w = float(ppage.height), float(ppage.width)
        loc = f"p.{pno + 1}"
        elems = []   # (top, x0, kind, payload)

        found = []
        for t in ppage.find_tables():
            data_rows = [r for r in t.rows if any(r.cells)]
            if len(data_rows) < 2 or max(len(r.cells) for r in data_rows) < 2:
                continue
            found.append(t.bbox)
            elems.append((t.bbox[1], t.bbox[0], "table", table_struct(ppage, t)))

        img_rects = []
        for img in page.get_images(full=True):
            xref = img[0]
            if xref in logos:
                continue
            try:
                rects = page.get_image_rects(xref)
            except Exception:
                rects = []
            for r in rects[:1]:
                if r.width * r.height < 40 * 40 or r.y1 < h * 0.06 or r.y0 > h * 0.94:
                    continue
                try:
                    info = doc.extract_image(xref)
                    blob, ext = info["image"], info["ext"]
                    if ext not in ("png", "jpg", "jpeg"):
                        pix = pymupdf.Pixmap(doc, xref)
                        if pix.n - pix.alpha >= 4:
                            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                        blob, ext = pix.tobytes("png"), "png"
                except Exception:
                    blob, ext = page.get_pixmap(clip=r, dpi=render_dpi).tobytes("png"), "png"
                img_rects.append(tuple(r))
                elems.append((r.y0, r.x0, "figure", {"bbox": tuple(r), "image": blob, "ext": ext, "labels": [], "render": "raster"}))

        # body lines outside tables / images / header-footer
        lines = []
        for l in page_lines[pno]:
            bb = (l["x0"], l["top"], l["x1"], l["bottom"])
            if any(_inside(bb, tb) for tb in found):
                continue
            if _hf_key(l["text"]) in hf_keys and (l["top"] < h * 0.08 or l["bottom"] > h * 0.92):
                continue
            if any(_inside(bb, r) for r in img_rects):
                for e in elems:
                    if e[2] == "figure" and _inside(bb, e[3]["bbox"]):
                        e[3]["labels"].append(l["text"])
                continue
            lines.append(l)

        # vector figures: caption without a raster image nearby -> render drawings around it
        drawings = None
        for i, l in enumerate(lines):
            if not CAPTION_FIG.match(l["text"]) or l.get("drop"):
                continue
            if any(abs(r[3] - l["top"]) < 60 or abs(r[1] - l["bottom"]) < 60 for r in img_rects):
                continue
            if drawings is None:
                drawings = [d["rect"] for d in page.get_drawings() if d["rect"].width * d["rect"].height > 4]
            # look above the caption first, then below
            for region in (_region_above(lines, i, found, h), _region_below(lines, i, found, h)):
                vec = [d for d in drawings if region.intersects(d) and not any(_inside(tuple(d), tb) for tb in found)]
                if region.height < 25 or len(vec) < 2:
                    continue
                u = vec[0]
                for d in vec[1:]:
                    u |= d
                clip = u & region
                # short text lines (diagram labels) inside the search region belong to the figure
                for o in lines:
                    ob = pymupdf.Rect(o["x0"], o["top"], o["x1"], o["bottom"])
                    if o is not l and region.contains(ob) and not _is_body(o):
                        clip |= ob
                clip = clip + (-6, -6, 6, 6)
                labels = []
                for o in lines:
                    if o is not l and _inside((o["x0"], o["top"], o["x1"], o["bottom"]), tuple(clip)):
                        labels.append(o["text"]); o["drop"] = True
                png = page.get_pixmap(clip=clip, dpi=render_dpi).tobytes("png")
                elems.append((clip.y0, clip.x0, "figure", {"bbox": tuple(clip), "image": png, "ext": "png",
                                                           "labels": labels, "render": "vector"}))
                break

        for para in group_paragraphs([l for l in lines if not l.get("drop")], body):
            elems.append((para["top"], para["x0"], "para", para))

        elems.sort(key=lambda e: (round(e[0] / 3), e[1]))
        for top, x0, kind, p in elems:
            if kind == "table":
                prev = blocks[-1] if blocks else None
                if (prev is not None and prev.kind == "table" and id(prev) in tables and prev.loc != loc
                        and top < h * 0.3 and len(tables[id(prev)]["mat"][0]) == len(p["mat"][0])):
                    merge_continuation(tables[id(prev)], p)
                    prev.loc = re.sub(r"(-\d+)?$", f"-{pno + 1}", prev.loc, count=1)
                else:
                    b = Block(kind="table", loc=loc)
                    tables[id(b)] = p
                    blocks.append(b)
            elif kind == "figure":
                blocks.append(Block(kind="figure", image=p["image"], image_ext=p["ext"], loc=loc,
                                    text=" | ".join(p["labels"]), style=p["render"]))
            else:
                _emit(blocks, p, body, loc, h)
    for b in blocks:
        if b.kind == "table":
            b.grid = struct_to_grid(tables[id(b)])
    plumber.close()
    return attach_captions(blocks)


def _region_above(lines, i, tables, h):
    cap = lines[i]
    bottoms = [o["bottom"] for o in lines[:i] if o["bottom"] <= cap["top"] and _is_body(o)]
    bottoms += [t[3] for t in tables if t[3] <= cap["top"]]
    top = max(bottoms) if bottoms else h * 0.07
    return pymupdf.Rect(20, top + 1, 10_000, cap["top"] - 1)


def _region_below(lines, i, tables, h):
    cap = lines[i]
    tops = [o["top"] for o in lines[i + 1:] if o["top"] >= cap["bottom"] and _is_body(o)]
    tops += [t[1] for t in tables if t[1] >= cap["bottom"]]
    bottom = min(tops) if tops else h * 0.93
    return pymupdf.Rect(20, cap["bottom"] + 1, 10_000, bottom - 1)


def _is_body(o) -> bool:
    """Long lines or sentences are body text; short fragments are probably diagram labels."""
    t = o["text"]
    return len(t) >= 30 or bool(SENT_END.search(t)) or bool(HEADING_NUM.match(t)) or bool(CAPTION_TBL.match(t))


def group_paragraphs(lines: list[dict], body: float) -> list[dict]:
    paras, cur = [], []
    for l in lines:
        if cur:
            p = cur[-1]
            lh = max(p["bottom"] - p["top"], 1)
            new = (l["top"] - p["bottom"] > 0.65 * lh or abs(l["size"] - p["size"]) > 0.6 or l["bold"] != p["bold"]
                   or BULLET.match(l["text"]) or CAPTION_FIG.match(l["text"]) or CAPTION_TBL.match(l["text"])
                   or HEADING_NUM.match(l["text"]) and (l["bold"] or l["size"] > body + 0.5)
                   or abs(l["x0"] - cur[0]["x0"]) > 40 and len(cur) == 1 and abs(l["x0"] - p["x0"]) > 40)
            if new:
                paras.append(cur); cur = []
        cur.append(l)
    if cur:
        paras.append(cur)
    out = []
    for p in paras:
        out.append({"text": join_lines(p), "top": p[0]["top"], "x0": min(l["x0"] for l in p), "size": p[0]["size"],
                    "bold": all(l["bold"] for l in p), "nlines": len(p)})
    return out


def _emit(blocks: list[Block], p: dict, body: float, loc: str, page_h: float):
    t = p["text"]
    m = HEADING_NUM.match(t)
    heading = False
    if p["nlines"] <= 2 and len(t) < 90 and not CAPTION_FIG.match(t) and not CAPTION_TBL.match(t) \
            and not re.search(r"(다|함|음)\s*[.]?\s*$", t):
        if p["size"] >= body + 0.8 or (p["bold"] and len(t) < 60):
            heading = True
        elif m and m.group(1).count(".") >= 1 and len(t) < 60:
            heading = True
    if heading:
        if m:
            number, title = m.group(1), m.group(2)
            level = number.count(".") + 1
        else:
            number, title = "", t
            level = 1 if p["size"] >= body + 3 else 2 if p["size"] >= body + 1.5 else 3
        blocks.append(Block(kind="heading", text=title, number=number, level=level, loc=loc))
        return
    prev = blocks[-1] if blocks else None
    # paragraph continued from the previous page
    if (prev is not None and prev.kind == "para" and prev.loc != loc and p["top"] < page_h * 0.2
            and not SENT_END.search(prev.text) and not BULLET.match(t) and not HEADING_NUM.match(t)):
        prev.text = norm_text(prev.text + t)
        return
    blocks.append(Block(kind="para", text=t, loc=loc, list_level=0 if BULLET.match(t) else -1))
