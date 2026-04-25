# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

"""Generate eval/runs/manual_cursor_required.json — the queue of cases that
require a manual Cursor transcript before any Cursor evidence can be written.

Contents: one entry per (case_id, variant) pair for every authored_fixture case
in eval/cases/. Each entry records workspace_path (after hermetic copy), prompt,
and expected transcript filename the human reviewer must produce.

No transcript → no Cursor evidence. This file is the single source of truth for
the Cursor manual backlog; if the list is non-empty, the Cursor count cannot
be reported as anything but blocked_cursor_transcript_missing.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CASES_DIR = REPO / "eval" / "cases"
MANUAL_DIR = REPO / "eval" / "runs" / "manual_cursor"
OUT = REPO / "eval" / "runs" / "manual_cursor_required.json"


def main() -> int:
    entries = []
    for p in sorted(CASES_DIR.glob("generated_*.json")):
        case = json.loads(p.read_text())
        if not case.get("promotion_eligible"):
            continue
        for variant in ("baseline", "polaris"):
            entries.append({
                "case_id": case["case_id"],
                "pattern_id": case.get("pattern_id"),
                "ecosystem": case.get("ecosystem"),
                "variant": variant,
                "prompt_template": case["initial_prompt"],
                "fix_command_test": case["success_criteria"]["fix_command_test"],
                "expected_transcript_path": str(
                    (MANUAL_DIR / f"{case['case_id']}__{variant}.json").relative_to(REPO)
                ),
                "workspace_instruction": (
                    "Before running Cursor, copy eval/fixtures/" + case["case_id"] +
                    "/files/ into a fresh workspace and point Cursor at it; substitute "
                    "{workdir} in the prompt with that workspace's absolute path."
                ),
            })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generated_cases": len({e["case_id"] for e in entries}),
        "queue_length_total_variants": len(entries),
        "entries": entries,
        "note": (
            "Cursor has no stable headless CLI runner in this environment. "
            "Until each entry's expected_transcript_path exists, "
            "eval.orchestrator --runner cursor emits blocked_cursor_transcript_missing "
            "and evidence_writer refuses to record Cursor verified_live."
        ),
    }, indent=2))
    print(f"wrote {OUT.relative_to(REPO)}: {len(entries)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
