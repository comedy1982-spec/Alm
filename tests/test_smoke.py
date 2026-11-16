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


def test_work_product_tables():
    from ecualm import workproducts as W
    from ecualm.stages import derive
    with tempfile.TemporaryDirectory() as td:
        root = Path(td); write_default_config(root)
        cfg, repo = load_config(root), Repo(root)
        import_document(repo, cfg, SAMPLES / "CRS_eLSD_ECU_rev1.0.docx", doc="CRS", rev="1.0", mode="crs")
        derive(repo, cfg, "SYS1", "SYS2"); derive(repo, cfg, "SYS2", "SWE1")
        t = W.table(repo, cfg, "SYS2")
        keys = {c["key"] for c in t["columns"] if c["required"]}
        assert {"id", "text", "asil", "verification_criteria", "upstream", "tests", "status"} <= keys
        assert len(t["rows"]) > 150 and t["missing_by_column"]["tests"] == len(t["rows"])   # no SYS.5 yet
        carried = [r for r in t["rows"] if r["values"]["asil"]]
        assert carried, "ASIL from the CRS table rows should reach SYS.2"
        # custom column: add, fill (no Suspect downstream), required -> counted as missing
        col = W.add_column(repo, cfg, "SYS2", "릴리스", "enum", ["A", "B"], required=True, user="t")
        row = next(r for r in t["rows"] if r["values"]["downstream"])
        W.set_cell(repo, cfg, row["id"], col["key"], "B", "t")
        assert not any(l["suspect"] for l in repo.links() if l["dst"] == row["id"])
        try:
            W.set_cell(repo, cfg, row["id"], col["key"], "Z", "t"); assert False
        except ValueError:
            pass
        t2 = W.table(repo, cfg, "SYS2")
        assert t2["missing_by_column"][col["key"]] == len(t2["rows"]) - 1
        # requirement content change marks downstream Suspect; nested attr path works for SWE.1 spec
        W.set_cell(repo, cfg, row["id"], "asil", "C", "t")
        assert any(l["suspect"] for l in repo.links() if l["dst"] == row["id"])
        swe = W.table(repo, cfg, "SWE1")["rows"][0]
        W.set_cell(repo, cfg, swe["id"], "timing", "10 ms", "t")
        assert repo.get(swe["id"])["attrs"]["spec"]["timing"] == "10 ms"
        assert repo.get(swe["id"])["attrs"]["spec"].get("output") is not None    # sibling keys kept
        # audit: approved item with missing required columns -> warn
        ops.edit_item(repo, cfg, row["id"], status="approved", user="t")
        f = [x for x in run_audit(repo, cfg)["findings"] if x["rule"] == "wp_required" and x["item"] == row["id"]]
        assert f and f[0]["sev"] == "warn"
        out = W.export_xlsx(repo, cfg, "SYS2", root / "t.xlsx")
        from openpyxl import load_workbook
        assert load_workbook(out)["SYS2"]["A4"].value == "ID *"
        W.delete_column(repo, "SYS2", col["key"])
        assert col["key"] not in {c["key"] for c in W.table(repo, cfg, "SYS2")["columns"]}


def test_test_sessions_and_evidence():
    from ecualm import testruns as T
    from ecualm.stages import derive
    with tempfile.TemporaryDirectory() as td:
        root = Path(td); write_default_config(root)
        cfg, repo = load_config(root), Repo(root); T.init(repo)
        import_document(repo, cfg, SAMPLES / "CRS_eLSD_ECU_rev1.0.docx", doc="CRS", rev="1.0", mode="crs")
        derive(repo, cfg, "SYS1", "SYS2"); derive(repo, cfg, "SYS2", "SWE1"); derive(repo, cfg, "SWE1", "SWE6")
        eng = {"username": "kim", "name": "김", "role": "engineer"}
        pm = {"username": "pm", "name": "PM", "role": "manager"}
        s = T.create_session(repo, cfg, {"name": "r1", "stage": "SWE6", "q": "MOT", "build": "0.1"}, eng)
        tcs = [c["tc"] for c in s["cases"]]
        assert s["counts"]["total"] == len(tcs) > 5 and s["status"] == "planned"
        T.record(repo, cfg, s["id"], {"tc": tcs[0], "status": "PASS"}, eng)
        assert repo.get(tcs[0])["attrs"]["result"]["status"] == "PASS"                   # pushed to the TC
        assert T.session(repo, cfg, s["id"])["status"] == "in_progress"
        try:
            T.record(repo, cfg, s["id"], {"tc": tcs[1], "status": "FAIL"}, eng); assert False
        except ValueError:
            pass
        T.record(repo, cfg, s["id"], {"tc": tcs[1], "status": "FAIL", "actual": "150ms", "defect": "J-1"}, eng)
        T.record(repo, cfg, s["id"], {"tc": tcs[2], "status": "N_A"}, eng)
        e = T.add_evidence(repo, s["id"], tcs[1], "wave.png", b"\x89PNG data", "scope", eng)
        meta, data = T.get_evidence(repo, e["id"])
        assert data == b"\x89PNG data" and meta["sha256"] == __import__("hashlib").sha256(data).hexdigest()
        assert any(f["rule"] == "test_fail" and f["item"] == tcs[1] for f in run_audit(repo, cfg)["findings"])
        d = T.dashboard(repo, cfg)
        assert d["kpi"]["fail"] == 1 and d["open_failures"][0]["defect"] == "J-1"
        cov = next(c for c in d["coverage"] if c["stage"] == "SWE6")
        assert cov["failed"] >= 1 and cov["linked"] > 0
        # retest session picks the failed TC only
        r2 = T.candidates(repo, cfg, "SWE6", only="failed")
        assert [c["id"] for c in r2] == [tcs[1]]
        done = T.update_session(repo, cfg, s["id"], {"action": "complete"}, eng)
        assert done["verdict"] == "FAIL" and done["status"] == "completed"
        for bad in ({"tc": tcs[3], "status": "PASS"},):
            try:
                T.record(repo, cfg, s["id"], bad, eng); assert False
            except ValueError:
                pass
        try:
            T.delete_evidence(repo, e["id"], eng); assert False                  # completed -> locked
        except ValueError:
            pass
        try:
            T.update_session(repo, cfg, s["id"], {"action": "reopen"}, eng); assert False
        except PermissionError:
            pass
        assert T.update_session(repo, cfg, s["id"], {"action": "reopen"}, pm)["status"] == "in_progress"
        out = T.export_xlsx(repo, cfg, s["id"], root / "r.xlsx")
        from openpyxl import load_workbook
        wb = load_workbook(out)
        assert wb.sheetnames == ["요약", "TC 결과", "증빙"] and wb["증빙"]["D2"].value == e["sha256"]


