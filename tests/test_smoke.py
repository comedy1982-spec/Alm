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


if __name__ == "__main__":
    test_revision_flow()
    test_pdf_tables_and_figures()
    test_stage_flow()
    test_hwe_architecture_flow()
    test_config_merge_adds_new_stages()
    print("OK")
