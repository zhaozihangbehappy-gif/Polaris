#!/usr/bin/env python3
"""Task fingerprint contract for Polaris experience stores.

Every fingerprint preserves three layers:
- raw_descriptor: original user input, verbatim
- normalized_descriptor: canonicalized form
- matching_key: deterministic hash for exact-match lookup

Both success patterns and failure records use this as their primary key.
"""
import hashlib
import json
import shlex


def normalize_command(command: str) -> str:
    """Canonicalize a shell command: sort flags, collapse whitespace."""
    try:
        parts = shlex.split(command)
    except ValueError:
        parts = command.split()
    if not parts:
        return command.strip()
    executable = parts[0]
    args = sorted(parts[1:])
    return " ".join([executable] + args)


def compute(command: str, cwd: str, task_name: str | None = None) -> dict:
    """Compute a three-layer task fingerprint."""
    raw = command
    normalized = normalize_command(command)
    key_input = f"{normalized}\0{cwd}"
    if task_name:
        key_input = f"{task_name}\0{key_input}"
    matching_key = hashlib.sha256(key_input.encode("utf-8")).hexdigest()[:16]
    return {
        "raw_descriptor": raw,
        "normalized_descriptor": normalized,
        "matching_key": matching_key,
    }


def matches(fp_a: dict, fp_b: dict) -> bool:
    """Exact-match on matching_key. This is the L3 extension point."""
    return fp_a.get("matching_key") == fp_b.get("matching_key")
