#!/usr/bin/env python3
# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

"""Validate a contribution JSON file for CI acceptance (3D).

Usage:
    validate_contribution.py <contribution.json> [--packs-dir DIR]

Checks:
1. JSON schema valid (schema_version, records array)
2. All stderr_pattern regexes compile without error
3. No ReDoS-risky patterns (exponential backtracking)
4. All hint kinds are in the allowed set
5. No sensitive fields leak through
6. Duplicate detection against existing packs
"""
import json
import os
import re
import sys
from pathlib import Path

ALLOWED_HINT_KINDS = {"append_flags", "set_env", "rewrite_cwd", "set_timeout",
                      "set_locale", "create_dir", "retry_with_backoff", "install_package"}

REQUIRED_RECORD_FIELDS = {"ecosystem", "error_class", "stderr_pattern", "avoidance_hints", "source"}

FORBIDDEN_FIELDS = {"stderr_summary", "command", "fingerprint", "matching_key",
                    "command_key", "first_seen", "last_seen", "created_at"}

# Simple ReDoS heuristic: nested quantifiers like (a+)+ or (a*)*
_REDOS_PATTERN = re.compile(r'(\(.+[*+]\))[*+]')


def validate(contribution_path: str, packs_dir: str | None = None) -> list[str]:
    """Validate a contribution file. Returns list of error strings (empty = valid)."""
    errors = []

    # Load JSON
    try:
        with open(contribution_path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        return [f"JSON load error: {e}"]

    # Schema version
    if data.get("schema_version") != 1:
        errors.append(f"Invalid schema_version: {data.get('schema_version')} (expected 1)")

    records = data.get("records")
    if not isinstance(records, list):
        errors.append("Missing or invalid 'records' array")
        return errors

    if not records:
        errors.append("No records in contribution")
        return errors

    for i, rec in enumerate(records):
        prefix = f"record[{i}]"

        # Required fields
        for field in REQUIRED_RECORD_FIELDS:
            if not rec.get(field):
                errors.append(f"{prefix}: missing required field '{field}'")

        # Forbidden fields (sensitive data leak)
        for field in FORBIDDEN_FIELDS:
            if field in rec:
                errors.append(f"{prefix}: contains forbidden field '{field}'")

        # Regex compilation
        pattern = rec.get("stderr_pattern", "")
        if pattern:
            try:
                re.compile(pattern)
            except re.error as e:
                errors.append(f"{prefix}: invalid regex '{pattern}': {e}")

            # ReDoS check
            if _REDOS_PATTERN.search(pattern):
                errors.append(f"{prefix}: potential ReDoS pattern '{pattern}'")

        # Hint kinds
        hints = rec.get("avoidance_hints", [])
        if not isinstance(hints, list) or not hints:
            errors.append(f"{prefix}: avoidance_hints must be a non-empty list")
        else:
            for j, hint in enumerate(hints):
                kind = hint.get("kind")
                if kind not in ALLOWED_HINT_KINDS:
                    errors.append(f"{prefix}.hints[{j}]: invalid kind '{kind}'")

        # Source must be 'contributed'
        if rec.get("source") != "contributed":
            errors.append(f"{prefix}: source must be 'contributed', got '{rec.get('source')}'")

    # Duplicate check against existing packs
    if packs_dir:
        packs = Path(packs_dir)
        index_path = packs / "index.json"
        if index_path.exists():
            try:
                idx = json.load(open(index_path))
                existing_keys: set[tuple[str, str, str]] = set()
                for eco, info in idx.get("ecosystems", {}).items():
                    for ec in info.get("error_classes", []):
                        shard_path = packs / eco / f"{ec}.json"
                        if shard_path.exists():
                            shard = json.load(open(shard_path))
                            for r in shard.get("records", []):
                                existing_keys.add((eco, ec, r.get("stderr_pattern", "")))
                for i, rec in enumerate(records):
                    key = (rec.get("ecosystem", ""), rec.get("error_class", ""), rec.get("stderr_pattern", ""))
                    if key in existing_keys:
                        errors.append(f"record[{i}]: duplicate ({key[0]}/{key[1]}) pattern '{rec['stderr_pattern'][:60]}...'")
            except (json.JSONDecodeError, KeyError):
                pass  # Skip duplicate check if packs are invalid

    return errors


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <contribution.json> [--packs-dir DIR]", file=sys.stderr)
        sys.exit(2)

    contribution_path = sys.argv[1]
    packs_dir = None
    if "--packs-dir" in sys.argv:
        idx = sys.argv.index("--packs-dir")
        if idx + 1 < len(sys.argv):
            packs_dir = sys.argv[idx + 1]

    errors = validate(contribution_path, packs_dir)
    if errors:
        print(f"REJECTED: {len(errors)} error(s)")
        for e in errors:
            print(f"  ✗ {e}")
        sys.exit(1)
    else:
        print("ACCEPTED: contribution is valid")
        sys.exit(0)


if __name__ == "__main__":
    main()