def test_sup_processes():
    from ecualm import sup as U, testruns as T
    from ecualm.stages import derive
    with tempfile.TemporaryDirectory() as td:
        root = Path(td); write_default_config(root)
        cfg, repo = load_config(root), Repo(root); T.init(repo); U.init(repo)
        import_document(repo, cfg, SAMPLES / "CRS_eLSD_ECU_rev1.0.docx", doc="CRS", rev="1.0", mode="crs")
        derive(repo, cfg, "SYS1", "SYS2"); derive(repo, cfg, "SYS2", "SWE1"); derive(repo, cfg, "SWE1", "SWE6")
        eng = {"username": "kim", "name": "김", "role": "engineer"}
        eng2 = {"username": "lee", "name": "이", "role": "engineer"}
        pm = {"username": "pm", "name": "PM", "role": "manager"}
        s = T.create_session(repo, cfg, {"name": "r1", "stage": "SWE6", "q": "COM"}, eng)
        tc = s["cases"][0]["tc"]
        T.record(repo, cfg, s["id"], {"tc": tc, "status": "FAIL", "actual": "x"}, eng)
        # SUP.9: problem from failed test, guarded workflow
        p = U.problem_from_test(repo, cfg, s["id"], tc, eng)
        assert {x["role"] for x in p["items"]} == {"found_by", "verify", "affects"}
        assert T.session(repo, cfg, s["id"])["cases"][0]["defect"] == p["id"]
        U.transition(repo, cfg, p["id"], "analyzing", "", eng)
        try:
            U.transition(repo, cfg, p["id"], "resolving", "", eng); assert False
        except ValueError:
            pass
        U.update(repo, cfg, p["id"], {"fields": {"root_cause_cat": "코드", "root_cause": "rc", "corrective": "fix", "verification": "TS"}}, eng)
        U.transition(repo, cfg, p["id"], "resolving", "", eng)
        U.transition(repo, cfg, p["id"], "verifying", "", eng)
        try:
            U.transition(repo, cfg, p["id"], "closed", "", eng); assert False      # verify TC still FAIL
        except ValueError:
            pass
        # SUP.10: CR from the problem, impact analysis, CCB by manager only, close after retest PASS
        cr = U.cr_from_problem(repo, cfg, p["id"], eng)
        assert p["id"] in cr["refs"] and cr["id"] in U.get(repo, p["id"])["refs"]
        U.transition(repo, cfg, cr["id"], "analyzing", "", eng)
        try:
            U.transition(repo, cfg, cr["id"], "review", "", eng); assert False
        except ValueError:
            pass
        cr = U.save_impact(repo, cfg, cr["id"], eng)
        imp = cr["fields"]["impact"]
        assert imp["rows"][0]["action"] == "modify" and tc in imp["retest"]
        U.transition(repo, cfg, cr["id"], "review", "", eng)
        U.update(repo, cfg, cr["id"], {"fields": {"decision": "ok"}}, pm)
        try:
            U.transition(repo, cfg, cr["id"], "approved", "", eng); assert False
        except ValueError:
            pass
        U.transition(repo, cfg, cr["id"], "approved", "", pm)
        U.transition(repo, cfg, cr["id"], "implementing", "", eng); U.transition(repo, cfg, cr["id"], "verifying", "", eng)
        U.update(repo, cfg, cr["id"], {"fields": {"verification": "retest"}}, eng)
        s2 = T.create_session(repo, cfg, {"name": "retest", "stage": "SWE6", "tcs": imp["retest"]}, eng)
        for t in imp["retest"]:
            T.record(repo, cfg, s2["id"], {"tc": t, "status": "PASS"}, eng)
        U.transition(repo, cfg, cr["id"], "closed", "요구사항 문구 변경 없음 (코드 수정)", eng)
        U.transition(repo, cfg, p["id"], "closed", "", eng)
        # SUP.1: checklist auto evaluation, findings, independence of verification
        qa = U.create(repo, cfg, "QA", {"title": "SWE1", "fields": {"check_type": "산출물 점검", "target": "SWE1"}}, pm)
        qa = U.evaluate_checklist(repo, cfg, qa["id"], pm)
        assert any(c["result"] == "NOK" for c in qa["fields"]["checklist"])
        qf = U.findings_from_checklist(repo, cfg, qa["id"], pm)["created"][0]
        U.update(repo, cfg, qf, {"fields": {"corrective": "c"}}, eng); U.transition(repo, cfg, qf, "resolved", "", eng)
        try:
            U.transition(repo, cfg, qf, "verified", "", eng); assert False
        except ValueError:
            pass
        U.transition(repo, cfg, qf, "verified", "", pm)
        try:
            U.transition(repo, cfg, qa["id"], "done", "", pm); assert False     # summary + manual item missing
        except ValueError:
            pass
        # SUP.8: release checks, baseline, backup/restore
        rel = U.create(repo, cfg, "REL", {"title": "B", "fields": {"sw_version": "0.4.1", "git_commit": "abc", "sessions": s2["id"]}}, pm)
        assert {c["key"] for c in rel["checks"]} >= {"audit_errors", "open_cr", "commit"}
        rel = U.transition(repo, cfg, rel["id"], "released", "데모", pm)
        assert repo.baseline(rel["fields"]["item_baseline"]) is not None
        assert U.baseline_diff(repo, rel["fields"]["item_baseline"], None)["rows"] == []
        z = U.backup(repo, root / "b.zip")
        dst = root / "restored"
        U.restore(dst, z)
        assert Repo(dst).get(tc) is not None
        U.summary(repo, cfg)
        assert any(f["rule"] == "cr_without_impact" for f in U.audit_findings(repo, cfg)) is False


