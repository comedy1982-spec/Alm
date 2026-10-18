"""SQLite repository: work items, links, history, assets, baselines and ID counters."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id            TEXT PRIMARY KEY,           -- stable ID, never reused (e.g. SWE1-COM-0007)
    type          TEXT NOT NULL,              -- key of config.types
    domain        TEXT NOT NULL DEFAULT 'GEN',
    title         TEXT NOT NULL DEFAULT '',
    text          TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'draft',  -- draft | review | approved | deleted
    attrs         TEXT NOT NULL DEFAULT '{}', -- JSON: table grid, figure, native_id, custom fields ...
    lint          TEXT NOT NULL DEFAULT '[]', -- JSON list of lint findings
    doc           TEXT NOT NULL DEFAULT '',   -- source document name (LiveDoc)
    doc_rev       TEXT NOT NULL DEFAULT '',
    section       TEXT NOT NULL DEFAULT '',   -- section path, e.g. "3.2 CAN 통신"
    source_loc    TEXT NOT NULL DEFAULT '',   -- page / paragraph anchor in the original
    ord           REAL NOT NULL DEFAULT 0,    -- order inside the document
    fingerprint   TEXT NOT NULL DEFAULT '',
    version       INTEGER NOT NULL DEFAULT 1,
    created       REAL NOT NULL,
    updated       REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_items_doc  ON items(doc, ord);
CREATE INDEX IF NOT EXISTS ix_items_type ON items(type);

CREATE TABLE IF NOT EXISTS history (
    id        TEXT NOT NULL,
    version   INTEGER NOT NULL,
    text      TEXT NOT NULL,
    attrs     TEXT NOT NULL,
    status    TEXT NOT NULL,
    change    TEXT NOT NULL,                 -- created | modified | deleted | restored | edited
    import_id TEXT,
    at        REAL NOT NULL,
    by        TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_hist ON history(id, version);

CREATE TABLE IF NOT EXISTS links (
    src      TEXT NOT NULL,   -- downstream item (depends on dst)
    role     TEXT NOT NULL,
    dst      TEXT NOT NULL,   -- upstream item
    state    TEXT NOT NULL DEFAULT 'confirmed',  -- confirmed | proposed
    suspect  INTEGER NOT NULL DEFAULT 0,
    note     TEXT NOT NULL DEFAULT '',
    created  REAL NOT NULL,
    PRIMARY KEY (src, role, dst)
);
CREATE INDEX IF NOT EXISTS ix_links_dst ON links(dst);

CREATE TABLE IF NOT EXISTS counters (key TEXT PRIMARY KEY, next INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS imports (
    import_id TEXT PRIMARY KEY, doc TEXT, rev TEXT, path TEXT, at REAL, summary TEXT
);

CREATE TABLE IF NOT EXISTS baselines (
    name TEXT PRIMARY KEY, at REAL, note TEXT, snapshot TEXT
);
"""


