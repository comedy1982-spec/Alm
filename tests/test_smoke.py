"""End-to-end smoke test:  python -m pytest tests  (or python tests/test_smoke.py)"""
from pathlib import Path
import tempfile

from ecualm import ops
from ecualm.audit import run_audit
from ecualm.config import load_config, write_default_config
from ecualm.db import Repo
from ecualm.importer import import_document

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def test_revision_flow():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        write_default_config(root)
        repo, cfg = Repo(root), load_config(root)

        a = import_document(repo, cfg, SAMPLES / "SRS_BLDC_revA.docx", doc="SRS", rev="A")
        assert a["by_type"]["SYS2"] == 7 and a["by_type"]["HSI"] == 5 and a["by_type"]["FIG"] == 2

        timeout_req = next(i for i in repo.items(type_="SWE1") if i["attrs"].get("native_id") == "REQ-COM-002")
        tc = ops.create_item(repo, cfg, "SWE6_TC", "300ms 경과 후 Timeout 판정 확인", domain="COM", doc="SRS")
        ops.link(repo, cfg, tc["id"], "verifies", timeout_req["id"])
        ops.edit_item(repo, cfg, timeout_req["id"], status="approved")

        b = import_document(repo, cfg, SAMPLES / "SRS_BLDC_revB.docx", doc="SRS", rev="B")
        assert timeout_req["id"] in b["modified"]            # same ID kept, change detected
        assert len(b["new"]) == 1 and len(b["deleted"]) == 1
        assert repo.get(tc["id"])["status"] != "deleted"     # manual items survive re-import
        it = repo.get(timeout_req["id"])
        assert it["status"] == "draft" and "500ms" in it["text"]

        res = run_audit(repo, cfg)
        rules = {(f["rule"], f["item"]) for f in res["findings"]}
        assert ("suspect", tc["id"]) in rules
        assert ("consistency", tc["id"]) in rules


def test_pdf_tables_and_figures():
    from ecualm.parse_pdf import parse_pdf
    blocks = parse_pdf(SAMPLES / "SRS_BLDC_revA.pdf")
    tables = [b for b in blocks if b.kind == "table"]
    figs = [b for b in blocks if b.kind == "figure"]
    assert len(tables) == 2 and len(figs) == 2
    pin = tables[1]
    assert len(pin.grid) == 6                               # table split across pages stitched
    assert pin.grid[1][3]["rs"] == 3                        # vertical merge preserved
    vec = [b for b in parse_pdf(SAMPLES / "vector_figure_example.pdf") if b.kind == "figure"]
    assert vec and vec[0].style == "vector" and vec[0].image




def test_stage_flow():
    from ecualm.stages import derive, stage_doc
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        write_default_config(root)
        repo, cfg = Repo(root), load_config(root)
        import_document(repo, cfg, SAMPLES / "SRS_BLDC_revA.docx", doc="CRS", rev="1.0", mode="crs")
        assert derive(repo, cfg, "SYS1", "SYS2")["created"]
        sd = stage_doc(repo, cfg, "SYS2")
        kinds = [s["kind"] for s in sd["sections"]]
        assert kinds == ["text", "text", "text", "group", "verification", "trace"]
        r = derive(repo, cfg, "SYS2", "SWE1")
        assert r["created"] and r["skipped"]              # HW-only requirements stay at SYS.2
        assert derive(repo, cfg, "SYS2", "SWE1")["created"] == []   # idempotent
        derive(repo, cfg, "SWE1", "SWE6"); derive(repo, cfg, "SWE1", "SWE2"); derive(repo, cfg, "SYS2", "SYS3")
        swe1 = repo.items(type_="SWE1")[0]
        assert "spec" in swe1["attrs"] and swe1["attrs"]["derived_from"].startswith("SYS2-")
        # a CRS revision must not delete derived items, and must mark derived links suspect
        b = import_document(repo, cfg, SAMPLES / "SRS_BLDC_revB.docx", doc="CRS", rev="1.1", mode="crs")
        assert all(not d.startswith(("SYS2", "SWE1", "SWE6")) for d in b["deleted"])
        res = run_audit(repo, cfg)
        assert any(f["rule"] == "suspect" and f["item"].startswith("SYS2") for f in res["findings"])
        assert not any(f["rule"] == "duplicate" for f in res["findings"])


