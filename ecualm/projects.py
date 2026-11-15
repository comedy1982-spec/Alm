"""Several projects in one server: the folder the server was started in is the first project ("default"),
further projects live in <root>/projects/<id>/, each with its own alm.json and .alm/ (database, assets,
evidence, sources). Accounts are shared: they stay in the first project's database."""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import time
from pathlib import Path

from .config import load_config, write_default_config
from .db import Repo

DEFAULT = "default"
ID_RE = re.compile(r"^[\w][\w-]{0,39}$")
CONTENT = ("HDG", "INFO", "TBL", "FIG")


def slug(name: str) -> str:
    s = re.sub(r"[^\w-]+", "_", name.strip(), flags=re.UNICODE).strip("_")[:40]
    return s or time.strftime("p%Y%m%d_%H%M%S")


class Workspace:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.dir = self.root / "projects"

    def path(self, pid: str) -> Path:
        if pid == DEFAULT:
            return self.root
        if not ID_RE.match(pid or ""):
            raise KeyError(pid)
        return self.dir / pid

    def exists(self, pid: str) -> bool:
        try:
            return pid == DEFAULT or (self.path(pid) / "alm.json").exists()
        except KeyError:
            return False

    def ids(self) -> list[str]:
        out = [DEFAULT]
        if self.dir.exists():
            out += sorted(p.name for p in self.dir.iterdir() if ID_RE.match(p.name) and (p / "alm.json").exists())
        return out

    def info(self, pid: str) -> dict:
        root = self.path(pid)
        cfg = load_config(root)
        out = {"id": pid, "name": str(cfg.get("project") or pid), "requirements": 0, "items": 0, "docs": 0, "updated": 0}
        db = root / ".alm" / "alm.db"
        if db.exists():
            con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=5)
            try:
                q = ",".join("?" * len(CONTENT))
                out["requirements"] = con.execute(
                    f"SELECT count(*) FROM items WHERE status!='deleted' AND type NOT IN ({q})", CONTENT).fetchone()[0]
                out["items"] = con.execute("SELECT count(*) FROM items WHERE status!='deleted'").fetchone()[0]
                out["docs"] = con.execute("SELECT count(DISTINCT doc) FROM imports").fetchone()[0]
            except sqlite3.Error:
                pass
            finally:
                con.close()
            out["updated"] = db.stat().st_mtime
        return out

    def list(self) -> list[dict]:
        return [self.info(p) for p in self.ids()]

    def create(self, name: str, pid: str = "", copy_from: str = "") -> dict:
        """New empty project. copy_from: take that project's settings (alm.json: types, ID formats, stages, AI
        endpoint and its key file) — never its requirements."""
        name = (name or "").strip()
        if not name or len(name) > 60:
            raise ValueError("프로젝트 이름을 1~60자로 입력하세요")
        pid = (pid or "").strip() or slug(name)
        if not ID_RE.match(pid) or pid == DEFAULT:
            raise ValueError("프로젝트 ID 는 글자·숫자·_·- 만 쓸 수 있습니다 (40자 이내)")
        if any(p.lower() == pid.lower() for p in self.ids()):
            raise ValueError(f"이미 있는 프로젝트 ID 입니다: {pid}")
        if any(i["name"] == name for i in self.list()):
            raise ValueError(f"같은 이름의 프로젝트가 이미 있습니다: {name}")
        root = self.dir / pid
        root.mkdir(parents=True)
        cfgf = write_default_config(root)
        cfg = json.loads(cfgf.read_text(encoding="utf-8"))
        if copy_from and self.exists(copy_from):
            src = self.path(copy_from)
            if (src / "alm.json").exists():
                cfg = json.loads((src / "alm.json").read_text(encoding="utf-8"))
            sec = src / ".alm" / "secrets.json"
            if sec.exists():
                (root / ".alm").mkdir(exist_ok=True)
                shutil.copy2(sec, root / ".alm" / "secrets.json")
        cfg["project"] = name
        cfgf.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        Repo(root)
        return self.info(pid)

    def rename(self, pid: str, name: str) -> dict:
        name = (name or "").strip()
        if not name or len(name) > 60:
            raise ValueError("프로젝트 이름을 1~60자로 입력하세요")
        if any(i["name"] == name and i["id"] != pid for i in self.list()):
            raise ValueError(f"같은 이름의 프로젝트가 이미 있습니다: {name}")
        cfgf = self.path(pid) / "alm.json"
        cfg = json.loads(cfgf.read_text(encoding="utf-8")) if cfgf.exists() else {}
        cfg["project"] = name
        cfgf.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.info(pid)
