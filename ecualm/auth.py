"""Login, sessions, roles and API tokens (stdlib only).

Accounts live in the project database (.alm/alm.db). Passwords are stored as PBKDF2-SHA256 hashes with a
per-user salt; session and API tokens are stored only as SHA-256 hashes, so a copy of the database does not
give anyone a working login.

Roles (each includes the rights of the ones below it):
  admin     user management, AI settings, everything else
  manager   project plan (MAN.3 schedule / effort / baselines), item baselines
  engineer  edit requirements, links, derive, import; report progress and actual effort on own tasks
  viewer    read only (the AI assistant may still answer questions)
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import functools
import secrets
import sqlite3
import threading
import time

ROLES = ("viewer", "engineer", "manager", "admin")
ROLE_LABEL = {"viewer": "조회", "engineer": "엔지니어", "manager": "PM", "admin": "관리자"}
ITER = 240_000
MIN_PW = 8
COOKIE = "ecualm_sid"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username  TEXT PRIMARY KEY,
    name      TEXT NOT NULL DEFAULT '',
    role      TEXT NOT NULL DEFAULT 'engineer',
    pw_hash   TEXT NOT NULL,
    salt      TEXT NOT NULL,
    iters     INTEGER NOT NULL,
    disabled  INTEGER NOT NULL DEFAULT 0,
    must_change INTEGER NOT NULL DEFAULT 0,
    created   REAL NOT NULL,
    last_login REAL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    username   TEXT NOT NULL,
    created    REAL NOT NULL,
    expires    REAL NOT NULL,
    last_seen  REAL NOT NULL,
    addr       TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS api_tokens (
    token_hash TEXT PRIMARY KEY,
    username   TEXT NOT NULL,
    label      TEXT NOT NULL DEFAULT '',
    created    REAL NOT NULL,
    last_used  REAL
);
CREATE TABLE IF NOT EXISTS auth_log (
    at REAL NOT NULL, username TEXT, event TEXT NOT NULL, addr TEXT, detail TEXT
);
"""


class AuthError(Exception):
    def __init__(self, msg: str, code: int = 401):
        super().__init__(msg)
        self.code = code


def _h(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _pw(password: str, salt: str, iters: int) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), iters).hex()


def rank(role: str) -> int:
    return ROLES.index(role) if role in ROLES else -1


def is_loopback(addr: str) -> bool:
    try:
        return ipaddress.ip_address(addr.split("%")[0]).is_loopback
    except ValueError:
        return False


def _locked(fn):
    @functools.wraps(fn)
    def w(self, *a, **k):
        with self._db:
            return fn(self, *a, **k)
    return w