def test_revision_change_analysis():
    import json as _json
    from ecualm import changes as C, llm, sup as U
    from ecualm.stages import derive
    sys_path = SAMPLES / "CRS_eLSD_ECU_rev1.1.docx"
    if not sys_path.exists():
        import subprocess, sys
        subprocess.run([sys.executable, str(SAMPLES / "make_elsd_rev.py")], check=True, capture_output=True)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td); write_default_config(root)
        cfg, repo = load_config(root), Repo(root); U.init(repo)
        import_document(repo, cfg, SAMPLES / "CRS_eLSD_ECU_rev1.0.docx", doc="CRS", rev="1.0", mode="crs")
        derive(repo, cfg, "SYS1", "SYS2"); derive(repo, cfg, "SYS2", "SWE1"); derive(repo, cfg, "SWE1", "SWE6")
        prev = import_document(repo, cfg, sys_path, doc="CRS", rev="1.1", mode="crs", dry_run=True)
        rep = C.analyze(repo, cfg, prev)
        by = {r["native_id"]: r for r in rep["rows"] if r["native_id"]}
        assert by["REQ-CLU-001"]["numbers"][0]["direction"] == "stricter" and by["REQ-CLU-001"]["severity"] == "high"
        assert by["REQ-YAW-003"]["numbers"][0]["direction"] == "threshold"
        assert by["REQ-MODE-014"]["numbers"][0]["direction"] == "looser" and by["REQ-MODE-014"]["severity"] == "medium"
        assert "asil" in by["REQ-THERM-003"]["kinds"]                      # table ASIL column only
        assert "obligation" in by["REQ-LOCK-010"]["kinds"]                  # shall -> should (ID still in the doc)
        assert by["REQ-LOCK-012"]["kinds"] == ["removed"]
        assert "negation" in by["REQ-DIAG-003"]["kinds"] and "obligation" not in by["REQ-DIAG-003"]["kinds"]
        assert by["REQ-ENV-001"]["kinds"] == ["editorial"] and by["REQ-ENV-001"]["severity"] == "low"
        assert by["REQ-SEC-007"]["change"] == "new"
        assert rep["mode"] == "local" and rep["counts"]["retest"] > 0
        # LLM enrichment (stubbed): explanation merged, risk can only go up, failure keeps local report
        cfg["llm"].update(provider="openai_compatible", base_url="http://stub", model="stub")
        orig = llm.chat_call
        llm.chat_call = lambda *a, **k: _json.dumps({"summary": ["요약"], "questions": ["Q1"],
                                                     "items": {by["REQ-ENV-001"]["id"]: {"explain": "표현", "risk": "medium"}}})
        try:
            rep2 = C.analyze(repo, cfg, prev)
        finally:
            llm.chat_call = orig
        r2 = next(r for r in rep2["rows"] if r["native_id"] == "REQ-ENV-001")
        assert rep2["mode"] == "llm" and r2["ai"] == "표현" and r2["severity"] == "medium" and rep2["questions"] == ["Q1"]
        llm.chat_call = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down"))
        try:
            rep3 = C.analyze(repo, cfg, prev)
        finally:
            llm.chat_call = orig
        assert rep3["mode"] == "local" and "AI 호출 실패" in rep3["ai_status"]
        cfg["llm"]["provider"] = "none"
        # real import -> save report -> change request with impact
        real = import_document(repo, cfg, sys_path, doc="CRS", rev="1.1", mode="crs")
        rep = C.analyze(repo, cfg, real)
        C.save(repo, rep, "t")
        assert C.reports(repo)[0]["import_id"] == real["import_id"]
        pick = [r["id"] for r in rep["rows"] if r["severity"] == "high" and r["change"] == "modified"]
        cr = C.to_cr(repo, cfg, real["import_id"], pick, {"username": "t", "name": "t", "role": "engineer"})
        assert cr["fields"]["reason"] == "고객 요구 변경" and cr["fields"]["impact"]["scope"] == pick
        out = C.export_xlsx(rep, root / "c.xlsx")
        assert out.exists()


