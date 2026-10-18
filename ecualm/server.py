"""Local web UI server (stdlib only). Run: ecualm serve --port 8765"""
from __future__ import annotations

import json
import mimetypes
import tempfile
import threading
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import ops
from .audit import run_audit, suggest_links
from .config import load_config
from .db import Repo
from .export import export_excel, state_payload
from .importer import import_document
from .stages import derive, stage_doc

WEB = Path(__file__).parent / "web"
LOCK = threading.Lock()


def make_handler(root: Path):
    repo = Repo(root)

    class H(BaseHTTPRequestHandler):
        server_version = "ecualm"

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
            self.send_header("Cache-Control", "no-store")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _json_body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            try:
                p = urllib.parse.urlparse(self.path)
                path = p.path
                if path in ("/", "/index.html"):
                    return self._send(200, (WEB / "index.html").read_bytes(), "text/html; charset=utf-8")
                if path.startswith("/assets/"):
                    f = (repo.assets / Path(path[8:]).name)
                    if f.exists():
                        return self._send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")
                    return self._send(404, {"error": "not found"})
                if path == "/api/state":
                    with LOCK:
                        return self._send(200, state_payload(repo, self.cfg))
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
            except Exception as e:
                traceback.print_exc()
                return self._send(500, {"error": str(e)})

        def do_POST(self):
            try:
                path = urllib.parse.urlparse(self.path).path
                cfg = self.cfg
                user = self.headers.get("X-User", "web")
                with LOCK:
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
                    if path == "/api/baseline":
                        return self._send(200, repo.create_baseline(b["name"], b.get("note", "")))
                return self._send(404, {"error": "not found"})
            except (KeyError, ValueError) as e:
                return self._send(400, {"error": str(e)})
            except Exception as e:
                traceback.print_exc()
                return self._send(500, {"error": str(e)})

    return H


def serve(root: Path, host: str = "127.0.0.1", port: int = 8765):
    httpd = ThreadingHTTPServer((host, port), make_handler(Path(root)))
    print(f"ECU-ALM web UI: http://{host}:{port}  (Ctrl+C 로 종료)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
