"""Local web UI server (stdlib only). Run: ecualm serve --port 8765"""
from __future__ import annotations

import http.cookies
import json
import mimetypes
import sys
import tempfile
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import arch, assistant, changes, ops, reqif, schedule, sources, sup, testruns, workproducts
from .auth import COOKIE, ROLE_LABEL, ROLES, Auth, AuthError, is_loopback, rank
from .audit import run_audit, suggest_links
from .config import load_config
from .db import Repo
from .export import export_excel, state_payload
from .importer import import_document
from .stages import derive, stage_doc

WEB = Path(__file__).parent / "web"
LOCK = threading.Lock()


# Minimum role per POST path (anything not listed needs "engineer"). /api/plan/* checks rights per task.
POST_ROLE = {"/api/chat": "viewer", "/api/auth/logout": "viewer", "/api/auth/password": "viewer",
             "/api/plan/task": "viewer", "/api/plan/task/delete": "viewer", "/api/plan/baseline": "viewer",
             "/api/plan/template": "viewer", "/api/plan/meta": "manager", "/api/baseline": "manager",
             "/api/ai/settings": "admin", "/api/users": "admin", "/api/users/update": "admin", "/api/users/reset": "admin",
             "/api/users/token": "admin", "/api/wpcol": "manager", "/api/wpcol/update": "manager",
             "/api/wpcol/delete": "manager"}
PUBLIC_POST = {"/api/auth/login", "/api/auth/setup"}


def _pub(u: dict | None) -> dict | None:
    if not u:
        return None
    return {"username": u["username"], "name": u.get("name") or u["username"], "role": u["role"],
            "role_label": ROLE_LABEL.get(u["role"], u["role"]), "must_change": bool(u.get("must_change"))}