def test_hwe_architecture_flow():
    """HW branch: SYS.2 → HWE.1 → HWE.2 blocks (+ canvas interfaces) → HWE.3/HWE.4, results and audit."""
    from ecualm import arch
    from ecualm.stages import derive
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        write_default_config(root)
        repo, cfg = Repo(root), load_config(root)
        import_document(repo, cfg, SAMPLES / "SRS_BLDC_revA.docx", doc="CRS", rev="1.0", mode="crs")
        derive(repo, cfg, "SYS1", "SYS2"); derive(repo, cfg, "SYS2", "SYS3")
        hw = derive(repo, cfg, "SYS2", "HWE1")
        assert hw["created"] and hw["skipped"]                      # SW-only requirements stay out of HWE.1
        assert all(not repo.get(i)["text"].lstrip().startswith("SW") for i in hw["created"])
        derive(repo, cfg, "SYS3", "HWE2"); derive(repo, cfg, "HWE1", "HWE2")
        blocks = repo.items(type_="HWE2")
        assert blocks and all("기구" not in b["title"] for b in blocks)
        assert derive(repo, cfg, "HWE2", "HWE3")["created"] and derive(repo, cfg, "HWE1", "HWE4")["created"]

        # moving a block is layout, not content: no new version, no suspect
        b0 = blocks[0]
        arch.set_layout(repo, {b0["id"]: {"x": 123, "y": 45}})
        assert repo.get(b0["id"])["version"] == b0["version"]
        assert repo.get(b0["id"])["attrs"]["canvas_layout"] == {"x": 123, "y": 45}

        # an interface line is an item that connects both blocks; a block change makes it suspect
        a, b = blocks[0], blocks[1]
        f = arch.create_interface(repo, cfg, "HWE2", a["id"], b["id"], "PWM x6", "pwm", "CH0, CH1")
        assert f["attrs"]["signals"] == ["CH0", "CH1"]
        assert {(l["role"], l["dst"]) for l in repo.links(f["id"]) if l["src"] == f["id"]} == {("connects", a["id"]), ("connects", b["id"])}

        # test result: PASS recorded with versions; editing the verified block makes the PASS stale
        tc_id = next(l["src"] for l in repo.links(a["id"]) if l["role"] == "verifies" and l["dst"] == a["id"])
        r = arch.ingest_results(repo, cfg, {"results": [{"tc": tc_id, "status": "pass", "run_id": "R1"}, {"tc": "NOPE", "status": "FAIL"}]})
        assert r["updated"] == [tc_id] and r["unknown"] == ["NOPE"]
        assert repo.get(tc_id)["version"] == 1 and repo.get(tc_id)["attrs"]["result"]["status"] == "PASS"
        ops.edit_item(repo, cfg, a["id"], attrs={"hw": {"part_number": "X1", "interfaces": "", "safety_mechanism": ""}})
        assert repo.get(a["id"])["title"] == a["title"]                 # a block keeps its name
        rules = {(x["rule"], x["item"]) for x in run_audit(repo, cfg)["findings"]}
        assert ("result_stale", tc_id) in rules
        arch.ingest_results(repo, cfg, [{"tc": tc_id, "status": "FAIL", "note": "over limit"}])
        assert ("test_fail", tc_id) in {(x["rule"], x["item"]) for x in run_audit(repo, cfg)["findings"]}

        # sample HW architecture merges into the derived blocks by name, and the canvas round-trips as JSON
        n_blocks = len(repo.items(type_="HWE2"))
        res = arch.load_sample(repo, cfg)
        assert res["interfaces"] == 10 and res["results"] == 3
        assert len(repo.items(type_="HWE2")) == n_blocks + len(res["created"])
        exp = arch.export_arch(repo, cfg, "HWE2")
        again = arch.import_arch(repo, cfg, exp)
        assert again["created"] == [] and again["interfaces"] == 0       # idempotent
        art = arch.artifact_json(repo, cfg, next(b["id"] for b in repo.items(type_="HWE2") if b["title"] == "과전류 하드웨어 차단 경로 (Shut-off Path)"))
        assert art["safety_classification"] == "B" and art["traceability"]["interfaces"]
        assert any(v["status"] == "PASS" for v in art["traceability"]["verified_by_downstream"])