def test_source_side_by_side():
    from ecualm import sources as SR
    with tempfile.TemporaryDirectory() as td:
        root = Path(td); write_default_config(root)
        cfg, repo = load_config(root), Repo(root); SR.init(repo)
        a = import_document(repo, cfg, SAMPLES / "CRS_eLSD_ECU_rev1.0.pdf", doc="E", rev="1.0", mode="crs")
        b = import_document(repo, cfg, SAMPLES / "CRS_eLSD_ECU_rev1.1.pdf", doc="E", rev="1.1", mode="crs")
        assert SR.source_file(repo, a["import_id"]).name == "CRS_eLSD_ECU_rev1.0.pdf"      # each revision kept
        m = SR.meta(repo, b["import_id"])
        assert m["kind"] == "pdf" and len(m["pages"]) > 40
        La, Lb = SR.locate(repo, a["import_id"]), SR.locate(repo, b["import_id"])
        reqs = [i for i in Lb["items"] if i["type"] == "CRS"]
        assert sum(1 for i in reqs if i["id"] in Lb["locs"]) >= len(reqs) - 1
        clu = next(i for i in Lb["items"] if i["native_id"] == "REQ-CLU-001")
        old = next(i for i in La["items"] if i["id"] == clu["id"])
        assert "100ms" in clu["text"] and "120ms" in old["text"]                       # text as of each revision
        assert clu["change"] == "modified" and clu["id"] in La["locs"] and clu["id"] in Lb["locs"]
        assert not any(i["native_id"] == "REQ-LOCK-012" for i in Lb["items"])          # withdrawn in 1.1
        assert SR.page_png(repo, b["import_id"], 0)[:4] == b"\x89PNG"
        h = SR.html(repo, b["import_id"])
        assert "data-items" in h["html"]


def test_reqif_exchange():
    """ReqIF: DOORS-style import, revision compare by object ID, supplier reply into the customer's file, round trip."""
    import io, zipfile
    from ecualm import changes as C, reqif, sup as U
    from ecualm.stages import derive
    r10, r11 = SAMPLES / "CRS_eLSD_ECU_rev1.0.reqifz", SAMPLES / "CRS_eLSD_ECU_rev1.1.reqifz"
    if not r11.exists():
        import subprocess, sys
        subprocess.run([sys.executable, str(SAMPLES / "make_reqif_sample.py")], check=True, capture_output=True)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td); write_default_config(root)
        cfg, repo = load_config(root), Repo(root); U.init(repo)
        a = import_document(repo, cfg, r10, doc="CRS", rev="1.0", mode="crs")
        assert a["by_type"]["CRS"] == 186 and a["by_type"]["FIG"] == 12 and a["by_type"]["TBL"] > 50
        crs = repo.items(doc="CRS", type_="CRS")
        assert all(i["attrs"].get("reqif_id") and i["attrs"].get("native_id") for i in crs)
        therm = next(i for i in crs if i["attrs"]["native_id"] == "REQ-THERM-003")
        assert therm["attrs"]["asil"] == "B" and therm["attrs"]["reqif_supplier"] == {"Supplier Status": "Open"}
        derive(repo, cfg, "SYS1", "SYS2")

        prev = import_document(repo, cfg, r11, doc="CRS", rev="1.1", mode="crs", dry_run=True)
        by = {r["native_id"]: r for r in C.analyze(repo, cfg, prev)["rows"] if r["native_id"]}
        assert "obligation" in by["REQ-LOCK-010"]["kinds"] and by["REQ-LOCK-010"]["change"] == "modified"   # same object
        assert "asil" in by["REQ-THERM-003"]["kinds"] and by["REQ-LOCK-012"]["change"] == "deleted"
        assert by["REQ-SEC-007"]["change"] == "new" and by["REQ-ENV-001"]["kinds"] == ["editorial"]

        for it, v in zip(crs[:4], ["C (준수)", "PC (부분 준수)", "NC (미준수)", "검토중"]):
            ops.edit_item(repo, cfg, it["id"], attrs={**it["attrs"], "compliance": v, "comment": "의견 " + v[:2]}, suspect=False)
        data, name, rep = reqif.reply(repo, cfg, "CRS")
        assert name.endswith("_reply.reqifz") and rep["answered"] == 3 and rep["objects"] == 186 and not rep["warnings"]
        out = root / name; out.write_bytes(data)
        back = reqif.parse(out)
        assert set(back["objects"]) == set(reqif.parse(r10)["objects"])            # customer objects untouched
        st = {k: o["values"] for k, o in back["objects"].items()}
        nid = lambda i: crs[i]["attrs"]["reqif_id"]
        assert st[nid(0)]["Supplier Status"] == "Accepted" and st[nid(1)]["Supplier Status"] == "Partly accepted"
        assert st[nid(2)]["Supplier Status"] == "Not accepted" and st[nid(3)]["Supplier Status"] == "Open"
        assert st[nid(0)]["Supplier Comment"].startswith("의견") and "SYS2-" in st[nid(0)]["Supplier Reference"]
        assert len(zipfile.ZipFile(io.BytesIO(data)).namelist()) == 13                  # images kept

        g, gname, grep_ = reqif.export(repo, cfg, doc="CRS")
        assert gname == "CRS.reqifz" and grep_["objects"] == 350 and grep_["files"] == 12
        gp = root / gname; gp.write_bytes(g)
        root2 = root / "p2"; root2.mkdir(); write_default_config(root2)
        cfg2, repo2 = load_config(root2), Repo(root2)
        b = import_document(repo2, cfg2, gp, doc="CRS", rev="x", mode="crs")
        assert b["by_type"]["CRS"] == 186 and b["by_type"]["FIG"] == 12
        again = import_document(repo2, cfg2, gp, doc="CRS", rev="y", mode="crs", dry_run=True)
        assert not again["new"] and not again["modified"] and not again["deleted"]
        assert reqif.export(repo, cfg, stage="SYS2")[2]["objects"] == 186


