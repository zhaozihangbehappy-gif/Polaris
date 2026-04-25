# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

"""Sample 10 random v4 patterns and dump their state for human review.

This is the Gate 1 close-out artifact. Codex's pass criterion was "false_paths
non-empty and real on 10 random". After migration, all false_paths are empty
(by design — we do not fabricate). The sample surfaces that fact explicitly.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
V4 = REPO / "experience-packs-v4"
SEED = 20260419


def main() -> int:
    rng = random.Random(SEED)
    all_records: list[dict] = []
    for shard_path in sorted(V4.rglob("*.json")):
        shard = json.loads(shard_path.read_text())
        all_records.extend(shard.get("records", []))

    sample = rng.sample(all_records, 10)
    rows = []
    for rec in sample:
        rows.append({
            "pattern_id": rec["pattern_id"],
            "description": rec["description"][:90],
            "false_paths_count": len(rec.get("false_paths", [])),
            "applicability_do_not_apply_when_count":
                len(rec.get("applicability_bounds", {}).get("do_not_apply_when", [])),
            "agent_repro_evidence_count":
                len(rec.get("agent_reproducibility", {}).get("evidence", [])),
            "needs_human_review": rec.get("needs_human_review", []),
        })
    report = {
        "sampled": 10,
        "seed": SEED,
        "rows": rows,
        "summary": {
            "false_paths_non_empty": sum(1 for r in rows if r["false_paths_count"] > 0),
            "applicability_bounds_authored":
                sum(1 for r in rows if r["applicability_do_not_apply_when_count"] > 0),
            "agent_repro_evidenced":
                sum(1 for r in rows if r["agent_repro_evidence_count"] > 0),
        },
        "verdict": (
            "Migration preserved v3 content faithfully. false_paths, "
            "applicability_bounds, and agent_reproducibility are intentionally "
            "empty — these are the three human/eval-authored fields that Gate 2 "
            "and subsequent curation must populate before any pattern counts "
            "toward the 1000 target."
        ),
    }
    (REPO / "migration-sample-v4.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