def test_config_merge_adds_new_stages():
    """An alm.json written by an older version still gets the HWE stages and rules."""
    import json
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        old = {"project": "OLD", "stages": [{"id": "SYS2", "aspice": "SYS.2", "name": "SRS", "short": "SRS", "types": ["SYS2"],
                                             "next": ["SWE1"], "side": "spec"}],
               "link_rules": [{"src": "SWE1", "role": "refines", "dst": ["SYS2"]}]}
        (root / "alm.json").write_text(json.dumps(old), encoding="utf-8")
        cfg = load_config(root)
        ids = [s["id"] for s in cfg["stages"]]
        assert "HWE2" in ids and "HWE1" in next(s for s in cfg["stages"] if s["id"] == "SYS2")["next"]
        assert any(r["src"] == "HWE2" for r in cfg["link_rules"])


def test_assistant_local_and_llm(monkeypatch=None):
    """Chat panel back-end: offline commands work without a provider; with a provider the context carries
    the selected item and invalid action proposals are dropped."""
    from ecualm import assistant
    from ecualm.stages import derive
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        write_default_config(root)
        repo, cfg = Repo(root), load_config(root)
        import_document(repo, cfg, SAMPLES / "SRS_BLDC_revA.docx", doc="CRS", rev="1.0", mode="crs")
        derive(repo, cfg, "SYS1", "SYS2")
        assert assistant.status(cfg)["mode"] == "local"
        r = assistant.chat(repo, cfg, [{"role": "user", "content": "SYS.2 → SWE.1 전개"}])
        assert r["mode"] == "local" and r["actions"][0] == {"type": "derive", "from": "SYS2", "to": "SWE1", "label": "SYS2 → SWE1 전개"}
        sys2 = repo.items(type_="SYS2")[0]
        r = assistant.chat(repo, cfg, [{"role": "user", "content": f"{sys2['id']} 설명"}])
        assert sys2["id"] in r["reply"] and r["actions"][0]["type"] == "open"
        assert "감사 결과" in assistant.chat(repo, cfg, [{"role": "user", "content": "감사"}])["reply"]

        # LLM path with a stubbed transport
        cfg["llm"].update(provider="openai_compatible", base_url="http://stub", model="stub")
        seen = {}
        def fake(cfg_, system, messages, **kw):
            seen["ctx"] = messages[-1]["content"]
            return ('{"reply":"ok","actions":[{"type":"edit","id":"%s","text":"새 문장"},'
                    '{"type":"link","src":"NOPE","role":"refines","dst":"X"},{"type":"derive","from":"SYS2","to":"BAD"}]}' % sys2["id"])
        orig = assistant.chat_call
        assistant.chat_call = fake
        try:
            r = assistant.chat(repo, cfg, [{"role": "user", "content": "선택한 요구사항을 고쳐줘"}], {"selected": sys2["id"], "stage": "SYS2"})
        finally:
            assistant.chat_call = orig
        assert r["mode"] == "llm" and [a["type"] for a in r["actions"]] == ["edit"]
        assert f"[아이템 {sys2['id']}]" in seen["ctx"] and "SYS.2" in seen["ctx"]
        # a failing provider falls back to local answers instead of erroring
        def boom(*a, **k):
            raise RuntimeError("no network")
        assistant.chat_call = boom
        try:
            r = assistant.chat(repo, cfg, [{"role": "user", "content": "현황"}])
        finally:
            assistant.chat_call = orig
        assert r["mode"] == "local" and "AI 호출 실패" in r["reply"]