def test_figures_tables_charts_linked():
    """Non-text content: native charts (data + SVG), equations, pictures in a requirement / table row, and
    requirement --refers--> figure/table links that turn Suspect when the figure or table changes."""
    from ecualm import changes as C, sup as U
    r1, r2 = SAMPLES / "CRS_media_demo_rev1.docx", SAMPLES / "CRS_media_demo_rev2.docx"
    if not r2.exists():
        import subprocess, sys
        subprocess.run([sys.executable, str(SAMPLES / "make_media_sample.py")], check=True, capture_output=True)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td); write_default_config(root)
        cfg, repo = load_config(root), Repo(root); U.init(repo)
        a = import_document(repo, cfg, r1, doc="M", rev="1", mode="crs")
        assert a["by_type"]["FIG"] == 4 and a["by_type"]["TBL"] == 1 and a["media_links"] == 4
        nat = {i["attrs"].get("native_id"): i for i in repo.items(doc="M") if i["type"] == "CRS"}
        assert "I_ref=T_req/K_t" in nat["REQ-TRQ-003"]["text"]                       # equation kept as text
        figs = {i["attrs"].get("caption", ""): i for i in repo.items(doc="M", type_="FIG")}
        chart = figs["그림 1 토크-속도 한계 곡선"]
        assert chart["attrs"]["render"] == "chart" and chart["attrs"]["file"].endswith(".svg")
        assert chart["attrs"]["chart"]["series"][0]["name"] == "최대 토크" and len(chart["attrs"]["grid"]) == 7
        refs = {(l["src"], l["dst"]) for l in repo.links() if l["role"] == "refers"}
        tbl = repo.items(doc="M", type_="TBL")[0]
        assert (nat["REQ-TRQ-001"]["id"], chart["id"]) in refs and (nat["REQ-TRQ-002"]["id"], tbl["id"]) in refs
        pic = next(l["dst"] for l in repo.links() if l["src"] == nat["REQ-TRQ-004"]["id"] and l["role"] == "refers")
        assert any(l["src"] == nat["REQ-IF-001"]["id"] for l in repo.links() if l["role"] == "refers")   # table-row picture

        b = import_document(repo, cfg, r2, doc="M", rev="2", mode="crs")
        assert not b["new"] and not b["deleted"] and pic in b["modified"]           # redrawn picture = same figure
        sus = {(l["src"], l["dst"]) for l in repo.links() if l["suspect"]}
        assert (nat["REQ-TRQ-001"]["id"], chart["id"]) in sus and (nat["REQ-TRQ-002"]["id"], tbl["id"]) in sus
        rows = {r["id"]: r for r in C.analyze(repo, cfg, b)["rows"]}
        assert rows[chart["id"]]["severity"] == "medium" and "최대 토크 @2000: 11.5 → 11" in rows[chart["id"]]["detail"]
        assert "90 ~ 110°C · 허용 토크 (%): 80 → 70" in rows[tbl["id"]]["detail"]
        assert "이미지 교체" in rows[pic]["detail"] and any("참조하는 요구사항" in x for x in rows[pic]["actions"])


