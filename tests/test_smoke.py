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


if __name__ == "__main__":
    test_revision_flow()
    test_pdf_tables_and_figures()
    test_stage_flow()
    print("OK")
