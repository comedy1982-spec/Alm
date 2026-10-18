"""Editing operations shared by the CLI and the web server."""
from __future__ import annotations

from .audit import validate_link
from .classify import Analyzer, quantities
from .db import Repo
from .importer import REQ_TYPES, fingerprint

STATUSES = ("draft", "review", "approved", "rejected", "deleted")


def _fmt(cfg, typ, domain=""):
    return cfg["id_format"] if ((typ in REQ_TYPES or typ.endswith("_TC")) and domain != typ) else cfg["id_format_no_domain"]


def create_item(repo: Repo, cfg: dict, typ: str, text: str, domain: str | None = None, doc: str = "",
                section: str = "", after: str | None = None, title: str = "", attrs: dict | None = None,
                user: str = "") -> dict:
    if typ not in cfg["types"]:
        raise ValueError(f"알 수 없는 타입: {typ}")
    an = Analyzer(cfg)
    domain = domain or (an.domain(text, section) if (typ in REQ_TYPES or typ.endswith("_TC")) else "GEN")
    ord_ = 0.0
    if after:
        a = repo.get(after)
        if a:
            doc, section = doc or a["doc"], section or a["section"]
            nxt = repo.con.execute("SELECT MIN(ord) FROM items WHERE doc=? AND ord>?", (a["doc"], a["ord"])).fetchone()[0]
            ord_ = (a["ord"] + nxt) / 2 if nxt is not None else a["ord"] + 10
    elif doc:
        mx = repo.con.execute("SELECT MAX(ord) FROM items WHERE doc=?", (doc,)).fetchone()[0]
        ord_ = (mx or 0) + 10
    new_id = repo.next_id(_fmt(cfg, typ, domain), cfg["types"][typ]["prefix"], domain, cfg)
    at = {"quantities": quantities(text), **(attrs or {})}
    it = repo.insert({"id": new_id, "type": typ, "domain": domain, "title": title or text[:80], "text": text,
                      "attrs": at, "lint": an.lint(text, typ) if typ in REQ_TYPES else [], "doc": doc,
                      "section": section, "ord": ord_, "fingerprint": fingerprint(text), "source_loc": "manual"},
                     by=user or "manual")
    repo.commit()
    return it


def edit_item(repo: Repo, cfg: dict, item_id: str, text: str | None = None, status: str | None = None,
              custom: dict | None = None, user: str = "", attrs: dict | None = None) -> dict:
    cur = repo.get(item_id)
    if not cur:
        raise KeyError(item_id)
    changes = {}
    content_changed = False
    if text is not None and text != cur["text"]:
        an = Analyzer(cfg)
        new_attrs = dict(cur["attrs"])
        new_attrs["quantities"] = quantities(text)
        new_attrs["prev_text"] = cur["text"]
        # a title that was only the first 80 chars of the text follows the text; a real name (block, unit) stays
        title = text[:80] if cur["type"] in REQ_TYPES and cur["title"] == cur["text"][:80] else cur["title"]
        changes.update(text=text, title=title, fingerprint=fingerprint(text), attrs=new_attrs,
                       lint=an.lint(text, cur["type"]) if cur["type"] in REQ_TYPES else [])
        content_changed = True
        if cur["status"] == "approved" and status is None:
            changes["status"] = "draft"
    if attrs:
        a = changes.get("attrs", dict(cur["attrs"]))
        a.update(attrs)
        changes["attrs"] = a
        content_changed = True
    if custom:
        a = changes.get("attrs", dict(cur["attrs"]))
        a["custom"] = {**a.get("custom", {}), **custom}
        changes["attrs"] = a
        content_changed = True
    if status is not None:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        changes["status"] = status
    if not changes:
        return cur
    it = repo.update(item_id, changes, change="edited" if content_changed else f"status:{changes.get('status')}",
                     by=user or "manual", mark_suspect=content_changed)
    repo.commit()
    return it


def reclassify(repo: Repo, cfg: dict, item_id: str, new_type: str, domain: str | None = None, user: str = "") -> dict:
    """Type changes alter the ID prefix, so a new ID is issued; the old one is retired (never reused)
    and the links are moved to the new item."""
    cur = repo.get(item_id)
    if not cur:
        raise KeyError(item_id)
    if new_type not in cfg["types"]:
        raise ValueError(f"알 수 없는 타입: {new_type}")
    domain = domain or cur["domain"]
    new_id = repo.next_id(_fmt(cfg, new_type, domain), cfg["types"][new_type]["prefix"], domain, cfg)
    attrs = {**cur["attrs"], "former_id": item_id}
    an = Analyzer(cfg)
    repo.insert({"id": new_id, "type": new_type, "domain": domain, "title": cur["title"], "text": cur["text"],
                 "status": "draft", "attrs": attrs, "lint": an.lint(cur["text"], new_type) if new_type in REQ_TYPES else [],
                 "doc": cur["doc"], "doc_rev": cur["doc_rev"], "section": cur["section"], "source_loc": cur["source_loc"],
                 "ord": cur["ord"], "fingerprint": cur["fingerprint"]}, by=user or "manual")
    for l in repo.links(item_id):
        repo.remove_link(l["src"], l["role"], l["dst"])
        src = new_id if l["src"] == item_id else l["src"]
        dst = new_id if l["dst"] == item_id else l["dst"]
        repo.add_link(src, l["role"], dst, state="proposed", note=f"moved from {item_id}")
    repo.update(item_id, {"status": "deleted", "attrs": {**cur["attrs"], "moved_to": new_id}},
                change=f"reclassified→{new_id}", by=user or "manual", mark_suspect=False)
    repo.commit()
    return repo.get(new_id)


def link(repo: Repo, cfg: dict, src: str, role: str, dst: str, force: bool = False) -> None:
    s, d = repo.get(src), repo.get(dst)
    if not s or not d:
        raise KeyError(f"아이템 없음: {src if not s else dst}")
    if not force and not validate_link(cfg, s["type"], role, d["type"]):
        from .audit import allowed_roles
        ok = allowed_roles(cfg, s["type"], d["type"])
        raise ValueError(f"{s['type']} -{role}-> {d['type']} 는 스키마에 없음. 허용: {ok or '없음'}")
    repo.add_link(src, role, dst, state="confirmed")
    repo.commit()
