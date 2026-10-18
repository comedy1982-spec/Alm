"""ecualm — command line interface.

  ecualm init                                   프로젝트 폴더 초기화 (alm.json, .alm/)
  ecualm import SRS.docx --mode srs --rev B     문서 가져오기 + 자동 ID + 표/그림 변환 (재임포트 시 ID 유지/변경 감지)
  ecualm list --type SWE1 --status draft        아이템 조회
  ecualm show SWE1-COM-0003                     상세/링크/이력
  ecualm link SWE1-COM-0003 refines SYS2-PWR-0001
  ecualm suggest-links --src SWE1 --dst SYS2    추적 링크 자동 제안 (proposed)
  ecualm audit --report audit.html --fail-on error
  ecualm derive SYS1 SYS2 / SYS2 SWE1 / SWE1 SWE6 ...   다음 단계 전개 (draft + 추적 링크)
  ecualm stagedoc SYS2                           PAM 4.0 구조 SRS 보기 / export docx srs.docx --stage SYS2
  ecualm export xlsx out.xlsx | json out.json | md ./md | html snapshot.html
  ecualm baseline create BL_v1.0 / baseline diff BL_v1.0
  ecualm results results.json                   CI/HIL 시험 결과(PASS/FAIL·파형) 반영 → audit 에 FAIL·재시험 필요 표시
  ecualm arch export HWE2 hw.json / arch import hw.json / arch sample   블록도를 JSON(Git) 으로 주고받기
  ecualm artifact HWE2-0003                     아이템 하나의 추적 JSON (상위·SW 할당·검증 결과·인터페이스)
  ecualm serve --port 8765                      웹 UI
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import sys
import time
from pathlib import Path

from . import ops
from .audit import run_audit, suggest_links
from .config import load_config, write_default_config
from .db import Repo


def _root(args) -> Path:
    return Path(args.root).resolve()


def _ctx(args):
    root = _root(args)
    if not (root / "alm.json").exists() and args.cmd != "init":
        write_default_config(root)
    return Repo(root), load_config(root)


def _short(s: str, n: int = 90) -> str:
    s = s.replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def cmd_init(args):
    root = _root(args)
    root.mkdir(parents=True, exist_ok=True)
    p = write_default_config(root)
    if args.project:
        cfg = json.loads(p.read_text(encoding="utf-8"))
        cfg["project"] = args.project
        p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    Repo(root)
    print(f"초기화 완료: {root}\n  설정: {p}\n  저장소: {root / '.alm'}")


def cmd_import(args):
    from .importer import import_document
    repo, cfg = _ctx(args)
    for f in args.files:
        s = import_document(repo, cfg, f, doc=args.doc, rev=args.rev or "", mode=args.mode,
                            dry_run=args.dry_run, ai=args.ai, user=args.user)
        tag = " (DRY-RUN, 저장 안 함)" if s.get("dry_run") else ""
        print(f"\n[{s['doc']} rev {s['rev']}] {s['file']}{tag}")
        print(f"  블록 {s['blocks']}개 → 아이템 유형별: " + ", ".join(f"{k} {v}" for k, v in sorted(s["by_type"].items())))
        print(f"  신규 {len(s['new'])} | 변경 {len(s['modified'])} | 동일 {s['unchanged']} | 삭제 {len(s['deleted'])} | 복원 {len(s['restored'])}")
        if s["modified"]:
            print("  변경됨: " + ", ".join(s["modified"][:30]) + (" …" if len(s["modified"]) > 30 else ""))
        if s["deleted"]:
            print("  삭제됨: " + ", ".join(s["deleted"][:30]) + (" …" if len(s["deleted"]) > 30 else ""))
        if s.get("ref_links"):
            print(f"  원문 참조(근거: REQ-xxx)로 연결한 링크 {s['ref_links']}건")
        if s["suspect_links"]:
            print(f"  ⚠ Suspect 링크 {s['suspect_links']}건 → ecualm audit 로 확인")


def cmd_list(args):
    repo, cfg = _ctx(args)
    rows = repo.items(doc=args.doc, type_=args.type, include_deleted=args.status == "deleted")
    if args.status:
        rows = [r for r in rows if r["status"] == args.status]
    if args.q:
        rows = [r for r in rows if args.q.lower() in r["text"].lower() or args.q.lower() in r["id"].lower()]
    if not args.all:
        rows = [r for r in rows if r["type"] not in ("HDG", "INFO")]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2)); return
    for r in rows:
        lint = f" ⚠{len(r['lint'])}" if r["lint"] else ""
        print(f"{r['id']:<18} {r['type']:<5} {r['status']:<8} v{r['version']:<2}{lint:<4} {_short(r['text'])}")
    print(f"-- {len(rows)}건", file=sys.stderr)


def cmd_show(args):
    repo, cfg = _ctx(args)
    it = repo.get(args.id)
    if not it:
        sys.exit(f"없음: {args.id}")
    t = cfg["types"].get(it["type"], {})
    print(f"{it['id']}  [{it['type']} / {t.get('aspice', '')} / {t.get('polarion', '')}]  domain={it['domain']}  "
          f"status={it['status']}  v{it['version']}")
    print(f"문서: {it['doc']} rev {it['doc_rev']}  위치: {it['source_loc']}  섹션: {it['section']}")
    print("-" * 80)
    print(it["text"])
    print("-" * 80)
    a = {k: v for k, v in it["attrs"].items() if k not in ("grid", "quantities", "prev_text")}
    if a:
        print("속성:", json.dumps(a, ensure_ascii=False))
    if it["attrs"].get("quantities"):
        print("수치:", ", ".join(q["raw"] for q in it["attrs"]["quantities"]))
    for f in it["lint"]:
        print(f"  [{f['sev']}] {f['msg']}")
    for l in repo.links(it["id"]):
        arrow = f"→ {l['role']} {l['dst']}" if l["src"] == it["id"] else f"← {l['src']} {l['role']}"
        flags = (" [SUSPECT]" if l["suspect"] else "") + (" [proposed]" if l["state"] == "proposed" else "")
        print(f"  link {arrow}{flags}")
    if args.history:
        for h in repo.history(it["id"]):
            print(f"  v{h['version']} {h['change']:<10} {time.strftime('%Y-%m-%d %H:%M', time.localtime(h['at']))} "
                  f"{h['by']}: {_short(h['text'], 70)}")


def cmd_edit(args):
    repo, cfg = _ctx(args)
    it = ops.edit_item(repo, cfg, args.id, text=args.text, status=args.status, user=args.user)
    print(f"{it['id']} v{it['version']} status={it['status']}")


def cmd_approve(args):
    repo, cfg = _ctx(args)
    for i in args.ids:
        it = ops.edit_item(repo, cfg, i, status="approved", user=args.user)
        print(f"{it['id']} → approved")


def cmd_add(args):
    repo, cfg = _ctx(args)
    it = ops.create_item(repo, cfg, args.type, args.text, args.domain, args.doc or "", after=args.after, user=args.user)
    print(it["id"])


def cmd_reclassify(args):
    repo, cfg = _ctx(args)
    it = ops.reclassify(repo, cfg, args.id, args.type, args.domain, user=args.user)
    print(f"{args.id} → {it['id']} (기존 ID는 폐기, 링크는 proposed 상태로 이전)")


def cmd_link(args):
    repo, cfg = _ctx(args)
    ops.link(repo, cfg, args.src, args.role, args.dst, force=args.force)
    print(f"{args.src} -{args.role}-> {args.dst}")


def cmd_unlink(args):
    repo, cfg = _ctx(args)
    n = repo.remove_link(args.src, args.role, args.dst); repo.commit()
    print(f"삭제 {n}건")


def cmd_import_links(args):
    repo, cfg = _ctx(args)
    ok = bad = 0
    with open(args.csv, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                ops.link(repo, cfg, row["src"].strip(), row["role"].strip(), row["dst"].strip())
                ok += 1
            except Exception as e:
                bad += 1
                print(f"  skip {row}: {e}", file=sys.stderr)
    print(f"링크 {ok}건 등록, {bad}건 실패")


def cmd_suggest(args):
    repo, cfg = _ctx(args)
    res = suggest_links(repo, cfg, args.src, args.dst, args.min, args.top, apply=not args.dry_run)
    for r in res:
        print(f"{r['src']:<18} {r['role']:<9} {r['dst']:<18} score={r['score']}")
    print(f"-- 제안 {len(res)}건" + ("" if args.dry_run else " (proposed 상태로 저장, UI 또는 ecualm link 로 확정)"))


def cmd_clear_suspect(args):
    repo, cfg = _ctx(args)
    n = repo.clear_suspect(args.src, args.dst); repo.commit()
    print(f"Suspect 해제 {n}건")


def render_audit_html(res: dict, project: str) -> str:
    sev_color = {"error": "#c62828", "warn": "#b26a00", "info": "#456"}
    rows = "".join(
        f"<tr><td style='color:{sev_color[f['sev']]};font-weight:600'>{f['sev'].upper()}</td><td>{html.escape(f['rule'])}</td>"
        f"<td><code>{html.escape(f['item'])}</code></td><td>{html.escape(f['msg'])}</td></tr>" for f in res["findings"])
    cov = "".join(f"<tr><td>{html.escape(k)}</td><td>{v['covered']}/{v['total']}</td><td>"
                  f"<div style='background:#e3e8ef;width:160px;height:10px;border-radius:5px'>"
                  f"<div style='background:{'#2e7d32' if v['pct'] == 100 else '#c77700'};width:{1.6 * v['pct']}px;height:10px;border-radius:5px'></div></div>"
                  f"</td><td>{v['pct']}%</td></tr>" for k, v in res["coverage"].items())
    s = res["summary"]
    return f"""<!doctype html><html lang="ko"><meta charset="utf-8"><title>PAM 4.0 Audit</title>