class Auth:
    """Own connection to the project database plus a re-entrant lock: auth calls run outside the item write lock."""

    def __init__(self, repo, cfg: dict | None = None):
        self._db = threading.RLock()
        self.con = sqlite3.connect(repo.dir / "alm.db", check_same_thread=False, timeout=15)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(SCHEMA)
        self.con.commit()
        a = (cfg or {}).get("auth", {})
        self.session_hours = float(a.get("session_hours", 12))
        self.idle_minutes = float(a.get("idle_minutes", 120))
        self._fail: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    # ---------------- users ----------------
    @_locked
    def count(self) -> int:
        return self.con.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    @_locked
    def user(self, username: str) -> dict | None:
        r = self.con.execute("SELECT username,name,role,disabled,must_change,created,last_login FROM users WHERE username=?",
                             (username,)).fetchone()
        return dict(r) if r else None

    @_locked
    def users(self) -> list[dict]:
        return [dict(r) for r in self.con.execute(
            "SELECT username,name,role,disabled,must_change,created,last_login FROM users ORDER BY username")]

    @staticmethod
    def _check_pw(pw: str):
        if len(pw or "") < MIN_PW:
            raise AuthError(f"비밀번호는 {MIN_PW}자 이상이어야 합니다", 400)

    @staticmethod
    def _check_name(username: str) -> str:
        u = (username or "").strip()
        if not u or len(u) > 40 or not all(c.isalnum() or c in "._-@" for c in u):
            raise AuthError("아이디는 영문·숫자·._-@ 조합 40자 이내로 입력하세요", 400)
        return u

    @_locked
    def create_user(self, username: str, password: str, name: str = "", role: str = "engineer",
                    must_change: bool = False) -> dict:
        u = self._check_name(username)
        if role not in ROLES:
            raise AuthError(f"역할은 {', '.join(ROLES)} 중 하나", 400)
        self._check_pw(password)
        if self.user(u):
            raise AuthError("이미 있는 아이디입니다", 409)
        salt = secrets.token_hex(16)
        self.con.execute("INSERT INTO users(username,name,role,pw_hash,salt,iters,must_change,created) VALUES(?,?,?,?,?,?,?,?)",
                         (u, name.strip() or u, role, _pw(password, salt, ITER), salt, ITER, int(must_change), time.time()))
        self.con.commit()
        self._log(u, "user_created", "", role)
        return self.user(u)

    @_locked
    def update_user(self, username: str, name: str | None = None, role: str | None = None,
                    disabled: bool | None = None, actor: str = "") -> dict:
        cur = self.user(username)
        if not cur:
            raise AuthError("사용자를 찾을 수 없습니다", 404)
        if role is not None and role not in ROLES:
            raise AuthError("알 수 없는 역할", 400)
        losing_admin = cur["role"] == "admin" and ((role is not None and role != "admin") or disabled)
        if losing_admin and self._admins() <= 1:
            raise AuthError("마지막 관리자는 권한을 낮추거나 비활성화할 수 없습니다", 400)
        if name is not None:
            self.con.execute("UPDATE users SET name=? WHERE username=?", (name.strip() or username, username))
        if role is not None:
            self.con.execute("UPDATE users SET role=? WHERE username=?", (role, username))
        if disabled is not None:
            self.con.execute("UPDATE users SET disabled=? WHERE username=?", (int(disabled), username))
            if disabled:
                self.con.execute("DELETE FROM sessions WHERE username=?", (username,))
        self.con.commit()
        self._log(username, "user_updated", "", f"by {actor}: role={role} disabled={disabled}")
        return self.user(username)

    @_locked
    def _admins(self) -> int:
        return self.con.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND disabled=0").fetchone()[0]

    @_locked
    def set_password(self, username: str, new: str, old: str | None = None, must_change: bool = False) -> None:
        r = self.con.execute("SELECT pw_hash,salt,iters FROM users WHERE username=?", (username,)).fetchone()
        if not r:
            raise AuthError("사용자를 찾을 수 없습니다", 404)
        if old is not None and not hmac.compare_digest(_pw(old, r["salt"], r["iters"]), r["pw_hash"]):
            raise AuthError("현재 비밀번호가 맞지 않습니다", 400)
        self._check_pw(new)
        salt = secrets.token_hex(16)
        self.con.execute("UPDATE users SET pw_hash=?,salt=?,iters=?,must_change=? WHERE username=?",
                         (_pw(new, salt, ITER), salt, ITER, int(must_change), username))
        self.con.commit()
        self._log(username, "password_changed", "", "reset" if old is None else "self")

    # ---------------- sessions ----------------
    @_locked
    def login(self, username: str, password: str, addr: str = "") -> tuple[str, dict]:
        u = (username or "").strip()
        with self._lock:
            now = time.time()
            recent = [t for t in self._fail.get(u, []) if now - t < 300]
            self._fail[u] = recent
            if len(recent) >= 5 and now - recent[-1] < 60:
                raise AuthError("로그인 실패가 반복되어 잠시 잠겼습니다. 1분 뒤 다시 시도하세요", 429)
        r = self.con.execute("SELECT * FROM users WHERE username=?", (u,)).fetchone()
        ok = bool(r) and hmac.compare_digest(_pw(password or "", r["salt"], r["iters"]), r["pw_hash"])
        if not r:   # same cost as a real check, so unknown names are not revealed by timing
            _pw(password or "", "00" * 16, ITER)
        if not ok or r["disabled"]:
            with self._lock:
                self._fail.setdefault(u, []).append(time.time())
            self._log(u, "login_failed", addr, "disabled" if ok else "")
            raise AuthError("아이디 또는 비밀번호가 올바르지 않습니다")
        self._fail.pop(u, None)
        token = secrets.token_urlsafe(32)
        now = time.time()
        self.con.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?)",
                         (_h(token), u, now, now + self.session_hours * 3600, now, addr))
        self.con.execute("UPDATE users SET last_login=? WHERE username=?", (now, u))
        self.con.execute("DELETE FROM sessions WHERE expires<?", (now,))
        self.con.commit()
        self._log(u, "login", addr, "")
        return token, self.user(u)

    @_locked
    def logout(self, token: str) -> None:
        if token:
            self.con.execute("DELETE FROM sessions WHERE token_hash=?", (_h(token),))
            self.con.commit()

    @_locked
    def session_user(self, token: str) -> dict | None:
        if not token:
            return None
        r = self.con.execute("SELECT * FROM sessions WHERE token_hash=?", (_h(token),)).fetchone()
        now = time.time()
        if not r:
            return None
        if r["expires"] < now or now - r["last_seen"] > self.idle_minutes * 60:
            self.con.execute("DELETE FROM sessions WHERE token_hash=?", (r["token_hash"],)); self.con.commit()
            return None
        u = self.user(r["username"])
        if not u or u["disabled"]:
            return None
        if now - r["last_seen"] > 30:
            self.con.execute("UPDATE sessions SET last_seen=? WHERE token_hash=?", (now, r["token_hash"])); self.con.commit()
        return u

    # ---------------- API tokens (CI, scripts) ----------------
    @_locked
    def create_token(self, username: str, label: str = "") -> str:
        if not self.user(username):
            raise AuthError("사용자를 찾을 수 없습니다", 404)
        token = "alm_" + secrets.token_urlsafe(32)
        self.con.execute("INSERT INTO api_tokens VALUES(?,?,?,?,NULL)", (_h(token), username, label, time.time()))
        self.con.commit()
        self._log(username, "token_created", "", label)
        return token

    @_locked
    def token_user(self, token: str) -> dict | None:
        r = self.con.execute("SELECT username FROM api_tokens WHERE token_hash=?", (_h(token or ""),)).fetchone()
        if not r:
            return None
        u = self.user(r["username"])
        if not u or u["disabled"]:
            return None
        self.con.execute("UPDATE api_tokens SET last_used=? WHERE token_hash=?", (time.time(), _h(token))); self.con.commit()
        return u

    @_locked
    def revoke_tokens(self, username: str) -> int:
        n = self.con.execute("DELETE FROM api_tokens WHERE username=?", (username,)).rowcount
        self.con.commit()
        return n

    @_locked
    def _log(self, username, event, addr, detail):
        self.con.execute("INSERT INTO auth_log VALUES(?,?,?,?,?)", (time.time(), username, event, addr, detail))
        self.con.commit()

    @_locked
    def log(self, limit: int = 100) -> list[dict]:
        return [dict(r) for r in self.con.execute("SELECT * FROM auth_log ORDER BY at DESC LIMIT ?", (limit,))]
