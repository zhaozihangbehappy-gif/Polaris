"""Turn eval/curator/sources.yaml into eval/cases/real_*.json.

No HTTP. No scraping. User curates sources.yaml by hand (or by pasting from a
browser). This script just validates and emits. Refusing to run when
issue_url contains 'REPLACE_ME' so placeholders never become real cases.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("curator: pip install pyyaml", file=sys.stderr)
    raise

REPO = Path(__file__).resolve().parent.parent.parent
SRC = REPO / "eval" / "curator" / "sources.yaml"
OUT = REPO / "eval" / "cases"

REQUIRED = {"id", "issue_url", "title", "ecosystem", "pain_category",
            "initial_prompt", "success_criteria", "max_rounds"}
VALID_PAIN = {"monorepo", "ci_only", "long_session_repeat", "unfamiliar_ecosystem"}


def validate(entry: dict) -> list[str]:
    errs = []
    missing = REQUIRED - entry.keys()
    if missing:
        errs.append(f"missing fields: {sorted(missing)}")
    if "REPLACE_ME" in entry.get("issue_url", ""):
        errs.append("issue_url still contains REPLACE_ME placeholder")
    if entry.get("pain_category") not in VALID_PAIN:
        errs.append(f"pain_category must be one of {sorted(VALID_PAIN)}")
    sc = entry.get("success_criteria", {})
    if "root_cause_regex" not in sc or "fix_command_test" not in sc:
        errs.append("success_criteria missing root_cause_regex or fix_command_test")
    return errs


def to_case(entry: dict) -> dict:
    return {
        "case_id": entry["id"],
        "source": "real_issue",
        "ecosystem": entry["ecosystem"],
        "initial_prompt": entry["initial_prompt"].strip(),
        "success_criteria": entry["success_criteria"],
        "max_rounds": entry["max_rounds"],
        "real_issue_url": entry["issue_url"],
        "pain_category": entry["pain_category"],
    }


def main() -> int:
    entries = yaml.safe_load(SRC.read_text()) or []
    emitted = 0
    skipped = []
    for e in entries:
        errs = validate(e)
        if errs:
            skipped.append({"id": e.get("id", "?"), "errors": errs})
            continue
        case = to_case(e)
        out_path = OUT / f"{e['id']}.json"
        out_path.write_text(json.dumps(case, indent=2))
        emitted += 1
    report = {
        "sources_total": len(entries),
        "emitted": emitted,
        "skipped": skipped,
        "note": "Skipped entries are expected until issue_url placeholders are filled in.",
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
