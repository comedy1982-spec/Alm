"""Optional AI refinement (stdlib only, no SDK needed).

provider = "anthropic"          → Claude Messages API (key from env named in llm.api_key_env)
provider = "openai_compatible"  → any on-prem / private server exposing /v1/chat/completions
                                  (vLLM, Ollama, LM Studio ...), so documents never leave the company.

Everything AI produces stays in 'draft' status and is marked with source "ai" for human review.
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

SYSTEM = (
    "You are a requirements engineer for an automotive ECU project (ASPICE PAM 4.0, AUTOSAR Classic, "
    "Infineon TC364, BLDC position control, Hyundai ES specs). Answer ONLY with valid JSON, no prose. "
    "Keep the original language of the requirement text (Korean stays Korean)."
)

REFINE_PROMPT = """Classify and clean these requirement candidates taken from an SRS.
For each item return an object:
  "i": same index,
  "type": "SYS2" (system level: physical/electrical/mechanical/environment/EMC/vehicle behaviour) or
          "SWE1" (software: algorithms, timing/cycles, signal processing, CAN/diagnostics handling, state logic),
  "domain": one of PWR, MOT, COM, DIAG, SAFE, ENV, MECH, GEN,
  "split": null, or a list of atomic requirement sentences if the text contains several obligations,
  "issues": list of short Korean strings describing ambiguity / missing quantity / missing condition,
  "verification_criteria": one short Korean sentence describing how to verify it.
Return a JSON array only.