def _http(port, path, body=None, opener=None, csrf=True):
    import json, urllib.request, urllib.error
    h = {"content-type": "application/json"}
    if csrf:
        h["X-ECUALM"] = "1"
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", None if body is None else json.dumps(body).encode(), h)
    try:
        r = opener.open(req)
        return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_login_roles_and_plan():
    import http.cookiejar, threading, urllib.request
    from ecualm.server import _Server, make_handler
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        write_default_config(root)
        srv = _Server(("127.0.0.1", 0), make_handler(root)); port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        mk = lambda: urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        adm, eng, anon = mk(), mk(), mk()
        try:
            assert _http(port, "/api/state", opener=anon)[0] == 401
            assert _http(port, "/api/auth/state", opener=anon)[1]["setup"] is True
            assert _http(port, "/api/auth/setup", {"username": "pm", "password": "Passw0rd!"}, adm)[0] == 200
            assert _http(port, "/api/auth/setup", {"username": "x", "password": "Passw0rd!"}, anon)[0] == 409   # only once
            assert _http(port, "/api/state", opener=adm)[1]["me"]["role"] == "admin"
            assert _http(port, "/api/plan/template", {"start": "2026-11-02"}, adm, csrf=False)[0] == 403       # CSRF header required
            assert _http(port, "/api/plan/template", {"start": "2026-11-02"}, adm)[1]["created"] > 30
            plan = _http(port, "/api/plan", opener=adm)[1]
            t = next(x for x in plan["tasks"] if x["wbs"] == "4.1")
            assert not t["flags"], t["flags"]                       # template respects finish-to-start
            assert plan["metrics"]["bac"] > 0 and plan["load"]
            # engineer: temp password must be changed, then only own task progress/actuals
            assert _http(port, "/api/users", {"username": "kim", "password": "Temp12345", "role": "engineer"}, adm)[0] == 200
            assert _http(port, "/api/auth/login", {"username": "kim", "password": "nope"}, eng)[0] == 401
            assert _http(port, "/api/auth/login", {"username": "kim", "password": "Temp12345"}, eng)[1]["user"]["must_change"]
            assert _http(port, "/api/plan/task", {"id": t["id"], "progress": 10}, eng)[0] == 403
            assert _http(port, "/api/auth/password", {"old": "Temp12345", "new": "Kim-12345"}, eng)[0] == 200
            assert _http(port, "/api/plan/task", {"id": t["id"], "progress": 10}, eng)[0] == 403      # not the owner yet
            assert _http(port, "/api/plan/task", {"id": t["id"], "owner": "kim"}, adm)[0] == 200
            r = _http(port, "/api/plan/task", {"id": t["id"], "progress": 40, "effort_actual": 12}, eng)
            assert r[0] == 200 and r[1]["status"] == "in_progress"
            assert _http(port, "/api/plan/task", {"id": t["id"], "start": "2027-01-04"}, eng)[0] == 403   # dates are the PM's
            assert _http(port, "/api/baseline", {"name": "b"}, eng)[0] == 403
            # baseline then slip -> flags; cycle rejected
            assert _http(port, "/api/plan/baseline", {"name": "BL1"}, adm)[0] == 200
            nxt = next(x for x in plan["tasks"] if x["wbs"] == "4.2")
            import datetime as _dt
            later = (_dt.date.fromisoformat(t["finish"]) + _dt.timedelta(days=14)).isoformat()
            _http(port, "/api/plan/task", {"id": t["id"], "finish": later}, adm)
            t2 = next(x for x in _http(port, "/api/plan", opener=adm)[1]["tasks"] if x["id"] == t["id"])
            assert "slip" in t2["flags"] and t2["slip_days"] == 14
            assert "dep_conflict" in next(x for x in _http(port, "/api/plan", opener=adm)[1]["tasks"] if x["id"] == nxt["id"])["flags"]
            assert _http(port, "/api/plan/task", {"id": t["id"], "deps": [nxt["id"]]}, adm)[0] == 400
            x = adm.open(__import__("urllib.request").request.Request(f"http://127.0.0.1:{port}/api/plan/xlsx"))
            assert x.status == 200 and x.read(2) == b"PK"
            assert _http(port, "/api/auth/logout", {}, eng)[0] == 200 and _http(port, "/api/state", opener=eng)[0] == 401
        finally:
            srv.shutdown()
        from ecualm import schedule
        out = schedule.export_xlsx(Repo(root), load_config(root), root / "plan.xlsx")
        from openpyxl import load_workbook
        wb = load_workbook(out)
        assert wb.sheetnames == ["일정·공수 계획", "공수 부하", "계획 변경 이력"]
        assert wb["일정·공수 계획"]["A6"].value == "1"


if __name__ == "__main__":
    test_assistant_local_and_llm()
    test_revision_flow()
    test_pdf_tables_and_figures()
    test_stage_flow()
    test_hwe_architecture_flow()
    test_config_merge_adds_new_stages()
    test_login_roles_and_plan()
    print("OK")
