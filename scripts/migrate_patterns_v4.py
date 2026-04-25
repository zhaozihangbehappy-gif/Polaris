# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

"""Migrate v3 experience-packs/*.json into v4 schema.

Auto-fills what can be mechanically derived. Never fabricates false_paths or
applicability_bounds — those must be human-authored and show up in the
NEEDS_HUMAN_REVIEW report. agent_reproducibility is empty on migration; it is
populated later by the eval harness (Gate 2).
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

from pattern_schema import (
    AgentReproducibility,
    ApplicabilityBounds,
    FalsePath,
    FixPath,
    PatternV4,
    ShortestVerification,
    TriggerSignals,
    SCHEMA_VERSION,
)

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "experience-packs"
DST = REPO / "experience-packs-v4"

# Ecosystems we migrate. Skip top-level summary files like index.json, *.json.
ECOSYSTEMS = ["python", "node", "docker", "go", "java", "rust", "ruby", "terraform"]


def migrate_record(rec: dict, ecosystem: str, error_class: str, idx: int) -> PatternV4:
    pattern_id = f"{ecosystem}.{error_class}.{idx:03d}"

    stderr = rec.get("stderr_pattern")
    trigger = TriggerSignals(
        stderr_regex=[stderr] if stderr else [],
    )

    repro = rec.get("reproduction", {}) or {}
    verification = ShortestVerification(
        command=repro.get("command", ""),
        trigger_env=repro.get("trigger_env", {}) or {},
        expected_stderr_match=repro.get("expected_stderr_match"),
        expected_fix_outcome=repro.get("expected_fix_outcome"),
    )

    fix = FixPath(
        structured_hints=rec.get("avoidance_hints", []) or [],
        fix_command=repro.get("fix_command"),
        fix_env=repro.get("fix_env", {}) or {},
        description=rec.get("description", ""),
    )

    needs_review = ["false_paths", "applicability_bounds", "agent_reproducibility"]

    return PatternV4(
        pattern_id=pattern_id,
        ecosystem=ecosystem,
        error_class=error_class,
        description=rec.get("description", ""),
        source=rec.get("source", "prebuilt"),
        trigger_signals=trigger,
        false_paths=[],
        shortest_verification=verification,
        fix_path=fix,
        applicability_bounds=ApplicabilityBounds(),
        agent_reproducibility=AgentReproducibility(),
        legacy_v3=rec,
        needs_human_review=needs_review,
    )


def migrate_ecosystem(eco: str) -> list[PatternV4]:
    eco_dir = SRC / eco
    if not eco_dir.is_dir():
        return []
    patterns: list[PatternV4] = []
    for shard_path in sorted(eco_dir.glob("*.json")):
        error_class = shard_path.stem
        with shard_path.open() as f:
            shard = json.load(f)
        for i, rec in enumerate(shard.get("records", [])):
            patterns.append(migrate_record(rec, eco, error_class, i))
    return patterns


def write_v4(patterns: list[PatternV4]) -> None:
    DST.mkdir(parents=True, exist_ok=True)
    grouped: dict[tuple[str, str], list[PatternV4]] = {}
    for p in patterns:
        grouped.setdefault((p.ecosystem, p.error_class), []).append(p)
    for (eco, cls), items in grouped.items():
        out_dir = DST / eco
        out_dir.mkdir(parents=True, exist_ok=True)
        shard = {
            "ecosystem": eco,
            "error_class": cls,
            "schema_version": SCHEMA_VERSION,
            "records": [asdict(p) for p in items],
        }
        (out_dir / f"{cls}.json").write_text(json.dumps(shard, indent=2))


def write_report(patterns: list[PatternV4]) -> dict:
    total = len(patterns)
    review_items = sum(len(p.needs_human_review) for p in patterns)
    per_eco: dict[str, int] = {}
    for p in patterns:
        per_eco[p.ecosystem] = per_eco.get(p.ecosystem, 0) + 1
    report = {
        "schema_version": SCHEMA_VERSION,
        "total_patterns_migrated": total,
        "per_ecosystem": per_eco,
        "needs_human_review_items_total": review_items,
        "patterns_counting_toward_1000_target": 0,
        "note": (
            "All patterns migrate schema-wise but count=0 for the 1000-target "
            "because agent_reproducibility is empty until Gate 2 eval harness "
            "runs and records verified_live evidence."
        ),
    }
    (REPO / "migration-report-v4.json").write_text(json.dumps(report, indent=2))
    return report


def main() -> int:
    all_patterns: list[PatternV4] = []
    for eco in ECOSYSTEMS:
        all_patterns.extend(migrate_ecosystem(eco))
    write_v4(all_patterns)
    report = write_report(all_patterns)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