def test_projects_and_sys1_shows_everything():
    """New projects in one server (own data, shared accounts) and SYS.1 listing the whole customer document."""
    import http.cookiejar, threading, urllib.request
    from ecualm.server import _Server, make_handler
    from ecualm.stages import stage_doc
    from ecualm import workproducts as W
    with tempfile.TemporaryDirectory() as td:
        root = Path(td); write_default_config(root)
        cfg, repo = load_config(root), Repo(root)
        W.init(repo)
        a = import_document(repo, cfg, SAMPLES / "CRS_media_demo_rev1.docx", doc="M", rev="1", mode="crs")
        sd = stage_doc(repo, cfg, "SYS1", "pam")
        body = next(s for s in sd["sections"] if s["kind"] == "group")
        shown = [i for x in body["sub"] for i in x["items"]]
        types = {i["type"] for i in shown}
        assert {"CRS", "INFO", "TBL", "FIG"} <= types and [x["title"] for x in body["sub"]][-3:] == ["토크 특성", "인터페이스", "시험 조건"]
        assert sum(1 for i in shown if i["type"] == "CRS") == a["by_type"]["CRS"] == sum(x["count"] for x in body["sub"])
        assert sum(1 for i in shown if i["type"] == "INFO") == a["by_type"]["INFO"] == sd["stats"]["content"]["info"]
        t = W.table(repo, cfg, "SYS1")
        assert t["info_rows"] == a["by_type"]["INFO"] and t["req_rows"] == a["by_type"]["CRS"]
        assert not any(r["missing"] for r in t["rows"] if r["type"] == "INFO")
        # an explanatory paragraph turned into a requirement stays one when the document comes again
        info = repo.items(doc="M", type_="INFO")[0]
        new = ops.reclassify(repo, cfg, info["id"], "CRS", user="t")
        b = import_document(repo, cfg, SAMPLES / "CRS_media_demo_rev1.docx", doc="M", rev="1b", mode="crs")
        assert not b["new"] and not b["deleted"] and repo.get(new["id"])["status"] != "deleted"
        assert repo.get(info["id"])["status"] == "deleted"
        # a document where nothing was recognised as a requirement is still listed in SYS.1
        note = root / "note.md"; note.write_text("# 개요\n\n이 문서는 배경을 설명한다고 적혀 있음\n", encoding="utf-8")
        import_document(repo, cfg, note, doc="NOTE", rev="1", mode="crs")
        assert "NOTE" in stage_doc(repo, cfg, "SYS1", "pam")["docs"]
        repo.con.close()

        srv = _Server(("127.0.0.1", 0), make_handler(root)); port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        mk = lambda: urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        adm, eng = mk(), mk()
        try:
            assert _http(port, "/api/auth/setup", {"username": "pm", "password": "Passw0rd!"}, adm)[0] == 200
            n0 = len(_http(port, "/api/state", opener=adm)[1]["items"])
            assert n0 > 10
            r = _http(port, "/api/projects/create", {"name": "eLSD 양산", "copy_settings": True}, adm)
            assert r[0] == 200 and r[1]["current"] == "eLSD_양산", r
            st = _http(port, "/api/state", opener=adm)[1]                     # switched by cookie
            assert st["project"] == "eLSD 양산" and st["project_id"] == "eLSD_양산" and not st["items"]
            assert st["me"]["role"] == "admin"                                # same account in every project
            assert (root / "projects" / "eLSD_양산" / ".alm" / "alm.db").exists()
            assert _http(port, "/api/projects/create", {"name": "eLSD 양산"}, adm)[0] == 400       # duplicate
            assert _http(port, "/api/projects/create", {"name": "x", "id": "../up"}, adm)[0] == 400
            ps = _http(port, "/api/projects", opener=adm)[1]
            assert [p["id"] for p in ps["projects"]] == ["default", "eLSD_양산"] and ps["projects"][0]["requirements"] >= 6
            assert _http(port, "/api/projects/switch", {"id": "nope"}, adm)[0] == 404
            assert _http(port, "/api/projects/switch", {"id": "default"}, adm)[0] == 200
            assert len(_http(port, "/api/state", opener=adm)[1]["items"]) == n0
            assert _http(port, "/api/users", {"username": "kim", "password": "Temp12345", "role": "engineer"}, adm)[0] == 200
            _http(port, "/api/auth/login", {"username": "kim", "password": "Temp12345"}, eng)
            _http(port, "/api/auth/password", {"old": "Temp12345", "new": "Kim-12345"}, eng)
            assert _http(port, "/api/projects/create", {"name": "no"}, eng)[0] == 403              # PM or admin only
            assert _http(port, "/api/projects/switch", {"id": "eLSD_양산"}, eng)[0] == 200
        finally:
            srv.shutdown(); srv.server_close()


