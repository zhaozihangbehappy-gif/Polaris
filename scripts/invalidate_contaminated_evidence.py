# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

"""One-shot: move existing evidence on two patterns into invalidated_evidence[].

Rationale (2026-04-19 Codex review): transcripts for run 20260419T171919 show
the agent reporting "already fixed / no edits needed" — the expected_failure
never reproduced in the workdir before the agent touched it. Evidence rows are
therefore not liveness proof; they only prove that a persistent /tmp/_polaris_*
workspace was already in the fixed state when the variant started.

This script preserves the audit trail: status on each row flips to
`invalidated_contaminated_fixture`, the full record moves into
`invalidated_evidence[]`, and the main `evidence[]` becomes empty.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REASON = (
    "Fixture not reset between runs — transcript shows agent observed "
    "already-fixed workdir state. Expected_failure_command never reproduced "
    "the bad state before the agent's 'fix', so these runs do not establish "
    "liveness. See INVALIDATED_EVIDENCE_REPORT.md."
)
INVALIDATED_AT = "2026-04-19T18:30:00+00:00"
TARGETS = [
    REPO / "experience-packs-v4/python/missing_dependency.json",
    REPO / "experience-packs-v4/node/missing_dependency.json",
]
TARGET_PATTERN_IDS = {"python.missing_dependency.000", "node.missing_dependency.000"}


def main() -> None:
    moved = 0
    for shard in TARGETS:
        data = json.loads(shard.read_text())
        for rec in data.get("records", []):
            if rec.get("pattern_id") not in TARGET_PATTERN_IDS:
                continue
            repro = rec.setdefault("agent_reproducibility", {})
            old = repro.get("evidence", []) or []
            invalidated = repro.setdefault("invalidated_evidence", [])
            for ev in old:
                ev_copy = dict(ev)
                ev_copy["status"] = "invalidated_contaminated_fixture"
                ev_copy["invalidation_reason"] = REASON
                ev_copy["invalidated_at"] = INVALIDATED_AT
                invalidated.append(ev_copy)
                moved += 1
            repro["evidence"] = []
        shard.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        print(f"rewrote {shard.relative_to(REPO)}")
    print(f"moved {moved} evidence rows → invalidated_evidence[]")


if __name__ == "__main__":
    main()
