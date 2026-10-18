"""Rule-based analysis: requirement detection, atomic splitting, SYS.2 / SWE.1 split,
domain tagging, PAM 4.0 lint and quantity extraction. Works offline; llm.py can refine it."""
from __future__ import annotations

import re

# ---------------------------------------------------------------- quantities
UNIT_FACTORS = {
    # time -> seconds
    "us": ("time", 1e-6), "µs": ("time", 1e-6), "μs": ("time", 1e-6), "ms": ("time", 1e-3), "s": ("time", 1.0),
    "sec": ("time", 1.0), "초": ("time", 1.0), "min": ("time", 60.0), "분": ("time", 60.0),
    # voltage
    "mv": ("voltage", 1e-3), "v": ("voltage", 1.0), "kv": ("voltage", 1e3),
    # current
    "ua": ("current", 1e-6), "µa": ("current", 1e-6), "μa": ("current", 1e-6), "ma": ("current", 1e-3), "a": ("current", 1.0),
    # temperature
    "°c": ("temperature", 1.0), "℃": ("temperature", 1.0), "degc": ("temperature", 1.0),
    # angle / position
    "deg": ("angle", 1.0), "°": ("angle", 1.0), "mm": ("length", 1e-3),
    # frequency
    "hz": ("frequency", 1.0), "khz": ("frequency", 1e3), "mhz": ("frequency", 1e6),
    # speed / torque / ratio
    "rpm": ("speed", 1.0), "nm": ("torque", 1.0), "n·m": ("torque", 1.0), "%": ("ratio", 1.0),
    "kbps": ("bitrate", 1e3), "mbps": ("bitrate", 1e6),
}
_units_sorted = sorted(UNIT_FACTORS, key=len, reverse=True)
QTY_RE = re.compile(
    r"(?<![\w.])([-+]?\d+(?:\.\d+)?)\s*(?:~|–|-|to|∼)?\s*(?:([-+]?\d+(?:\.\d+)?)\s*)?("
    + "|".join(re.escape(u) for u in _units_sorted) + r")(?![a-zA-Z])", re.I)


def quantities(text: str) -> list[dict]:
    out = []
    for m in QTY_RE.finditer(text):
        unit = m.group(3).lower()
        if unit not in UNIT_FACTORS:
            continue
        dim, f = UNIT_FACTORS[unit]
        vals = [float(m.group(1))]
        if m.group(2):
            vals.append(float(m.group(2)))
        for v in vals:
            out.append({"dim": dim, "value": round(v * f, 12), "raw": m.group(0).strip(), "unit": m.group(3)})
    return out


# ---------------------------------------------------------------- sentences
SENT_SPLIT = re.compile(r"(?<=[.。!?])\s+(?=\S)")


def split_sentences(text: str) -> list[str]:
    parts = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        # do not split decimals or abbreviations like "Fig. 3" / "e.g. "
        protected = re.sub(r"(\d)\.(\d)", r"\1<DOT>\2", line)
        protected = re.sub(r"\b(e\.g|i\.e|Fig|No|vs|etc)\.", lambda m: m.group(1) + "<DOT>", protected, flags=re.I)
        for s in SENT_SPLIT.split(protected):
            s = s.replace("<DOT>", ".").strip()
            if s:
                parts.append(s)
    return parts