ITEMS:
"""

FIG_PROMPT = """This figure comes from an automotive ECU requirements document.
Return JSON: {"summary": short Korean description,
 "diagram_type": "state" | "sequence" | "block" | "timing" | "flow" | "table" | "photo" | "other",
 "mermaid": Mermaid code that reproduces the diagram structure (states, transitions with conditions,
            blocks and connections, messages) or "" if it is a photo or cannot be expressed}"""


SECRETS = ".alm/secrets.json"


def api_key(cfg: dict) -> str:
    """API key: environment variable named in llm.api_key_env first, then the project-local
    .alm/secrets.json written from the web UI (never stored in alm.json, never sent to the browser)."""
    llm = cfg.get("llm", {})
    k = os.environ.get(llm.get("api_key_env") or "ANTHROPIC_API_KEY", "")
    if k:
        return k
    root = cfg.get("_root")
    if root:
        f = Path(root) / SECRETS
        if f.exists():
            try:
                return json.loads(f.read_text(encoding="utf-8")).get("api_key", "")
            except (ValueError, OSError):
                return ""
    return ""


def chat_call(cfg: dict, system: str, messages: list[dict], max_tokens: int = 2048, timeout: int = 120) -> str:
    """Multi-turn call used by the assistant panel. messages: [{"role": "user"|"assistant", "content": str}]."""
    llm = cfg["llm"]
    provider = llm.get("provider", "none")
    key = api_key(cfg)
    if provider == "anthropic":
        if not key:
            raise RuntimeError("API 키가 없습니다 (AI 설정에서 입력하거나 환경변수 " + (llm.get("api_key_env") or "ANTHROPIC_API_KEY") + ")")
        body = {"model": llm["model"], "max_tokens": max_tokens, "system": system, "messages": messages}
        url = (llm.get("base_url") or "https://api.anthropic.com").rstrip("/") + "/v1/messages"
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={
            "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    if provider == "openai_compatible":
        if not llm.get("base_url"):
            raise RuntimeError("사내 LLM 서버 주소(base_url)가 없습니다")
        body = {"model": llm["model"], "max_tokens": max_tokens, "messages": [{"role": "system", "content": system}, *messages]}
        headers = {"content-type": "application/json"}
        if key:
            headers["authorization"] = f"Bearer {key}"
        req = urllib.request.Request(llm["base_url"].rstrip("/") + "/v1/chat/completions", data=json.dumps(body).encode(),
                                     method="POST", headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
        return data["choices"][0]["message"]["content"]
    raise RuntimeError("AI 공급자가 설정되지 않았습니다")


def _call(cfg: dict, prompt: str, image: tuple[bytes, str] | None = None, max_tokens: int = 4096) -> str:
    llm = cfg["llm"]
    provider = llm.get("provider", "none")
    key = api_key(cfg)
    if provider == "anthropic":
        content = []
        if image:
            content.append({"type": "image", "source": {"type": "base64", "media_type": f"image/{image[1]}",
                                                        "data": base64.b64encode(image[0]).decode()}})
        content.append({"type": "text", "text": prompt})
        body = {"model": llm["model"], "max_tokens": max_tokens, "system": SYSTEM,
                "messages": [{"role": "user", "content": content}]}
        url = (llm.get("base_url") or "https://api.anthropic.com").rstrip("/") + "/v1/messages"
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={
            "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.loads(r.read())
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    if provider == "openai_compatible":
        content = [{"type": "text", "text": prompt}]
        if image:
            content.append({"type": "image_url", "image_url": {
                "url": f"data:image/{image[1]};base64,{base64.b64encode(image[0]).decode()}"}})
        body = {"model": llm["model"], "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}]}
        url = llm["base_url"].rstrip("/") + "/v1/chat/completions"
        headers = {"content-type": "application/json"}
        if key:
            headers["authorization"] = f"Bearer {key}"
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers=headers)
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.loads(r.read())
        return data["choices"][0]["message"]["content"]
    raise RuntimeError("alm.json 의 llm.provider 가 설정되지 않았습니다 (anthropic | openai_compatible)")


def _json(text: str):
    m = re.search(r"(\[.*\]|\{.*\})", text, re.S)
    return json.loads(m.group(1) if m else text)


def refine_candidates(cands: list[dict], cfg: dict, batch: int = 25) -> list[dict]:
    from .classify import Analyzer, quantities
    an = Analyzer(cfg)
    req_idx = [i for i, c in enumerate(cands) if c["kind"] == "req" and c["type"] in ("SYS2", "SWE1")]
    results: dict[int, dict] = {}
    for k in range(0, len(req_idx), batch):
        chunk = req_idx[k:k + batch]
        payload = [{"i": i, "text": cands[i]["text"], "section": cands[i]["section"]} for i in chunk]
        try:
            out = _json(_call(cfg, REFINE_PROMPT + json.dumps(payload, ensure_ascii=False)))
            for o in out:
                results[int(o["i"])] = o
        except Exception as e:  # keep the rule-based result
            print(f"[ai] refine batch failed: {e}", file=sys.stderr)
    new: list[dict] = []
    for i, c in enumerate(cands):
        r = results.get(i)
        if not r:
            new.append(c); continue
        texts = r.get("split") or [c["text"]]
        for t in texts:
            nc = json.loads(json.dumps(c))
            nc["text"], nc["title"] = t, t[:80]
            if r.get("type") in ("SYS2", "SWE1"):
                nc["type"] = r["type"]
            if r.get("domain") in cfg["domain_keywords"]:
                nc["domain"] = r["domain"]
            nc["attrs"]["quantities"] = quantities(t)
            nc["attrs"]["ai"] = {"verification_criteria": r.get("verification_criteria", ""),
                                 "split_from": c["text"] if len(texts) > 1 else ""}
            nc["lint"] = an.lint(t, nc["type"]) + [{"rule": "ai", "sev": "info", "msg": s} for s in r.get("issues", [])]
            new.append(nc)
    return new


def describe_figures(cands: list[dict], cfg: dict, asset_dir: Path) -> None:
    for c in cands:
        if c["kind"] != "fig" or not c["attrs"].get("file"):
            continue
        f = asset_dir / c["attrs"]["file"]
        ext = f.suffix.lstrip(".").replace("jpg", "jpeg")
        if ext not in ("png", "jpeg", "gif", "webp"):
            continue
        try:
            out = _json(_call(cfg, FIG_PROMPT + f"\nCaption: {c['attrs'].get('caption', '')}",
                              image=(f.read_bytes(), ext), max_tokens=3000))
            c["attrs"]["ai_summary"] = out.get("summary", "")
            c["attrs"]["diagram_type"] = out.get("diagram_type", "")
            if out.get("mermaid"):
                c["attrs"]["diagram_code"] = out["mermaid"]
                c["attrs"]["diagram_lang"] = "mermaid"
        except Exception as e:
            print(f"[ai] figure {f.name} failed: {e}", file=sys.stderr)
