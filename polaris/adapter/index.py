"""In-memory index over Polaris packs with a 300-token injection budget."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from polaris import paths

CONTEXT_TOKEN_BUDGET = 300
CONSTANT_CONTEXT_TOKEN_BUDGET = 100
CONSTANT_MAX_PATTERNS = 1

_WORD_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_\-]{2,}")


def runtime_roots() -> dict[Path, str]:
    roots = paths.configured_runtime_paths()
    return {
        roots["official"]: "official",
        roots["community"]: "community",
        roots["candidates"]: "candidate",
    }


def _tokenize_len(text: str) -> int:
    return max(1, len(text) // 4)


def _keywords(text: str) -> set[str]:
    return {m.group(0).lower() for m in _WORD_RE.finditer(text or "")}


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
    tier: str = "official"


def _compile_regexes(raws: list[str]) -> tuple:
    out = []
    for raw in raws or []:
        try:
            out.append(re.compile(raw))
        except re.error:
            continue
    return tuple(out)


def _build_pattern(rec: dict, tier: str) -> IndexedPattern:
    sigs = rec.get("trigger_signals", {}) or {}
    raws = sigs.get("stderr_regex", []) or []
    return IndexedPattern(
        pattern_id=rec["pattern_id"],
        ecosystem=rec["ecosystem"],
        error_class=rec["error_class"],
        description=rec.get("description", ""),
        stderr_regexes=_compile_regexes(raws),
        fix_path=rec.get("fix_path", {}) or {},
        false_paths=tuple(rec.get("false_paths", []) or []),
        applicability_bounds=rec.get("applicability_bounds", {}) or {},
        shortest_verification=rec.get("shortest_verification", {}) or {},
        keyword_hints=frozenset(_keywords(" ".join([rec.get("error_class", ""), rec.get("description", ""), " ".join(raws)]))),
        tier=tier,
    )


def _load_from_dir(root: Path, tier: str) -> list[IndexedPattern]:
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
                out.append(_build_pattern(rec, tier))
            except KeyError:
                continue
    return out


def _load_all() -> list[IndexedPattern]:
    all_patterns: list[IndexedPattern] = []
    for root, tier in runtime_roots().items():
        all_patterns.extend(_load_from_dir(root, tier))
    return all_patterns


def _root_signature(root: Path) -> tuple:
    if not root.exists():
        return ()
    stamp = root / ".version"
    if stamp.exists():
        stat = stamp.stat()
        return ("stamp", stat.st_mtime_ns, stat.st_size)
    stat = root.stat()
    return ("dir", stat.st_mtime_ns)


def _library_signature() -> tuple[tuple[str, tuple], ...]:
    return tuple((tier, _root_signature(root)) for root, tier in runtime_roots().items())


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
        for idx, pattern in enumerate(patterns):
            by_eco.setdefault(pattern.ecosystem, []).append(pattern)
            eco_map = kw_eco.setdefault(pattern.ecosystem, {})
            for kw in pattern.keyword_hints:
                kw_global.setdefault(kw, []).append(idx)
                eco_map.setdefault(kw, []).append(idx)
        return cls(
            patterns=tuple(patterns),
            by_ecosystem={k: tuple(v) for k, v in by_eco.items()},
            by_keyword_global={k: tuple(v) for k, v in kw_global.items()},
            by_keyword_per_eco={eco: {k: tuple(v) for k, v in mapping.items()} for eco, mapping in kw_eco.items()},
            all_ids={p.pattern_id for p in patterns},
        )


@lru_cache(maxsize=4)
def _state_for_signature(signature: tuple[tuple[str, tuple], ...]) -> IndexState:
    del signature
    return IndexState.build(_load_all())


def _default_state() -> IndexState:
    paths.ensure_user_data()
    return _state_for_signature(_library_signature())


def load_index() -> list[IndexedPattern]:
    return list(_default_state().patterns)


def match(
    error_text: str,
    ecosystem: Optional[str] = None,
    limit: int = 3,
    state: Optional[IndexState] = None,
) -> list[IndexedPattern]:
    state = state or _default_state()
    if ecosystem and ecosystem not in state.by_ecosystem:
        return []
    err_kw = _keywords(error_text)
    if err_kw:
        kw_map = state.by_keyword_per_eco.get(ecosystem) if ecosystem else state.by_keyword_global
        if not kw_map:
            return []
        candidate_idx = sorted({idx for kw in err_kw for idx in kw_map.get(kw, ())})
    else:
        candidate_idx = [idx for idx, pattern in enumerate(state.patterns) if not ecosystem or pattern.ecosystem == ecosystem]
    hits: list[IndexedPattern] = []
    for idx in candidate_idx:
        pattern = state.patterns[idx]
        if ecosystem and pattern.ecosystem != ecosystem:
            continue
        if any(rx.search(error_text) for rx in pattern.stderr_regexes):
            hits.append(pattern)
        if len(hits) >= limit:
            break
    return hits


def format_for_injection(
    patterns: list[IndexedPattern],
    token_budget: int = CONTEXT_TOKEN_BUDGET,
    max_patterns: Optional[int] = None,
) -> dict:
    payload: dict = {"patterns": []}
    used = 0
    over_budget = 0
    for pattern in patterns[:max_patterns] if max_patterns else patterns:
        entry = {
            "id": pattern.pattern_id,
            "tier": pattern.tier,
            "fix": pattern.fix_path.get("description") or pattern.fix_path.get("fix_command") or "",
            "verify": pattern.shortest_verification.get("command", ""),
            "avoid": [fp.get("wrong_guess", "") for fp in pattern.false_paths[:2]],
            "do_not_apply_when": pattern.applicability_bounds.get("do_not_apply_when", [])[:2],
        }
        projected = used + _tokenize_len(json.dumps(entry))
        if projected > token_budget:
            over_budget += 1
            if payload["patterns"]:
                break
            entry = {"id": entry["id"], "tier": entry["tier"], "fix": entry["fix"][:140]}
            projected = used + _tokenize_len(json.dumps(entry))
            while projected > token_budget and entry["fix"]:
                entry["fix"] = entry["fix"][: max(0, len(entry["fix"]) - 40)]
                projected = used + _tokenize_len(json.dumps(entry))
            if projected > token_budget:
                entry = {"id": entry["id"], "tier": entry["tier"]}
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
    payload = format_for_injection(
        patterns,
        token_budget=CONSTANT_CONTEXT_TOKEN_BUDGET,
        max_patterns=CONSTANT_MAX_PATTERNS,
    )
    payload["_budget"]["mode"] = "constant_budget"
    payload["_budget"]["max_patterns"] = CONSTANT_MAX_PATTERNS
    return payload