class Analyzer:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.req_res = [re.compile(p, re.I | re.M) for p in cfg["requirement_patterns"]]
        self.native_re = re.compile(cfg["native_id_pattern"])
        self.ambiguous = cfg["ambiguous_words"]
        self.info_res = [re.compile(p, re.I) for p in cfg.get("info_patterns", [])]
        self.anaphora = cfg.get("anaphora_words", [])

    # ------------------------------------------------------------ detection
    def is_requirement(self, text: str) -> bool:
        t = text.strip()
        if len(t) < 8 or any(r.search(t) for r in self.info_res):
            return False
        return any(r.search(t) for r in self.req_res)

    def native_id(self, text: str) -> str:
        m = self.native_re.search(text[:40])
        if not m:
            return ""
        nid = m.group(1)
        # ignore things that look like units/hex/ECU part numbers rather than IDs
        if re.fullmatch(r"0X[0-9A-F]+", nid) or nid.startswith(("TC3", "ISO", "AEC", "IEC")):
            return ""
        return nid

    def strip_native_id(self, text: str, nid: str) -> str:
        if not nid:
            return text
        return re.sub(r"^\s*[\[\(]?" + re.escape(nid) + r"[\]\)]?\s*[:.\-–]?\s*", "", text).strip() or text

    def split_atomic(self, text: str) -> list[str]:
        """Split a paragraph into atomic requirement statements: each sentence with its own
        obligation becomes an item. Explanatory sentences stay with the requirement before them."""
        sents = split_sentences(text)
        if len(sents) <= 1:
            return [text.strip()]
        groups: list[str] = []
        for s in sents:
            if self.is_requirement(s) or not groups:
                groups.append(s)
            else:
                groups[-1] = groups[-1] + " " + s
        return groups

    # ------------------------------------------------------------ classification
    def level(self, text: str, section: str = "") -> tuple[str, float]:
        """Return ('SYS2'|'SWE1', confidence) for a requirement taken from an integrated SRS."""
        hay = f"{section} {text}"
        score = {"SYS2": 0.0, "SWE1": 0.0}
        for lvl, hints in self.cfg.get("level_section_hints", {}).items():
            if any(h.lower() in section.lower() for h in hints):
                score[lvl] += 3.0
        for lvl, words in self.cfg["level_keywords"].items():
            for w in words:
                if w.lower() in hay.lower():
                    score[lvl] += 1.0 + (0.5 if w.lower() in section.lower() else 0)
        # timing in ms/us with cycles strongly suggests a software requirement
        if re.search(r"\d+\s*(ms|us|μs|µs)\s*(주기|cycle|period|마다)", hay, re.I):
            score["SWE1"] += 2
        total = score["SYS2"] + score["SWE1"]
        if total == 0:
            return "SWE1", 0.3
        lvl = "SYS2" if score["SYS2"] > score["SWE1"] else "SWE1"
        return lvl, round(max(score.values()) / total, 2)

    def domain(self, text: str, section: str = "", native_id: str = "") -> str:
        m = re.match(r"^[A-Z]+[-_]([A-Z]+)[-_]\d", native_id or "")
        if m and m.group(1) in self.cfg.get("native_domain_map", {}):
            return self.cfg["native_domain_map"][m.group(1)]
        tl, sl = text.lower(), section.lower()
        best, best_score = "GEN", 0
        for dom, words in self.cfg["domain_keywords"].items():
            if dom == "HSI":
                continue
            sc = sum(2 * tl.count(w.lower()) + sl.count(w.lower()) for w in words)
            if sc > best_score:
                best, best_score = dom, sc
        return best

    # ------------------------------------------------------------ lint
    def lint(self, text: str, type_: str) -> list[dict]:
        out = []
        low = text.lower()
        hits = []
        for w in self.ambiguous:
            wl = w.lower()
            if (re.search(r"(?<![a-z])" + re.escape(wl.strip()) + r"(?![a-z])", low) if wl.strip().isascii() else wl in low):
                hits.append(w.strip())
        for w in hits:
            if not any(w != o and w.lower() in o.lower() for o in hits):  # keep the longest match only
                out.append({"rule": "ambiguous", "sev": "warn", "msg": f"모호한 표현 '{w}' → 정량 수치/조건으로 대체"})
        modal_hits = len(re.findall(r"(해야|하여야|되어야|shall|must)", text, re.I))
        conj = re.search(r"(하고|하며|및|그리고|또한|, and |; )", text)
        if modal_hits >= 2 or (modal_hits >= 1 and conj and len(text) > 120):
            out.append({"rule": "compound", "sev": "warn", "msg": "복합 요구사항 의심 → 원자적 단문으로 분할 검토"})
        qs = quantities(text)
        if any(t in text for t in self.cfg["quantity_triggers"]) and not qs and type_ in ("SYS2", "SWE1", "CRS"):
            out.append({"rule": "no_quantity", "sev": "warn", "msg": "시간/전압/전류 등 언급에 정량 값(수치+단위) 없음"})
        if re.search(r"\b\d+(\.\d+)?\s*(이내|이상|이하|미만|초과)", text) and not qs:
            out.append({"rule": "no_unit", "sev": "warn", "msg": "수치에 단위가 없음"})
        if type_ == "SWE1" and not re.search(r"(조건|경우|시|when|if|동안|while|상태)", text, re.I):
            out.append({"rule": "no_condition", "sev": "info", "msg": "SWE.1 구조 [Pre-Condition]→[Trigger]→[Processing]→[Output] 중 조건 미기술"})
        if re.search(r"(TBD|TBC|미정|추후)", text, re.I):
            out.append({"rule": "tbd", "sev": "error", "msg": "미확정 항목(TBD/TBC/미정) 포함"})
        if any(text.lstrip().startswith(w) for w in self.anaphora):
            out.append({"rule": "anaphora", "sev": "warn", "msg": "앞 문장을 참조('이때' 등) → 단독으로 이해되도록 조건을 다시 기술"})
        if len(text) > 400:
            out.append({"rule": "too_long", "sev": "info", "msg": "400자 초과 → 분할 검토"})
        return out