def test_compliance_matrix():
    """Compliance matrix: status + comment per customer requirement, bulk set, Excel, ReqIF reply uses the same answers."""
    from ecualm import compliance as CM, reqif
    from openpyxl import load_workbook
    with tempfile.TemporaryDirectory() as td:
        root = Path(td); write_default_config(root)
        cfg, repo = load_config(root), Repo(root)
        import_document(repo, cfg, SAMPLES / "CRS_eLSD_ECU_rev1.0.reqifz", doc="CRS", rev="1.0", mode="crs")
        from ecualm.stages import derive
        derive(repo, cfg, "SYS1", "SYS2")
        m = CM.matrix(repo, cfg)
        assert m["summary"]["total"] == 186 and m["summary"]["open"] == 186 and len(m["statuses"]) == 9
        ids = [r["id"] for r in m["rows"]]
        assert CM.set_rows(repo, cfg, ids[:100], {"status": "Accept"}, "kim")["updated"] == 100          # bulk
        CM.set_rows(repo, cfg, [ids[100]], {"status": "Accept with Deviation"}, "kim")
        CM.set_rows(repo, cfg, [ids[101]], {"status": "Not Accept", "comment": "액추에이터 사양 한계"}, "kim")
        ops.edit_item(repo, cfg, ids[102], attrs={"compliance": "PC (부분 준수)", "deviation": "B 샘플부터"}, suspect=False)   # older value
        try:
            CM.set_rows(repo, cfg, [ids[0]], {"status": "Maybe"}, "kim"); assert False
        except ValueError:
            pass
        m = CM.matrix(repo, cfg)
        s = m["summary"]
        assert s["answered"] == 103 and s["counts"]["Accept"] == 100 and s["counts"]["Accept with Deviation"] == 1
        assert s["counts"]["Partially Accept"] == 1 and sum(c["total"] for c in m["chapters"]) == 186
        assert s["issues"] == 2 and m["rows"][100]["issue"] and not m["rows"][101]["issue"] and m["rows"][102]["issue"]
        assert m["rows"][0]["by"] == "kim" and m["rows"][0]["trace"] and m["rows"][0]["trace"][0].startswith("SYS2-")
        assert not any(l["suspect"] for l in repo.links())                     # answering is not a requirement change
        out = CM.export_xlsx(repo, cfg, root / "cm.xlsx")
        wb = load_workbook(out); ws = wb["Compliance Matrix"]
        assert ws.max_row == 5 + 186 and ws.cell(6, 7).value == "Accept" and ws.cell(107, 8).value == "액추에이터 사양 한계"
        assert str(ws.data_validations.dataValidation[0].sqref) == "G6:G191" and "Summary" in wb.sheetnames
        assert len(wb["Summary"]._charts) == 3
        # Excel -> matrix: edit the exported workbook and read it back (preview first, then apply)
        ws.cell(6, 7).value = "partially accept"; ws.cell(6, 8).value = "토크 맵은 2종만 지원"       # row of ids[0]
        ws.cell(7, 7).value = "Maybe"; ws.cell(8, 11).value = "고객 확인 완료"; ws.cell(9, 7).value = None
        ws.cell(10, 3).value = "CRS-NOPE-9999"; ws.cell(10, 2).value = None
        wb.save(root / "back.xlsx")
        pv = CM.import_xlsx(repo, cfg, root / "back.xlsx", "lee")
        ch = {(c["id"], c["field"]): c["new"] for c in pv["changes"]}
        assert ch == {(ids[0], "status"): "Partially Accept", (ids[0], "comment"): "토크 맵은 2종만 지원",
                      (ids[2], "customer_response"): "고객 확인 완료", (ids[3], "status"): ""}, ch
        assert [x["value"] for x in pv["invalid"]] == ["Maybe"] and [x["id"] for x in pv["unknown"]] == ["CRS-NOPE-9999"]
        assert pv["applied"] == 0 and CM.matrix(repo, cfg)["rows"][0]["status"] == "Accept"           # preview changes nothing
        assert CM.import_xlsx(repo, cfg, root / "back.xlsx", "lee", apply=True)["applied"] == 3
        m2 = CM.matrix(repo, cfg)["rows"]
        assert m2[0]["status"] == "Partially Accept" and m2[0]["by"] == "lee" and m2[3]["status"] == "" and m2[1]["status"] == "Accept"
        assert not CM.import_xlsx(repo, cfg, root / "back.xlsx", "lee")["changes"]
        # every change is logged with user and time; each field shows who wrote it last
        h = CM.history(repo, ids[0])
        assert [(x["user"], x["field"], x["old"], x["new"]) for x in h] == [
            ("lee", "comment", "", "토크 맵은 2종만 지원"), ("lee", "status", "Accept", "Partially Accept"), ("kim", "status", "", "Accept")]
        assert h[0]["via"].startswith("Excel: back.xlsx") and len(h[0]["at"]) == 19
        assert m2[0]["meta"]["comment"]["by"] == "lee" and m2[1]["meta"]["status"]["by"] == "kim"
        v0 = CM.version(repo)
        CM.set_rows(repo, cfg, [ids[1]], {"comment": "확인"}, "park")
        assert CM.version(repo) == v0 + 1 and CM.matrix(repo, cfg)["version"] == v0 + 1
        CM.set_rows(repo, cfg, [ids[1]], {"comment": ""}, "park")
        rep = reqif.reply(repo, cfg, "CRS")[2]                                 # same answers go into the customer's ReqIF
        assert rep["answered"] == 102 and rep["by_code"]["C"] == 98 and rep["by_code"]["PC"] == 3 and not rep["warnings"]


def test_pdf_to_word():
    """PDF -> editable Word: headings with numbers, tables, pictures; scanned / non-PDF input is refused."""
    from docx import Document
    from ecualm import pdf2docx
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "o.docx"
        st = pdf2docx.convert(SAMPLES / "CRS_eLSD_ECU_rev1.0.pdf", out)
        assert st["pages"] == 49 and st["tables"] > 60 and st["figures"] == 12 and not st["skipped_images"]
        d = Document(out)
        heads = [p.text for p in d.paragraphs if p.style.name.startswith("Heading")]
        assert any(h.startswith("3.1 ") for h in heads) and len(heads) == st["headings"]
        body = "\n".join(p.text for p in d.paragraphs)
        assert "[REQ-LOCK-001]" in body and len(d.tables) == st["tables"] and len(d.inline_shapes) == 12
        assert any("REQ-YAW-003" in c.text for t in d.tables for c in t.columns[0].cells)
        import pymupdf
        blank = Path(td) / "scan.pdf"; doc = pymupdf.open(); doc.new_page(); doc.save(blank)
        try:
            pdf2docx.convert(blank, out); assert False
        except ValueError as e:
            assert "OCR" in str(e)


