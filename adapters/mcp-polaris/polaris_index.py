"""In-memory index over experience-packs-v4 with 300-token injection budget.

Matching pipeline (designed for scale-invariance to 1000+ patterns):

  1. ecosystem_bucket[eco]   → candidates for that ecosystem only (if hint)
  2. keyword_prefilter       → drop candidates whose error_class/description
                                share no trigger keyword with error_text
  3. regex_scan              → compile-once pattern set, first hit per record
  4. limit=3 short-circuit   → break once limit hits accumulate

The match() return list never exceeds `limit` (default 3). Injection format
applies a hard 300-token budget before flushing to the MCP client.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

PACKS_DIR = Path(__file__).resolve().parent.parent.parent / "experience-packs-v4"
CONTEXT_TOKEN_BUDGET = 300
CONSTANT_CONTEXT_TOKEN_BUDGET = 100
CONSTANT_MAX_PATTERNS = 1


# ---------- tokenizer stub ----------

def _tokenize_len(text: str) -> int:
    return max(1, len(text) // 4)


# ---------- keyword prefilter ----------

_WORD_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_\-]{2,}")


def _keywords(text: str) -> set[str]:
    return {m.group(0).lower() for m in _WORD_RE.finditer(text or "")}


# ---------- record ----------

@dataclass(frozen=True)
class IndexedPattern:
    pattern_id: str
    ecosystem: str
    error_class: str
    description: str
    stderr_regexes: tuple
    fix_path: dict
    false_paths: tuple
    applicability_bounds: dict
    shortest_verification: dict
    keyword_hints: frozenset


def _compile_regexes(raws: list[str]) -> tuple:
    out = []
    for r in raws or []:
        try:
            out.append(re.compile(r))
        except re.error:
            continue
    return tuple(out)


def _build_pattern(rec: dict) -> IndexedPattern:
    sigs = rec.get("trigger_signals", {}) or {}
    raws = sigs.get("stderr_regex", []) or []
    regexes = _compile_regexes(raws)
    hints_text = " ".join([
        rec.get("error_class", ""),
        rec.get("description", ""),
        " ".join(raws),
    ])
    hints = _keywords(hints_text)
    return IndexedPattern(
        pattern_id=rec["pattern_id"],
        ecosystem=rec["ecosystem"],
        error_class=rec["error_class"],
        description=rec.get("description", ""),
        stderr_regexes=regexes,
        fix_path=rec.get("fix_path", {}) or {},
        false_paths=tuple(rec.get("false_paths", []) or []),
        applicability_bounds=rec.get("applicability_bounds", {}) or {},
        shortest_verification=rec.get("shortest_verification", {}) or {},
        keyword_hints=frozenset(hints),
    )


def _load_from_dir(root: Path) -> list[IndexedPattern]:
    out: list[IndexedPattern] = []
    if not root.exists():
        return out
    for shard in sorted(root.rglob("*.json")):
        try:
            data = json.loads(shard.read_text())
        except json.JSONDecodeError:
            continue
        for rec in data.get("records", []):
            try:
                out.append(_build_pattern(rec))
            except KeyError:
                continue
    return out


@dataclass
class IndexState:
    patterns: tuple
    by_ecosystem: dict
    by_keyword_global: dict
    by_keyword_per_eco: dict
    all_ids: set

    @classmethod
    def build(cls, patterns: list[IndexedPattern]) -> "IndexState":
        by_eco: dict[str, list[IndexedPattern]] = {}
        kw_global: dict[str, list[int]] = {}
        kw_eco: dict[str, dict[str, list[int]]] = {}
        for idx, p in enumerate(patterns):
            by_eco.setdefault(p.ecosystem, []).append(p)
            eco_map = kw_eco.setdefault(p.ecosystem, {})
            for kw in p.keyword_hints:
                kw_global.setdefault(kw, []).append(idx)
                eco_map.setdefault(kw, []).append(idx)
        return cls(
            patterns=tuple(patterns),
            by_ecosystem={k: tuple(v) for k, v in by_eco.items()},
            by_keyword_global={k: tuple(v) for k, v in kw_global.items()},
            by_keyword_per_eco={
                eco: {k: tuple(v) for k, v in mp.items()}
                for eco, mp in kw_eco.items()
            },
            all_ids={p.pattern_id for p in patterns},
        )


@lru_cache(maxsize=1)
def _default_state() -> IndexState:
    return IndexState.build(_load_from_dir(PACKS_DIR))


def load_index() -> list[IndexedPattern]:
    """Back-compat for callers that want the flat list."""
    return list(_default_state().patterns)


def match(
    error_text: str,
    ecosystem: Optional[str] = None,
    limit: int = 3,
    state: Optional[IndexState] = None,
) -> list[IndexedPattern]:
    if state is None:
        state = _default_state()
    if ecosystem and ecosystem not in state.by_ecosystem:
        return []

    err_kw = _keywords(error_text)

    # Inverted index: union of pattern indices whose keyword_hints intersect
    # error keywords. Bounded by error keyword count × average postings length,
    # not by pool size.
    if err_kw:
        kw_map = state.by_keyword_per_eco.get(ecosystem) if ecosystem else state.by_keyword_global
        if not kw_map:
            return []
        seen_idx: set[int] = set()
        for kw in err_kw:
            for idx in kw_map.get(kw, ()):  # type: ignore[union-attr]
                seen_idx.add(idx)
        candidate_idx = sorted(seen_idx)
    else:
        if ecosystem:
            candidate_idx = [i for i, p in enumerate(state.patterns) if p.ecosystem == ecosystem]
        else:
            candidate_idx = list(range(len(state.patterns)))

    hits: list[IndexedPattern] = []
    for i in candidate_idx:
        p = state.patterns[i]
        if ecosystem and p.ecosystem != ecosystem:
            continue
        for rx in p.stderr_regexes:
            if rx.search(error_text):
                hits.append(p)
                break
        if len(hits) >= limit:
            break
    return hits


def format_for_injection(
    patterns: list[IndexedPattern],
    token_budget: int = CONTEXT_TOKEN_BUDGET,
    max_patterns: Optional[int] = None,
) -> dict:
    """Serialize under a hard 300-token budget. Drops low-priority fields first."""
    payload: dict = {"patterns": []}
    used = 0
    over_budget = 0
    for p in patterns[:max_patterns] if max_patterns else patterns:
        entry = {
            "id": p.pattern_id,
            "fix": p.fix_path.get("description") or p.fix_path.get("fix_command") or "",
            "verify": p.shortest_verification.get("command", ""),
            "avoid": [fp.get("wrong_guess", "") for fp in p.false_paths[:2]],
            "do_not_apply_when": p.applicability_bounds.get("do_not_apply_when", [])[:2],
        }
        projected = used + _tokenize_len(json.dumps(entry))
        if projected > token_budget:
            over_budget += 1
            if payload["patterns"]:
                break
            # Very first entry already over — trim to id+fix only.
            entry = {"id": entry["id"], "fix": entry["fix"][:140]}
            projected = used + _tokenize_len(json.dumps(entry))
            while projected > token_budget and entry["fix"]:
                entry["fix"] = entry["fix"][: max(0, len(entry["fix"]) - 40)]
                projected = used + _tokenize_len(json.dumps(entry))
            if projected > token_budget:
                entry = {"id": entry["id"]}
                projected = used + _tokenize_len(json.dumps(entry))
                if projected > token_budget:
                    break
        payload["patterns"].append(entry)
        used = projected
    payload["_budget"] = {
        "used_tokens_est": used,
        "limit": token_budget,
        "over_budget_count": over_budget,
    }
    return payload


def format_for_constant_budget(patterns: list[IndexedPattern]) -> dict:
    """Runtime default: constant-cost payload for large pattern pools."""
    payload = format_for_injection(
        patterns,
        token_budget=CONSTANT_CONTEXT_TOKEN_BUDGET,
        max_patterns=CONSTANT_MAX_PATTERNS,
    )
    payload["_budget"]["mode"] = "constant_budget"
    payload["_budget"]["max_patterns"] = CONSTANT_MAX_PATTERNS
    return payload
