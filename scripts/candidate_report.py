"""Emit candidate-report-v4.json — per-ecosystem, per-error-class breakdown.

Also flags any candidate that leaked evidence (policy violation) or that shares
a (ecosystem, error_class, stderr_regex[0]) fingerprint with another candidate.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pattern_schema import validate_shape

REPO = Path(__file__).resolve().parent.parent
CANDIDATE = REPO / "experience-packs-v4-candidates"


def main() -> int:
    per_eco: dict[str, int] = defaultdict(int)
    per_class: dict[str, int] = defaultdict(int)
    schema_valid = 0
    rejected = 0
    rejected_examples: list[tuple[str, list[str]]] = []
    fingerprints: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    leaked_evidence: list[str] = []
    wrong_source: list[str] = []
    missing_review_flag: list[str] = []

    if not CANDIDATE.exists():
        print("no candidate pool yet")
        return 1

    for shard_path in sorted(CANDIDATE.rglob("*.json")):
        shard = json.loads(shard_path.read_text())
        for rec in shard.get("records", []):
            errors = validate_shape(rec)
            if errors:
                rejected += 1
                if len(rejected_examples) < 10:
                    rejected_examples.append((rec.get("pattern_id", "?"), errors))
                continue
            schema_valid += 1
            pid = rec["pattern_id"]
            per_eco[rec["ecosystem"]] += 1
            per_class[f"{rec['ecosystem']}.{rec['error_class']}"] += 1
            regex0 = (rec.get("trigger_signals", {}).get("stderr_regex") or [""])[0]
            fingerprints[(rec["ecosystem"], rec["error_class"], regex0)].append(pid)
            if rec.get("agent_reproducibility", {}).get("evidence"):
                leaked_evidence.append(pid)
            if rec.get("source") != "candidate_generated":
                wrong_source.append(pid)
            needs = set(rec.get("needs_human_review", []))
            required = {"false_paths", "applicability_bounds", "agent_reproducibility"}
            if not required.issubset(needs):
                missing_review_flag.append(pid)

    duplicates = {
        "|".join(k): v for k, v in fingerprints.items() if len(v) > 1
    }

    report = {
        "candidate_total_files": sum(1 for _ in CANDIDATE.rglob("*.json")),
        "per_ecosystem_count": dict(sorted(per_eco.items())),
        "per_error_class_count": dict(sorted(per_class.items())),
        "schema_valid_count": schema_valid,
        "rejected_count": rejected,
        "rejected_examples": rejected_examples,
        "duplicate_fingerprints_count": len(duplicates),
        "duplicate_fingerprints_sample": dict(list(duplicates.items())[:10]),
        "policy_violations": {
            "leaked_evidence_ids": leaked_evidence,
            "wrong_source_ids": wrong_source,
            "missing_human_review_flag_ids": missing_review_flag,
        },
    }
    (REPO / "candidate-report-v4.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
