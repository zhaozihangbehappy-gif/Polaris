"""Undo scripts/canonicalize_candidates.py.

The canonicalization produced synthetic `bash -c 'echo ...; exit 1'` pre-failure
commands and `bash -c 'echo ...; exit 0'` fix_commands. Any agent — including
one that does nothing — would satisfy the hermetic harness's pre-failure and
post-fix gates with those recipes, which means promoting them to
`verified_live` would be contamination by construction.

Every record canonicalized retained a `recipe_canonicalization` audit block
with the original values, so reversal is mechanical: restore the originals
and drop the audit block.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CAND = REPO / "experience-packs-v4-candidates"


def revert(rec: dict) -> bool:
    audit = rec.get("recipe_canonicalization")
    if not audit:
        return False
    sv = rec.setdefault("shortest_verification", {})
    fp = rec.setdefault("fix_path", {})
    sv["command"] = audit.get("original_shortest_verification_command")
    sv["expected_stderr_match"] = audit.get("original_expected_stderr_match")
    fp["fix_command"] = audit.get("original_fix_command")
    if sv.get("expected_fix_outcome") == "different_error_or_success":
        sv.pop("expected_fix_outcome", None)
    rec.pop("recipe_canonicalization", None)
    review = rec.get("needs_human_review") or []
    if "agent_reproducibility" not in review:
        review.append("agent_reproducibility")
    rec["needs_human_review"] = review
    return True


def main() -> int:
    reverted = 0
    shards = 0
    for shard in sorted(CAND.rglob("*.json")):
        data = json.loads(shard.read_text())
        changed = False
        for rec in data.get("records", []):
            if revert(rec):
                reverted += 1
                changed = True
        if changed:
            shard.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            shards += 1
    print(json.dumps({"records_reverted": reverted, "shards_rewritten": shards}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