<style>body{{font-family:system-ui,'Malgun Gothic',sans-serif;margin:32px;color:#1d2733}}table{{border-collapse:collapse;width:100%;margin:12px 0 28px}}
td,th{{border-bottom:1px solid #e3e8ef;padding:6px 8px;text-align:left;font-size:13px;vertical-align:top}}th{{background:#f3f6fa}}
.cards{{display:flex;gap:12px}}.c{{border:1px solid #e3e8ef;border-radius:8px;padding:12px 18px}}.c b{{font-size:24px;display:block}}</style>
<h1>ASPICE PAM 4.0 추적성·일관성 감사 — {html.escape(project)}</h1><p>{time.strftime('%Y-%m-%d %H:%M')}</p>
<div class="cards"><div class="c"><b>{s['items']}</b>아이템</div><div class="c"><b>{s['links']}</b>링크</div>
<div class="c" style="color:#c62828"><b>{s['errors']}</b>Error</div><div class="c" style="color:#b26a00"><b>{s['warnings']}</b>Warning</div>
<div class="c"><b>{s['infos']}</b>Info</div></div>
<h2>커버리지</h2><table><tr><th>규칙</th><th>충족</th><th></th><th>%</th></tr>{cov}</table>
<h2>발견 사항</h2><table><tr><th>심각도</th><th>규칙</th><th>아이템</th><th>내용</th></tr>{rows}</table></html>"""


def cmd_audit(args):
    repo, cfg = _ctx(args)
    res = run_audit(repo, cfg)
    s = res["summary"]
    print(f"아이템 {s['items']} / 링크 {s['links']} → Error {s['errors']}, Warning {s['warnings']}, Info {s['infos']}")
    for k, v in res["coverage"].items():
        print(f"  {k:<45} {v['covered']}/{v['total']} ({v['pct']}%)")
    if not args.quiet:
        for f in res["findings"]:
            if f["sev"] == "info" and not args.verbose:
                continue
            print(f"  [{f['sev']:<5}] {f['item']:<18} {f['rule']:<20} {f['msg']}")
    if args.report:
        Path(args.report).write_text(render_audit_html(res, cfg["project"]), encoding="utf-8")
        print(f"리포트: {args.report}")
    if args.json:
        Path(args.json).write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.fail_on == "error" and s["errors"]:
        sys.exit(2)
    if args.fail_on == "warn" and (s["errors"] or s["warnings"]):
        sys.exit(2)


def cmd_derive(args):
    from .stages import derive
    repo, cfg = _ctx(args)
    r = derive(repo, cfg, args.src, args.dst, args.ids or None, user=args.user)
    print(f"{r['from']} → {r['to']}: 원천 {r['sources']}건 → 신규 {len(r['created'])}건, 링크 {r['links']}건, 건너뜀 {len(r['skipped'])}건")
    for i in r["created"][:40]:
        it = repo.get(i)
        print(f"  {i:<20} {_short(it['text'], 80)}")


def cmd_stagedoc(args):
    from .stages import stage_doc
    repo, cfg = _ctx(args)
    sd = stage_doc(repo, cfg, args.stage, args.mode)
    print(f"# {sd['title']}   아이템 {sd['stats']['total']}  상태 {sd['stats']['status']}")
    for sec in sd["sections"]:
        print(f"\n{sec['number']} {sec['title']}")
        if sec["kind"] == "text":
            for t in sec["text"]:
                print(f"   {t}")
        elif sec["kind"] == "group":
            for sub in sec["sub"]:
                print(f"  {sub['number']} {sub['title']}")
                for it in sub["items"]:
                    ups = ", ".join(f"{l['role']} {l['dst']}" for l in it.get("_up", []))
                    print(f"     {it['id']:<20} [{it['status']}] {_short(it['text'], 70)}" + (f"  ← {ups}" if ups else ""))
        elif sec["kind"] == "source":
            print(f"   ({len(sec['items'])} 블록)")
        else:
            print(f"   ({len(sec['rows'])} 행)")


def cmd_export(args):
    from . import export as ex
    repo, cfg = _ctx(args)
    fmt = args.format
    if fmt == "xlsx":
        print(ex.export_excel(repo, cfg, Path(args.out)))
    elif fmt == "json":
        print(ex.export_json(repo, cfg, Path(args.out)))
    elif fmt == "md":
        for p in ex.export_markdown(repo, cfg, Path(args.out)):
            print(p)
    elif fmt == "html":
        print(ex.export_static_html(repo, cfg, Path(args.out)))
    elif fmt == "docx":
        if not args.stage:
            sys.exit("--stage 가 필요합니다 (예: --stage SYS2)")
        print(ex.export_stage_docx(repo, cfg, args.stage, Path(args.out), args.mode))


def cmd_baseline(args):
    repo, cfg = _ctx(args)
    if args.action == "create":
        print(repo.create_baseline(args.name, args.note or ""))
    elif args.action == "list":
        for b in repo.baselines():
            print(f"{b['name']:<20} {time.strftime('%Y-%m-%d %H:%M', time.localtime(b['at']))} {b['note']}")
    elif args.action == "diff":
        a = repo.baseline(args.name)
        if a is None:
            sys.exit(f"베이스라인 없음: {args.name}")
        if args.other:
            b = repo.baseline(args.other)
        else:
            b = {"items": repo.items(include_deleted=True), "links": repo.links()}
        ai = {i["id"]: i for i in a["items"]}
        bi = {i["id"]: i for i in b["items"]}
        for iid in sorted(set(ai) | set(bi)):
            x, y = ai.get(iid), bi.get(iid)
            if x and not y:
                print(f"- {iid}")
            elif y and not x:
                print(f"+ {iid}  {_short(y['text'], 70)}")
            elif x["text"] != y["text"] or x["status"] != y["status"]:
                what = []
                if x["text"] != y["text"]:
                    what.append("text")
                if x["status"] != y["status"]:
                    what.append(f"status {x['status']}→{y['status']}")
                print(f"~ {iid}  ({', '.join(what)})")
        al = {(l["src"], l["role"], l["dst"]) for l in a["links"]}
        bl = {(l["src"], l["role"], l["dst"]) for l in b["links"]}
        for l in sorted(bl - al):
            print(f"+ link {' '.join(l)}")
        for l in sorted(al - bl):
            print(f"- link {' '.join(l)}")


def cmd_serve(args):
    from .server import serve
    _ctx(args)
    serve(_root(args), args.host, args.port)


def cmd_results(args):
    from .arch import ingest_results
    repo, cfg = _ctx(args)
    r = ingest_results(repo, cfg, json.loads(Path(args.file).read_text(encoding="utf-8")), user=args.user)
    print(f"결과 반영 {len(r['updated'])}건" + (f", 알 수 없는 TC {len(r['unknown'])}건: {', '.join(map(str, r['unknown']))}" if r["unknown"] else ""))
    if r["unknown"] and args.strict:
        sys.exit(2)


def cmd_arch(args):
    from . import arch
    repo, cfg = _ctx(args)
    if args.action == "export":
        if not args.target or not args.out:
            raise ValueError("사용법: ecualm arch export <SYS3|HWE2|SWE2> <out.json>")
        Path(args.out).write_text(json.dumps(arch.export_arch(repo, cfg, args.target), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"내보냄: {args.out}")
        return
    if args.action == "import":
        if not args.target:
            raise ValueError("사용법: ecualm arch import <arch.json>")
        r = arch.import_arch(repo, cfg, json.loads(Path(args.target).read_text(encoding="utf-8")), user=args.user)
    else:
        r = arch.load_sample(repo, cfg, user=args.user)
    print(f"[{r['canvas']}] 블록 신규 {len(r['created'])} · 갱신 {len(r['updated'])} · 인터페이스 {r['interfaces']} · TC {r['tests']} · 결과 {r['results']}")


def cmd_artifact(args):
    from .arch import artifact_json
    repo, cfg = _ctx(args)
    print(json.dumps(artifact_json(repo, cfg, args.id), ensure_ascii=False, indent=2))


def cmd_stats(args):
    repo, cfg = _ctx(args)
    for d in repo.docs():
        print(f"{d['doc']:<30} rev {d['rev']:<14} {d['n']} items, approved {d['approved']}")
    for row in repo.con.execute("SELECT type, status, COUNT(*) n FROM items GROUP BY type, status ORDER BY type"):
        print(f"  {row['type']:<8} {row['status']:<9} {row['n']}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ecualm", description="ECU ALM — ASPICE PAM 4.0 요구사항 관리 도구",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--root", default=".", help="프로젝트 폴더 (기본: 현재 폴더)")
    ap.add_argument("--user", default="cli", help="이력에 남길 사용자명")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init"); p.add_argument("--project"); p.set_defaults(fn=cmd_init)
    p = sub.add_parser("import", help="DOCX/PDF/DOC 가져오기")
    p.add_argument("files", nargs="+")
    p.add_argument("--doc", help="문서 이름 (기본: 파일명). 같은 이름으로 다시 넣으면 개정본으로 처리")
    p.add_argument("--rev", help="개정 표기 (예: B, v1.2)")
    p.add_argument("--mode", default="srs", choices=["srs", "crs", "sys2", "swe1", "info"],
                   help="srs: SYS.2/SWE.1 자동 분리, crs: 고객 요구사항(SYS.1), sys2/swe1: 타입 고정, info: 참고 문서")
    p.add_argument("--dry-run", action="store_true", help="저장하지 않고 변경 결과만 보기")
    p.add_argument("--ai", action="store_true", help="alm.json llm 설정으로 AI 정제(분류/분할/그림→Mermaid)")
    p.set_defaults(fn=cmd_import)
    p = sub.add_parser("list"); p.add_argument("--type"); p.add_argument("--doc"); p.add_argument("--status")
    p.add_argument("--q"); p.add_argument("--all", action="store_true", help="제목/설명 아이템 포함")
    p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_list)
    p = sub.add_parser("show"); p.add_argument("id"); p.add_argument("--history", action="store_true"); p.set_defaults(fn=cmd_show)
    p = sub.add_parser("edit"); p.add_argument("id"); p.add_argument("--text"); p.add_argument("--status"); p.set_defaults(fn=cmd_edit)
    p = sub.add_parser("approve"); p.add_argument("ids", nargs="+"); p.set_defaults(fn=cmd_approve)
    p = sub.add_parser("add"); p.add_argument("--type", required=True); p.add_argument("--text", required=True)
    p.add_argument("--domain"); p.add_argument("--doc"); p.add_argument("--after"); p.set_defaults(fn=cmd_add)
    p = sub.add_parser("reclassify"); p.add_argument("id"); p.add_argument("--type", required=True)
    p.add_argument("--domain"); p.set_defaults(fn=cmd_reclassify)
    p = sub.add_parser("link"); p.add_argument("src"); p.add_argument("role"); p.add_argument("dst")
    p.add_argument("--force", action="store_true"); p.set_defaults(fn=cmd_link)
    p = sub.add_parser("unlink"); p.add_argument("src"); p.add_argument("role"); p.add_argument("dst"); p.set_defaults(fn=cmd_unlink)
    p = sub.add_parser("import-links", help="CSV(src,role,dst) 일괄 링크"); p.add_argument("csv"); p.set_defaults(fn=cmd_import_links)
    p = sub.add_parser("suggest-links"); p.add_argument("--src", required=True); p.add_argument("--dst", required=True)
    p.add_argument("--min", type=float, default=0.2); p.add_argument("--top", type=int, default=2)
    p.add_argument("--dry-run", action="store_true"); p.set_defaults(fn=cmd_suggest)
    p = sub.add_parser("clear-suspect"); p.add_argument("--src"); p.add_argument("--dst"); p.set_defaults(fn=cmd_clear_suspect)
    p = sub.add_parser("audit"); p.add_argument("--report"); p.add_argument("--json")
    p.add_argument("--fail-on", choices=["none", "error", "warn"], default="none")
    p.add_argument("--quiet", action="store_true"); p.add_argument("--verbose", action="store_true"); p.set_defaults(fn=cmd_audit)
    p = sub.add_parser("export"); p.add_argument("format", choices=["xlsx", "json", "md", "html", "docx"]); p.add_argument("out")
    p.add_argument("--stage", help="docx: 단계 ID (SYS2, SWE1 ...)"); p.add_argument("--mode", default="pam", choices=["pam", "source"])
    p.set_defaults(fn=cmd_export)
    p = sub.add_parser("derive", help="단계 전개: 예) derive SYS2 SWE1"); p.add_argument("src"); p.add_argument("dst")
    p.add_argument("--ids", nargs="*", help="특정 아이템만"); p.set_defaults(fn=cmd_derive)
    p = sub.add_parser("stagedoc", help="PAM 4.0 구조 단계 문서 보기"); p.add_argument("stage")
    p.add_argument("--mode", default="pam", choices=["pam", "source"]); p.set_defaults(fn=cmd_stagedoc)
    p = sub.add_parser("baseline"); p.add_argument("action", choices=["create", "list", "diff"])
    p.add_argument("name", nargs="?"); p.add_argument("other", nargs="?"); p.add_argument("--note"); p.set_defaults(fn=cmd_baseline)
    p = sub.add_parser("results", help="시험 결과 JSON 반영 (CI/HIL)"); p.add_argument("file")
    p.add_argument("--strict", action="store_true", help="모르는 TC 가 있으면 종료 코드 2"); p.set_defaults(fn=cmd_results)
    p = sub.add_parser("arch", help="블록도 JSON 내보내기/가져오기"); p.add_argument("action", choices=["export", "import", "sample"])
    p.add_argument("target", nargs="?", help="export: 단계 ID, import: 파일"); p.add_argument("out", nargs="?"); p.set_defaults(fn=cmd_arch)
    p = sub.add_parser("artifact", help="아이템 추적 JSON"); p.add_argument("id"); p.set_defaults(fn=cmd_artifact)
    p = sub.add_parser("serve"); p.add_argument("--host", default="127.0.0.1"); p.add_argument("--port", type=int, default=8765)
    p.set_defaults(fn=cmd_serve)
    p = sub.add_parser("stats"); p.set_defaults(fn=cmd_stats)

    args = ap.parse_args(argv)
    try:
        args.fn(args)
    except (KeyError, ValueError, RuntimeError) as e:
        sys.exit(f"오류: {e}")


if __name__ == "__main__":
    main()