def make_handler(root: Path):
    repo = Repo(root)
    cfg0 = load_config(root)
    auth = Auth(repo, cfg0)
    schedule.init(repo)
    workproducts.init(repo)
    testruns.init(repo)
    sup.init(repo)
    changes.init(repo)
    sources.init(repo)
    auth_on = bool(cfg0.get("auth", {}).get("enabled", True))

    class H(BaseHTTPRequestHandler):
        server_version = "ecualm"

        # ---------------- auth helpers ----------------
        def _token(self) -> str:
            c = http.cookies.SimpleCookie()
            try:
                c.load(self.headers.get("Cookie", ""))
            except http.cookies.CookieError:
                return ""
            return c[COOKIE].value if COOKIE in c else ""

        def _who(self) -> tuple[dict | None, str]:
            """(user, how) — how is 'cookie', 'token' or 'open' (auth disabled)."""
            if not auth_on:
                name = self.headers.get("X-User", "web")
                return {"username": name, "name": name, "role": "admin"}, "open"
            a = self.headers.get("Authorization", "")
            if a.lower().startswith("bearer "):
                return auth.token_user(a[7:].strip()), "token"
            return auth.session_user(self._token()), "cookie"

        def _cookie(self, token: str, max_age: int) -> dict:
            return {"Set-Cookie": f"{COOKIE}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={max_age}"}

        def _auth_post(self, path: str, b: dict, user):
            addr = self.client_address[0]
            if path == "/api/auth/login":
                token, u = auth.login(b.get("username", ""), b.get("password", ""), addr)
                return self._sent(200, {"user": _pub(u)}, headers=self._cookie(token, int(auth.session_hours * 3600)))
            if path == "/api/auth/setup":
                if auth.count():
                    raise AuthError("이미 사용자가 있습니다. 관리자에게 계정을 요청하세요", 409)
                if not is_loopback(addr):
                    raise AuthError("첫 관리자 계정은 서버 PC(localhost)에서만 만들 수 있습니다", 403)
                auth.create_user(b.get("username", ""), b.get("password", ""), b.get("name", ""), "admin")
                token, u = auth.login(b.get("username", ""), b.get("password", ""), addr)
                return self._sent(200, {"user": _pub(u)}, headers=self._cookie(token, int(auth.session_hours * 3600)))
            if path == "/api/auth/logout":
                auth.logout(self._token())
                return self._sent(200, {"ok": True}, headers=self._cookie("", 0))
            if path == "/api/auth/password":
                auth.set_password(user["username"], b.get("new", ""), b.get("old", ""))
                return self._sent(200, {"ok": True})
            if path == "/api/users":
                u = auth.create_user(b.get("username", ""), b.get("password", ""), b.get("name", ""), b.get("role", "engineer"),
                                     must_change=bool(b.get("must_change", True)))
                return self._sent(200, u)
            if path == "/api/users/update":
                return self._sent(200, auth.update_user(b["username"], b.get("name"), b.get("role"), b.get("disabled"), user["username"]))
            if path == "/api/users/reset":
                auth.set_password(b["username"], b.get("password", ""), must_change=True)
                return self._sent(200, {"ok": True})
            if path == "/api/users/token":
                return self._sent(200, {"token": auth.create_token(b["username"], b.get("label", ""))})
            return None

        def log_message(self, fmt, *args):
            pass

        @property
        def cfg(self):
            return load_config(root)

        def _send(self, code: int, body, ctype="application/json; charset=utf-8", headers=None):
            data = body if isinstance(body, (bytes, bytearray)) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            if "Cache-Control" not in (headers or {}):
                self.send_header("Cache-Control", "no-store")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _sent(self, *a, **k) -> bool:
            self._send(*a, **k)
            return True

        def _json_body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            try:
                p = urllib.parse.urlparse(self.path)
                path = p.path
                if path in ("/", "/index.html"):
                    return self._send(200, (WEB / "index.html").read_bytes(), "text/html; charset=utf-8")
                user, _how = self._who()
                if path == "/api/auth/state":
                    return self._send(200, {"enabled": auth_on, "setup": auth_on and auth.count() == 0,
                                            "can_setup": is_loopback(self.client_address[0]), "user": _pub(user),
                                            "roles": [{"id": r, "label": ROLE_LABEL[r]} for r in ROLES]})
                if not user:
                    return self._send(401, {"error": "로그인이 필요합니다", "login": True})
                if path == "/api/users":
                    if rank(user["role"]) < rank("admin"):
                        return self._send(403, {"error": "관리자 권한이 필요합니다"})
                    return self._send(200, {"users": auth.users(), "log": auth.log(60)})
                if path == "/api/plan":
                    with LOCK:
                        from .stages import stage_counts
                        return self._send(200, schedule.computed(repo, self.cfg, stage_counts(repo, self.cfg)))
                if path == "/api/plan/history":
                    t = urllib.parse.parse_qs(p.query).get("task", [None])[0]
                    return self._send(200, {"history": schedule.history(repo, t)})
                if path == "/api/plan/xlsx":
                    from .stages import stage_counts
                    with LOCK, tempfile.TemporaryDirectory() as td:
                        out = schedule.export_xlsx(repo, self.cfg, Path(td) / "plan.xlsx", stage_counts(repo, self.cfg))
                        return self._send(200, out.read_bytes(),
                                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                          {"Content-Disposition": "attachment; filename=project_plan_MAN3.xlsx"})
                if path.startswith("/api/source/"):
                    qs = urllib.parse.parse_qs(p.query)
                    parts = path[len("/api/source/"):].split("/")
                    with LOCK:
                        if parts[0] == "list":
                            return self._send(200, {"sources": sources.sources_for(repo, qs.get("doc", [""])[0])})
                        iid = parts[0]
                        what = parts[1] if len(parts) > 1 else "meta"
                        if what == "meta":
                            return self._send(200, sources.meta(repo, iid))
                        if what == "locs":
                            return self._send(200, sources.locate(repo, iid))
                        if what == "html":
                            return self._send(200, sources.html(repo, iid))
                        if what == "page" and len(parts) > 2:
                            return self._send(200, sources.page_png(repo, iid, int(parts[2]), int(qs.get("dpi", ["110"])[0])),
                                              "image/png", {"Cache-Control": "private, max-age=86400"})
                        if what == "file":
                            f = sources.source_file(repo, iid)
                            if not f:
                                return self._send(404, {"error": "원문 없음"})
                            return self._send(200, f.read_bytes(), "application/octet-stream",
                                              {"Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(f.name)}"})
                    return self._send(404, {"error": "not found"})
                if path.startswith("/api/reqif/"):
                    qs = urllib.parse.parse_qs(p.query)
                    doc, stage = qs.get("doc", [""])[0], qs.get("stage", [""])[0]
                    with LOCK:
                        if path == "/api/reqif/info":
                            imp, src = reqif.reqif_source(repo, doc) if doc else (None, None)
                            out = {"doc": doc, "reqif": bool(src), "file": src.name if src else "",
                                   "rev": imp["rev"] if imp else ""}
                            if src:
                                out["reply"] = reqif.reply(repo, self.cfg, doc)[2]
                            return self._send(200, out)
                        if path in ("/api/reqif/reply", "/api/reqif/export"):
                            data, fn, rep = (reqif.reply(repo, self.cfg, doc) if path.endswith("reply")
                                             else reqif.export(repo, self.cfg, doc or None, stage or None))
                            ctype = "application/zip" if fn.endswith(".reqifz") else "application/xml"
                            return self._send(200, data, ctype, {
                                "Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(fn)}",
                                "X-ReqIF-Report": urllib.parse.quote(json.dumps(rep, ensure_ascii=False))})
                    return self._send(404, {"error": "not found"})
                if path == "/api/changes" or path.startswith("/api/changes/"):
                    with LOCK:
                        if path == "/api/changes":
                            return self._send(200, {"reports": changes.reports(repo)})
                        rid = path[len("/api/changes/"):]
                        if rid.endswith("/xlsx"):
                            with tempfile.TemporaryDirectory() as td:
                                out = changes.export_xlsx(changes.report(repo, rid[:-5]), Path(td) / "c.xlsx")
                                return self._send(200, out.read_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                                  {"Content-Disposition": f"attachment; filename=change_analysis_{rid[:-5]}.xlsx"})
                        return self._send(200, changes.report(repo, rid))
                if path.startswith("/api/sup") or path in ("/api/baseline/diff", "/api/backup"):
                    qs = urllib.parse.parse_qs(p.query)
                    g = lambda k, d="": qs.get(k, [d])[0]
                    with LOCK:
                        if path == "/api/sup":
                            return self._send(200, sup.summary(repo, self.cfg))
                        if path == "/api/sup/impact":
                            return self._send(200, sup.impact(repo, self.cfg, [x for x in g("ids").split(",") if x]))
                        if path.startswith("/api/sup/item/"):
                            return self._send(200, {"records": sup.for_item(repo, urllib.parse.unquote(path[len("/api/sup/item/"):]))})
                        if path.startswith("/api/sup/export/"):
                            kind = path.rsplit("/", 1)[1]
                            with tempfile.TemporaryDirectory() as td:
                                out = sup.export_xlsx(repo, self.cfg, kind, Path(td) / "x.xlsx")
                                return self._send(200, out.read_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                                  {"Content-Disposition": f"attachment; filename={kind}_records.xlsx"})
                        if path == "/api/baseline/diff":
                            return self._send(200, sup.baseline_diff(repo, g("a"), g("b") or None))
                        if path == "/api/backup":
                            if rank(user["role"]) < rank("admin"):
                                return self._send(403, {"error": "백업은 관리자만 받을 수 있습니다"})
                            with tempfile.TemporaryDirectory() as td:
                                out = sup.backup(repo, Path(td) / "b.zip")
                                return self._send(200, out.read_bytes(), "application/zip",
                                                  {"Content-Disposition": f"attachment; filename=ecualm_backup_{time.strftime('%Y%m%d_%H%M')}.zip"})
                        if path.startswith("/api/sup/"):
                            rid = urllib.parse.unquote(path[len("/api/sup/"):])
                            if rid.endswith("/8d"):
                                with tempfile.TemporaryDirectory() as td:
                                    out = sup.export_8d(repo, self.cfg, rid[:-3], Path(td) / "8d.docx")
                                    return self._send(200, out.read_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                                      {"Content-Disposition": f"attachment; filename={rid[:-3]}_8D.docx"})
                            return self._send(200, sup.detail(repo, self.cfg, rid))
                if path.startswith("/api/tests/") or path.startswith("/api/evidence/"):
                    qs = urllib.parse.parse_qs(p.query)
                    with LOCK:
                        if path == "/api/tests/dashboard":
                            return self._send(200, testruns.dashboard(repo, self.cfg))
                        if path == "/api/tests/sessions":
                            return self._send(200, {"sessions": testruns.sessions(repo, self.cfg)})
                        if path == "/api/tests/candidates":
                            g = lambda k, d="": qs.get(k, [d])[0]
                            return self._send(200, {"candidates": testruns.candidates(repo, self.cfg, g("stage"), g("domain"), g("only", "all"), g("q"))})
                        if path.startswith("/api/tests/session/"):
                            sid = urllib.parse.unquote(path[len("/api/tests/session/"):])
                            if sid.endswith("/xlsx"):
                                sid = sid[:-5]
                                with tempfile.TemporaryDirectory() as td:
                                    out = testruns.export_xlsx(repo, self.cfg, sid, Path(td) / "r.xlsx")
                                    return self._send(200, out.read_bytes(),
                                                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                                      {"Content-Disposition": f"attachment; filename={sid}_test_report.xlsx"})
                            return self._send(200, testruns.session(repo, self.cfg, sid))
                        if path.startswith("/api/evidence/"):
                            meta, data = testruns.get_evidence(repo, int(path.rsplit("/", 1)[1]))
                            inline = meta["mime"] in testruns.INLINE_MIME and "dl" not in qs
                            fn = urllib.parse.quote(meta["filename"])
                            ctype = meta["mime"] + ("; charset=utf-8" if meta["mime"].startswith("text/") else "")
                            return self._send(200, data, ctype if inline else "application/octet-stream",
                                              {"Content-Disposition": f"{'inline' if inline else 'attachment'}; filename*=UTF-8''{fn}",
                                               "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"})
                    return self._send(404, {"error": "not found"})
                if path.startswith("/api/table/"):
                    sid = path[len("/api/table/"):]
                    if sid.endswith("/xlsx"):
                        sid = sid[:-5]
                        with LOCK, tempfile.TemporaryDirectory() as td:
                            out = workproducts.export_xlsx(repo, self.cfg, sid, Path(td) / f"{sid}.xlsx")
                            return self._send(200, out.read_bytes(),
                                              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                              {"Content-Disposition": f"attachment; filename={sid}_table.xlsx"})
                    with LOCK:
                        return self._send(200, workproducts.table(repo, self.cfg, sid))
                if path.startswith("/assets/"):
                    f = (repo.assets / Path(path[8:]).name)
                    if f.exists():
                        return self._send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")
                    return self._send(404, {"error": "not found"})
                if path == "/api/state":
                    with LOCK:
                        st = state_payload(repo, self.cfg)
                    st["me"] = _pub(user); st["auth"] = auth_on
                    return self._send(200, st)
                if path.startswith("/api/item/"):
                    iid = urllib.parse.unquote(path[len("/api/item/"):])
                    it = repo.get(iid)
                    if not it:
                        return self._send(404, {"error": "not found"})
                    return self._send(200, {"item": it, "history": repo.history(iid), "links": repo.links(iid)})
                if path.startswith("/api/stagedoc/"):
                    sid = path[len("/api/stagedoc/"):].split("?")[0]
                    mode = urllib.parse.parse_qs(p.query).get("mode", ["pam"])[0]
                    with LOCK:
                        return self._send(200, stage_doc(repo, self.cfg, sid, mode))
                if path.startswith("/api/export/docx/"):
                    sid = path[len("/api/export/docx/"):]
                    mode = urllib.parse.parse_qs(p.query).get("mode", ["pam"])[0]
                    from .export import export_stage_docx
                    with LOCK, tempfile.TemporaryDirectory() as td:
                        out = export_stage_docx(repo, self.cfg, sid, Path(td) / f"{sid}.docx", mode)
                        return self._send(200, out.read_bytes(),
                                          "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                          {"Content-Disposition": f"attachment; filename={sid}_PAM40.docx"})
                if path.startswith("/api/artifact/"):
                    iid = urllib.parse.unquote(path[len("/api/artifact/"):])
                    with LOCK:
                        return self._send(200, arch.artifact_json(repo, self.cfg, iid))
                if path.startswith("/api/arch/"):
                    sid = path[len("/api/arch/"):]
                    with LOCK:
                        data = json.dumps(arch.export_arch(repo, self.cfg, sid), ensure_ascii=False, indent=2).encode()
                    return self._send(200, data, "application/json; charset=utf-8",
                                      {"Content-Disposition": f"attachment; filename={sid}_architecture.json"})
                if path == "/api/ai/status":
                    return self._send(200, assistant.status(self.cfg))
                if path == "/api/audit":
                    with LOCK:
                        return self._send(200, run_audit(repo, self.cfg))
                if path == "/api/export/xlsx":
                    with LOCK, tempfile.TemporaryDirectory() as td:
                        out = export_excel(repo, self.cfg, Path(td) / "alm_export.xlsx")
                        return self._send(200, out.read_bytes(),
                                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                          {"Content-Disposition": "attachment; filename=alm_export.xlsx"})
                return self._send(404, {"error": "not found"})
            except KeyError as e:
                return self._send(404, {"error": str(e).strip("'")})
            except ValueError as e:
                return self._send(400, {"error": str(e)})
            except Exception as e:
                traceback.print_exc()
                return self._send(500, {"error": str(e)})

        def do_POST(self):
            try:
                path = urllib.parse.urlparse(self.path).path
                cfg = self.cfg
                who, how = (None, "") if path in PUBLIC_POST else self._who()
                if path not in PUBLIC_POST:
                    if not who:
                        return self._send(401, {"error": "로그인이 필요합니다", "login": True})
                    if how == "cookie" and self.headers.get("X-ECUALM") != "1":
                        return self._send(403, {"error": "잘못된 요청 출처"})
                    need = POST_ROLE.get(path, "engineer")
                    if rank(who["role"]) < rank(need):
                        return self._send(403, {"error": f"권한이 없습니다 ({ROLE_LABEL[need]} 이상 필요)"})
                    if who.get("must_change") and path not in ("/api/auth/password", "/api/auth/logout"):
                        return self._send(403, {"error": "임시 비밀번호입니다. 먼저 비밀번호를 바꾸세요", "must_change": True})
                user = who["username"] if who else ""
                if path.startswith("/api/auth/") or path.startswith("/api/users"):
                    r = self._auth_post(path, self._json_body(), who)
                    return r if r is not None else self._send(404, {"error": "not found"})
                if path.startswith("/api/plan/"):
                    b = self._json_body()
                    with LOCK:
                        if path == "/api/plan/task":
                            return self._send(200, schedule.save_task(repo, b, who))
                        if path == "/api/plan/task/delete":
                            return self._send(200, schedule.delete_task(repo, b["id"], who))
                        if path == "/api/plan/baseline":
                            return self._send(200, schedule.set_baseline(repo, b.get("name", ""), b.get("note", ""), who))
                        if path == "/api/plan/template":
                            return self._send(200, schedule.template(repo, b.get("start", ""), who, bool(b.get("replace"))))
                        if path == "/api/plan/meta":
                            return self._send(200, schedule.set_meta(repo, b, user))
                    return self._send(404, {"error": "not found"})
                if path == "/api/changes/analyze":     # local analysis under the lock, the slow AI part outside it
                    b = self._json_body()
                    with LOCK:
                        rep = changes.analyze_local(repo, cfg, b.get("summary") or {})
                    rep = changes.enrich(cfg, rep, bool(b.get("ai", True)))
                    if b.get("save") and not rep.get("dry_run"):
                        with LOCK:
                            changes.save(repo, rep, user)
                    return self._send(200, rep)
                if path == "/api/changes/cr":
                    b = self._json_body()
                    with LOCK:
                        return self._send(200, changes.to_cr(repo, cfg, b["import_id"], b.get("ids") or [], who, b.get("title", "")))
                if path == "/api/chat":     # read-only and possibly slow (LLM): do not hold the write lock
                    b = self._json_body()
                    return self._send(200, assistant.chat(repo, cfg, b.get("messages", []), b.get("context") or {}))
                if path == "/api/ai/settings":
                    return self._send(200, _save_ai_settings(root, self._json_body()))
                with LOCK:
                    if path.startswith("/api/source/") and path.endswith("/attach"):
                        n = int(self.headers.get("Content-Length") or 0)
                        if n > 80 * 1024 * 1024:
                            return self._send(413, {"error": "파일이 너무 큽니다"})
                        return self._send(200, sources.attach(repo, path.split("/")[3], urllib.parse.unquote(self.headers.get("X-Filename", "")),
                                                              self.rfile.read(n)))
                    if path == "/api/evidence":
                        n = int(self.headers.get("Content-Length") or 0)
                        if n > testruns.MAX_EVIDENCE:
                            return self._send(413, {"error": "파일은 50MB 이하만 올릴 수 있습니다"})
                        data = self.rfile.read(n)
                        h = lambda k: urllib.parse.unquote(self.headers.get(k, ""))
                        return self._send(200, testruns.add_evidence(repo, h("X-Session"), h("X-Case"), h("X-Filename"), data, h("X-Note"), who))
                    if path == "/api/import":
                        name = urllib.parse.unquote(self.headers.get("X-Filename", "upload.docx"))
                        n = int(self.headers.get("Content-Length") or 0)
                        data = self.rfile.read(n)
                        upl = repo.dir / "uploads"
                        upl.mkdir(exist_ok=True)
                        f = upl / Path(name).name
                        f.write_bytes(data)
                        res = import_document(repo, cfg, f, doc=urllib.parse.unquote(self.headers.get("X-Doc", "")) or None,
                                              rev=urllib.parse.unquote(self.headers.get("X-Rev", "")),
                                              mode=self.headers.get("X-Mode", "srs"),
                                              dry_run=self.headers.get("X-Dry-Run") == "1", user=user)
                        return self._send(200, res)
                    b = self._json_body()
                    if path.startswith("/api/item/") and path.endswith("/reclassify"):
                        iid = urllib.parse.unquote(path[len("/api/item/"):-len("/reclassify")])
                        return self._send(200, ops.reclassify(repo, cfg, iid, b["type"], b.get("domain"), user))
                    if path.startswith("/api/item/"):
                        iid = urllib.parse.unquote(path[len("/api/item/"):])
                        return self._send(200, ops.edit_item(repo, cfg, iid, b.get("text"), b.get("status"),
                                                             b.get("custom"), user, b.get("attrs")))
                    if path == "/api/item":
                        return self._send(200, ops.create_item(repo, cfg, b["type"], b["text"], b.get("domain"),
                                                               b.get("doc", ""), b.get("section", ""), b.get("after"),
                                                               user=user))
                    if path == "/api/link":
                        ops.link(repo, cfg, b["src"], b["role"], b["dst"])
                        return self._send(200, {"ok": True})
                    if path == "/api/link/delete":
                        n = repo.remove_link(b["src"], b["role"], b["dst"]); repo.commit()
                        return self._send(200, {"removed": n})
                    if path == "/api/link/clear-suspect":
                        n = repo.clear_suspect(b.get("src"), b.get("dst")); repo.commit()
                        return self._send(200, {"cleared": n})
                    if path == "/api/suggest":
                        return self._send(200, suggest_links(repo, cfg, b["src_type"], b["dst_type"],
                                                             float(b.get("min", 0.2)), int(b.get("top", 2))))
                    if path == "/api/derive":
                        return self._send(200, derive(repo, cfg, b["from"], b["to"], b.get("ids"), user))
                    if path.startswith("/api/sup/"):
                        a = path[len("/api/sup/"):]
                        if a == "create":
                            return self._send(200, sup.create(repo, cfg, b.get("kind", ""), b, who))
                        if a == "update":
                            return self._send(200, sup.update(repo, cfg, b["id"], b, who))
                        if a == "transition":
                            return self._send(200, sup.transition(repo, cfg, b["id"], b["to"], b.get("comment", ""), who))
                        if a == "comment":
                            return self._send(200, sup.comment(repo, cfg, b["id"], b.get("text", ""), who))
                        if a == "escalate":
                            return self._send(200, sup.escalate(repo, cfg, b["id"], b.get("to", ""), b.get("comment", ""), who))
                        if a == "impact/save":
                            return self._send(200, sup.save_impact(repo, cfg, b["id"], who))
                        if a == "qa/evaluate":
                            return self._send(200, sup.evaluate_checklist(repo, cfg, b["id"], who))
                        if a == "qa/check":
                            return self._send(200, sup.set_check(repo, cfg, b["id"], int(b["idx"]), b.get("result", ""), b.get("comment", ""), who))
                        if a == "qa/findings":
                            return self._send(200, sup.findings_from_checklist(repo, cfg, b["id"], who))
                        if a == "from-test":
                            return self._send(200, sup.problem_from_test(repo, cfg, b["session"], b["tc"], who, b))
                        if a == "cr-from-pr":
                            return self._send(200, sup.cr_from_problem(repo, cfg, b["id"], who))
                        return self._send(404, {"error": "not found"})
                    if path == "/api/tests/session":
                        return self._send(200, testruns.create_session(repo, cfg, b, who))
                    if path == "/api/tests/session/update":
                        return self._send(200, testruns.update_session(repo, cfg, b["id"], b, who))
                    if path == "/api/tests/record":
                        return self._send(200, testruns.record(repo, cfg, b["session"], b, who))
                    if path == "/api/evidence/delete":
                        return self._send(200, testruns.delete_evidence(repo, int(b["id"]), who))
                    if path == "/api/table/cell":
                        return self._send(200, workproducts.set_cell(repo, cfg, b["id"], b["key"], b.get("value"), user))
                    if path == "/api/wpcol":
                        return self._send(200, workproducts.add_column(repo, cfg, b["stage"], b.get("label", ""), b.get("type", "text"),
                                                                       b.get("options"), b.get("required", False), b.get("help", ""), user))
                    if path == "/api/wpcol/update":
                        return self._send(200, workproducts.update_column(repo, b["stage"], b["key"], b.get("label"), b.get("required"),
                                                                          b.get("options"), b.get("help")))
                    if path == "/api/wpcol/delete":
                        return self._send(200, workproducts.delete_column(repo, b["stage"], b["key"]))
                    if path == "/api/layout":
                        return self._send(200, {"moved": arch.set_layout(repo, b["positions"])})
                    if path == "/api/block":
                        return self._send(200, arch.create_block(repo, cfg, b["canvas"], b["title"], b.get("text", ""),
                                                                 b.get("domain", "GEN"), b.get("x", 40), b.get("y", 40), user=user))
                    if path == "/api/interface":
                        return self._send(200, arch.create_interface(repo, cfg, b["canvas"], b["from"], b["to"], b.get("name", ""),
                                                                     b.get("signal_class", "digital"), b.get("signals"), user=user))
                    if path == "/api/results":
                        return self._send(200, arch.ingest_results(repo, cfg, b, user=user or "ci"))
                    if path == "/api/arch/import":
                        return self._send(200, arch.import_arch(repo, cfg, b, user=user))
                    if path == "/api/sample/hw":
                        return self._send(200, arch.load_sample(repo, cfg, user=user))
                    if path == "/api/baseline":
                        return self._send(200, repo.create_baseline(b["name"], b.get("note", "")))
                return self._send(404, {"error": "not found"})
            except AuthError as e:
                return self._send(e.code, {"error": str(e)})
            except PermissionError as e:
                return self._send(403, {"error": str(e)})
            except (KeyError, ValueError, json.JSONDecodeError) as e:
                return self._send(400, {"error": str(e)})
            except Exception as e:
                traceback.print_exc()
                return self._send(500, {"error": str(e)})

    return H


def _save_ai_settings(root: Path, b: dict) -> dict:
    """Provider / model / URL go to alm.json; the API key only to .alm/secrets.json (local, git-ignored)."""
    from .config import write_default_config
    from .llm import SECRETS
    p = write_default_config(root)
    data = json.loads(p.read_text(encoding="utf-8"))
    llm = data.setdefault("llm", {})
    prov = b.get("provider", llm.get("provider", "none"))
    if prov not in ("none", "anthropic", "openai_compatible"):
        raise ValueError("provider 는 none | anthropic | openai_compatible")
    llm["provider"] = prov
    for k in ("model", "base_url"):
        if k in b:
            llm[k] = str(b[k]).strip()
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    sec = root / SECRETS
    if b.get("clear_key") and sec.exists():
        sec.unlink()
    elif b.get("api_key"):
        sec.parent.mkdir(parents=True, exist_ok=True)
        sec.write_text(json.dumps({"api_key": str(b["api_key"]).strip()}), encoding="utf-8")
    return assistant.status(load_config(root))


class _Server(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR lets a second process bind the same port silently, so an old server
    # keeps answering after a "restart". Refuse instead, so a stale server is noticed.
    allow_reuse_address = sys.platform != "win32"


def serve(root: Path, host: str = "127.0.0.1", port: int = 8765):
    try:
        httpd = _Server((host, port), make_handler(Path(root)))
    except OSError as e:
        raise SystemExit(f"포트 {port} 를 열 수 없습니다 ({e}). 이미 ECU-ALM 서버가 떠 있으면 그 창을 닫거나 --port 로 다른 포트를 쓰세요.")
    print(f"ECU-ALM web UI: http://{host}:{port}  (Ctrl+C 로 종료)")
    cfg = load_config(Path(root))
    if cfg.get("auth", {}).get("enabled", True):
        if not Auth(Repo(Path(root)), cfg).count():
            print("  로그인: 아직 계정이 없습니다. 이 PC의 브라우저에서 열어 첫 관리자 계정을 만드세요 (또는 ecualm user add).")
    else:
        print("  로그인: 꺼짐 (alm.json auth.enabled=false)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
