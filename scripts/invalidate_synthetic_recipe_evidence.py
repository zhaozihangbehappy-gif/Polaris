"""Invalidate evidence rows produced against synthetic bash-echo recipes.

Applies the same quarantine logic as invalidate_contaminated_evidence.py, but
for a different contamination class: the pattern's `shortest_verification.command`
or `fix_path.fix_command` is an effective no-op (`bash -c 'echo ...; exit N'`,
or `python3 -c ... 2>&1 || true`, or a self-creating script that sets up and
tests its own state). Those recipes pass the hermetic harness's pre/post gates
regardless of whether the agent did anything, so any `verified_live` row
against them is contamination-by-construction.

The four rows that previously counted in VERIFIED_PROMOTION_REPORT.md — for
python.missing_dependency.000, python.syntax_error.000, python.file_not_found.000,
and node.file_not_found.001 — are moved into invalidated_evidence[] with
status=invalidated_synthetic_recipe. Their patterns stay in the pool and become
candidates for the authoring pipeline (scripts/author_fixtures.py); only once
an `authored_fixture` block with a sandbox-validated reviewer_record is present
are those patterns eligible for real verified_live re-run.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REASON = (
    "Evidence produced against a synthetic bash-echo recipe (pre-failure or "
    "fix_command that always succeeds/fails irrespective of agent action). "
    "Promotion to verified_live requires a pattern-level authored_fixture with "
    "a sandbox-validated reviewer_record. See VERIFIED_PROMOTION_REPORT.md "
    "and scripts/pattern_schema._is_synthetic_recipe."
)
INVALIDATED_AT = "2026-04-19T19:30:00+00:00"
TARGET_PATTERN_IDS = {
    "python.missing_dependency.000",
    "python.syntax_error.000",
    "python.file_not_found.000",
    "node.file_not_found.001",
}
TARGETS = [
    REPO / "experience-packs-v4/python/missing_dependency.json",
    REPO / "experience-packs-v4/python/syntax_error.json",
    REPO / "experience-packs-v4/python/file_not_found.json",
    REPO / "experience-packs-v4/node/file_not_found.json",
]


def main() -> None:
    moved = 0
    for shard in TARGETS:
        data = json.loads(shard.read_text())
        dirty = False
        for rec in data.get("records", []):
            if rec.get("pattern_id") not in TARGET_PATTERN_IDS:
                continue
            repro = rec.setdefault("agent_reproducibility", {})
            old = repro.get("evidence") or []
            if not old:
                continue
            invalidated = repro.setdefault("invalidated_evidence", [])
            for ev in old:
                ev_copy = dict(ev)
                ev_copy["status"] = "invalidated_synthetic_recipe"
                ev_copy["invalidation_reason"] = REASON
                ev_copy["invalidated_at"] = INVALIDATED_AT
                invalidated.append(ev_copy)
                moved += 1
            repro["evidence"] = []
            dirty = True
        if dirty:
            shard.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            print(f"rewrote {shard.relative_to(REPO)}")
    print(f"moved {moved} evidence rows → invalidated_evidence[] "
          f"(status=invalidated_synthetic_recipe)")


if __name__ == "__main__":
    main()