class Repo:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.dir = self.root / ".alm"
        self.assets = self.dir / "assets"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.assets.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(self.dir / "alm.db", check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(SCHEMA)
        self.con.commit()

    # ---------------- items ----------------
    @staticmethod
    def _row(r: sqlite3.Row | None) -> dict | None:
        if r is None:
            return None
        d = dict(r)
        d["attrs"] = json.loads(d["attrs"])
        d["lint"] = json.loads(d["lint"])
        return d

    def get(self, item_id: str) -> dict | None:
        return self._row(self.con.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone())

    def items(self, doc: str | None = None, type_: str | None = None, include_deleted=False) -> list[dict]:
        q, a = "SELECT * FROM items WHERE 1=1", []
        if doc:
            q += " AND doc=?"; a.append(doc)
        if type_:
            q += " AND type=?"; a.append(type_)
        if not include_deleted:
            q += " AND status!='deleted'"
        q += " ORDER BY doc, ord"
        return [self._row(r) for r in self.con.execute(q, a)]

    def docs(self) -> list[dict]:
        rows = self.con.execute(
            "SELECT doc, MAX(doc_rev) rev, COUNT(*) n, SUM(CASE WHEN status='approved' THEN 1 ELSE 0 END) approved "
            "FROM items WHERE status!='deleted' AND doc!='' GROUP BY doc ORDER BY doc").fetchall()
        return [dict(r) for r in rows]

    def next_id(self, key_fmt: str, prefix: str, domain: str, cfg: dict) -> str:
        """Allocate the next ID. The counter key is the rendered prefix so numbering is per type(+domain)."""
        if "{domain}" in key_fmt:
            ckey = f"{prefix}-{domain}"
        else:
            ckey = prefix
        cur = self.con.execute("SELECT next FROM counters WHERE key=?", (ckey,)).fetchone()
        n = cur["next"] if cur else 1
        while True:
            new_id = key_fmt.format(prefix=prefix, domain=domain, n=n)
            if not self.con.execute("SELECT 1 FROM items WHERE id=?", (new_id,)).fetchone():
                break
            n += 1
        self.con.execute("INSERT INTO counters(key,next) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET next=excluded.next",
                         (ckey, n + 1))
        return new_id

    def insert(self, item: dict, import_id: str | None = None, by: str = "import") -> dict:
        now = time.time()
        item.setdefault("status", "draft")
        item.setdefault("attrs", {})
        item.setdefault("lint", [])
        self.con.execute(
            "INSERT INTO items(id,type,domain,title,text,status,attrs,lint,doc,doc_rev,section,source_loc,ord,fingerprint,version,created,updated)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)",
            (item["id"], item["type"], item.get("domain", "GEN"), item.get("title", ""), item.get("text", ""),
             item["status"], json.dumps(item["attrs"], ensure_ascii=False), json.dumps(item["lint"], ensure_ascii=False),
             item.get("doc", ""), item.get("doc_rev", ""), item.get("section", ""), item.get("source_loc", ""),
             item.get("ord", 0), item.get("fingerprint", ""), now, now))
        self._hist(item["id"], 1, item.get("text", ""), item["attrs"], item["status"], "created", import_id, by)
        return self.get(item["id"])

    def update(self, item_id: str, changes: dict, change: str = "modified", import_id: str | None = None,
               by: str = "", bump_version: bool = True, mark_suspect: bool = True) -> dict:
        cur = self.get(item_id)
        if cur is None:
            raise KeyError(item_id)
        fields = dict(changes)
        if "attrs" in fields:
            fields["attrs"] = json.dumps(fields["attrs"], ensure_ascii=False)
        if "lint" in fields:
            fields["lint"] = json.dumps(fields["lint"], ensure_ascii=False)
        version = cur["version"] + 1 if bump_version else cur["version"]
        fields["version"] = version
        fields["updated"] = time.time()
        sets = ", ".join(f"{k}=?" for k in fields)
        self.con.execute(f"UPDATE items SET {sets} WHERE id=?", (*fields.values(), item_id))
        new = self.get(item_id)
        if bump_version:
            self._hist(item_id, version, new["text"], new["attrs"], new["status"], change, import_id, by)
            if mark_suspect:
                # Everything that depends on this item must be re-reviewed
                self.con.execute("UPDATE links SET suspect=1 WHERE dst=?", (item_id,))
        return new

    def _hist(self, item_id, version, text, attrs, status, change, import_id, by):
        self.con.execute("INSERT INTO history(id,version,text,attrs,status,change,import_id,at,by) VALUES(?,?,?,?,?,?,?,?,?)",
                         (item_id, version, text, json.dumps(attrs, ensure_ascii=False), status, change, import_id,
                          time.time(), by))

    def history(self, item_id: str) -> list[dict]:
        rows = self.con.execute("SELECT * FROM history WHERE id=? ORDER BY version", (item_id,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["attrs"] = json.loads(d["attrs"])
            out.append(d)
        return out

    # ---------------- links ----------------
    def add_link(self, src: str, role: str, dst: str, state: str = "confirmed", note: str = "") -> None:
        self.con.execute("INSERT INTO links(src,role,dst,state,suspect,note,created) VALUES(?,?,?,?,0,?,?) "
                         "ON CONFLICT(src,role,dst) DO UPDATE SET state=excluded.state",
                         (src, role, dst, state, note, time.time()))

    def remove_link(self, src: str, role: str, dst: str) -> int:
        return self.con.execute("DELETE FROM links WHERE src=? AND role=? AND dst=?", (src, role, dst)).rowcount

    def links(self, item_id: str | None = None) -> list[dict]:
        if item_id:
            rows = self.con.execute("SELECT * FROM links WHERE src=? OR dst=?", (item_id, item_id)).fetchall()
        else:
            rows = self.con.execute("SELECT * FROM links").fetchall()
        return [dict(r) for r in rows]

    def clear_suspect(self, src: str | None = None, dst: str | None = None) -> int:
        q, a = "UPDATE links SET suspect=0 WHERE 1=1", []
        if src:
            q += " AND src=?"; a.append(src)
        if dst:
            q += " AND dst=?"; a.append(dst)
        return self.con.execute(q, a).rowcount

    # ---------------- imports / baselines ----------------
    def record_import(self, import_id, doc, rev, path, summary):
        self.con.execute("INSERT INTO imports VALUES(?,?,?,?,?,?)",
                         (import_id, doc, rev, str(path), time.time(), json.dumps(summary, ensure_ascii=False)))

    def imports(self) -> list[dict]:
        out = []
        for r in self.con.execute("SELECT * FROM imports ORDER BY at"):
            d = dict(r)
            d["summary"] = json.loads(d["summary"])
            out.append(d)
        return out

    def create_baseline(self, name: str, note: str = "") -> dict:
        snap = {"items": self.items(include_deleted=True), "links": self.links()}
        self.con.execute("INSERT INTO baselines VALUES(?,?,?,?)",
                         (name, time.time(), note, json.dumps(snap, ensure_ascii=False)))
        self.commit()
        return {"name": name, "items": len(snap["items"]), "links": len(snap["links"])}

    def baselines(self) -> list[dict]:
        return [dict(name=r["name"], at=r["at"], note=r["note"])
                for r in self.con.execute("SELECT name,at,note FROM baselines ORDER BY at")]

    def baseline(self, name: str) -> dict | None:
        r = self.con.execute("SELECT snapshot FROM baselines WHERE name=?", (name,)).fetchone()
        return json.loads(r["snapshot"]) if r else None

    def commit(self):
        self.con.commit()