def test_sys2_derivation_ai_mode():
    """SYS.1 -> SYS.2 with the SYS.2 rules: compliance decides, AI splits / rewrites / proposes gaps, review before apply."""
    import json, time
    from ecualm import compliance as CM, derive_ai as D
    with tempfile.TemporaryDirectory() as td:
        root = Path(td); write_default_config(root)
        cfg, repo = load_config(root), Repo(root)
        import_document(repo, cfg, SAMPLES / "CRS_eLSD_ECU_rev1.0.reqifz", doc="CRS", rev="1.0", mode="crs")
        ids = [r["id"] for r in CM.matrix(repo, cfg)["rows"]]
        p0 = D.plan_local(repo, cfg)                       # nobody answered yet: everything is derived, and flagged
        assert p0["include_open"] and p0["summary"]["derive"] == 186 and p0["summary"]["hold"] == 0
        CM.set_rows(repo, cfg, ids[:6], {"status": "Accept"}, "kim")
        CM.set_rows(repo, cfg, [ids[6]], {"status": "Accept with Deviation", "deviation": "응답 150ms 로 합의"}, "kim")
        CM.set_rows(repo, cfg, [ids[7]], {"status": "Partially Accept"}, "kim")                 # no basis written
        CM.set_rows(repo, cfg, [ids[8]], {"status": "Not Accept", "comment": "불가"}, "kim")
        CM.set_rows(repo, cfg, [ids[9]], {"status": "Clarification Needed", "comment": "질의"}, "kim")
        plan = D.plan_local(repo, cfg)
        by = {r["src"]: r for r in plan["rows"]}
        sm = plan["summary"]
        assert (sm["derive"], sm["deviation"], sm["skip"], sm["hold"]) == (6, 1, 1, 178) and not plan["include_open"]
        assert by[ids[7]]["decision"] == "hold" and "편차" in by[ids[7]]["reason"] and by[ids[8]]["decision"] == "skip"
        assert by[ids[6]]["questions"][0].endswith("응답 150ms 로 합의") and by[ids[0]]["reqs"][0]["criteria"]
        assert len(plan["topics"]) == 12 and any(t["covered"] for t in plan["topics"])

        # AI step (stubbed): split into two, rewrite from the deviation, questions, gap proposals; one batch fails
        cfg["llm"].update(provider="openai_compatible", base_url="http://stub", model="stub")
        calls = []

        def fake(cfg_, system, messages, max_tokens=0, timeout=0):
            body = json.loads(messages[0]["content"]); calls.append(body)
            if "requirements" in body:
                out = {}
                for q in body["requirements"]:
                    if q["id"] == ids[6]:
                        assert q["basis"] == "deviation" and q["deviation"] == "응답 150ms 로 합의"
                        out[q["id"]] = {"reqs": [{"text": "시스템은 150ms 이내에 응답해야 한다.", "criteria": "150ms 경계 측정", "method": "HIL", "type": "performance"}]}
                    elif q["id"] == ids[0]:
                        out[q["id"]] = {"reqs": [{"text": "시스템은 A 를 해야 한다.", "criteria": "c1", "method": "", "type": "functional"},
                                                 {"text": "시스템은 [TBD: 시간] 이내에 B 를 해야 한다.", "criteria": "c2", "method": "분석", "type": "weird"}],
                                        "questions": ["B 의 허용 시간은?"]}
                return json.dumps({"items": out})
            return "설명 " + json.dumps({"gaps": [{"topic": "diag", "text": "시스템은 고장 검출 시 DTC 를 저장해야 한다.", "criteria": "UDS 0x19 로 확인", "rationale": "진단 요구 없음"},
                                                 {"topic": "nope", "text": "시스템은 [TBD] 모드를 지원해야 한다."}]})
        orig = D.chat_call; D.chat_call = fake
        try:
            jid = D.start(cfg, plan, True)
            for _ in range(200):
                j = D.job(jid)
                if j["done"]:
                    break
                time.sleep(0.05)
            plan = j["plan"]
        finally:
            D.chat_call = orig
        by = {r["src"]: r for r in plan["rows"]}
        assert plan["mode"] == "ai" and len(by[ids[0]]["reqs"]) == 2 and by[ids[0]]["reqs"][1]["type"] == "functional"
        assert by[ids[0]]["questions"] == ["B 의 허용 시간은?"] and by[ids[6]]["reqs"][0]["text"].startswith("시스템은 150ms")
        assert by[ids[1]]["mode"] == "rule" and by[ids[1]]["reqs"]            # the AI gave nothing for it: rule draft kept
        assert [g["topic"] for g in plan["gaps"]] == ["diag", ""] and plan["summary"]["split"] == 1

        # apply only what was reviewed: 3 sources + 1 gap
        rows = [by[ids[0]], by[ids[6]], by[ids[1]]]
        res = D.apply(repo, cfg, rows, plan["gaps"][:1], "kim")
        assert len(res["created"]) == 5 and res["links"] == 4
        new = [repo.get(i) for i in res["created"]]
        assert new[0]["attrs"]["split"] == "1/2" and new[1]["attrs"]["open_questions"] == ["B 의 허용 시간은?"]
        assert new[2]["attrs"]["derive_basis"] == "deviation" and new[2]["attrs"]["deviation"] == "응답 150ms 로 합의"
        assert new[2]["attrs"]["verification_method"] == "HIL" and new[2]["attrs"]["req_type"] == "performance"
        assert new[0]["attrs"]["derive_mode"] == "ai" and new[3]["attrs"]["derive_mode"] == "rule"
        assert new[4]["attrs"]["origin"] == "internal" and new[4]["domain"] == "DIAG" and not repo.links(new[4]["id"])
        assert {l["dst"] for i in new[:2] for l in repo.links(i["id"]) if l["role"] == "derives"} == {ids[0]}
        again = D.plan_local(repo, cfg)
        assert again["summary"]["done"] == 3 and D.apply(repo, cfg, rows, [], "kim")["skipped"] == [ids[0], ids[6], ids[1]]


if __name__ == "__main__":
    test_assistant_local_and_llm()
    test_revision_flow()
    test_pdf_tables_and_figures()
    test_stage_flow()
    test_hwe_architecture_flow()
    test_config_merge_adds_new_stages()
    test_login_roles_and_plan()
    test_work_product_tables()
    test_test_sessions_and_evidence()
    test_sup_processes()
    test_revision_change_analysis()
    test_source_side_by_side()
    test_reqif_exchange()
    test_figures_tables_charts_linked()
    test_projects_and_sys1_shows_everything()
    test_compliance_matrix()
    test_pdf_to_word()
    test_sys2_derivation_ai_mode()
    print("OK")
