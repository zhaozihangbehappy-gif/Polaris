#!/usr/bin/env python3
# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

"""Task fingerprint contract for Polaris experience stores.

Every fingerprint preserves four layers:
- raw_descriptor: original user input, verbatim
- normalized_descriptor: canonicalized form
- matching_key: deterministic hash for exact-match lookup (includes cwd)
- command_key: deterministic hash for command-only fallback (excludes cwd)

Both success patterns and failure records use this as their primary key.
"""
import argparse
import hashlib
import json
import shlex


def _is_flag(token: str) -> bool:
    """Return True if the token looks like a flag (starts with -)."""
    return token.startswith("-")


def normalize_command(command: str) -> str:
    """Canonicalize a shell command: sort flags, preserve positional arg order.

    Flags (tokens starting with '-') and their immediately following values
    are collected, sorted, and placed after the executable.  Positional
    arguments (non-flag tokens that are not flag-values) keep their original
    relative order.  This prevents order-sensitive commands like ``cp a b``
    and ``cp b a`` from collapsing into the same fingerprint.
    """
    try:
        parts = shlex.split(command)
    except ValueError:
        parts = command.split()
    if not parts:
        return command.strip()

    executable = parts[0]
    rest = parts[1:]

    flags: list[tuple[str, ...]] = []  # each item is (flag,) or (flag, value)
    positionals: list[str] = []
    i = 0
    while i < len(rest):
        token = rest[i]
        if _is_flag(token):
            # Peek ahead: if the next token exists and is NOT a flag, treat
            # it as this flag's value (e.g. --output foo).
            if i + 1 < len(rest) and not _is_flag(rest[i + 1]):
                flags.append((token, rest[i + 1]))
                i += 2
            else:
                flags.append((token,))
                i += 1
        else:
            positionals.append(token)
            i += 1

    # Sort flags lexicographically; positionals stay in original order.
    sorted_flags = sorted(flags)
    flag_tokens = [tok for group in sorted_flags for tok in group]
    return " ".join([executable] + flag_tokens + positionals)


def compute(command: str, cwd: str, task_name: str | None = None) -> dict:
    """Compute a four-layer task fingerprint.

    - matching_key: SHA-256(normalized + cwd + task_name) — exact match
    - command_key: SHA-256(normalized + task_name) — command-only fallback (no cwd)
    """
    raw = command
    normalized = normalize_command(command)

    # matching_key includes cwd
    key_input = f"{normalized}\0{cwd}"
    if task_name:
        key_input = f"{task_name}\0{key_input}"
    matching_key = hashlib.sha256(key_input.encode("utf-8")).hexdigest()[:16]

    # command_key excludes cwd
    cmd_key_input = normalized
    if task_name:
        cmd_key_input = f"{task_name}\0{cmd_key_input}"
    command_key = hashlib.sha256(cmd_key_input.encode("utf-8")).hexdigest()[:16]

    return {
        "raw_descriptor": raw,
        "normalized_descriptor": normalized,
        "matching_key": matching_key,
        "command_key": command_key,
    }


def matches(fp_a: dict, fp_b: dict) -> bool:
    """Exact-match on matching_key. This is the L3 extension point."""
    return fp_a.get("matching_key") == fp_b.get("matching_key")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute Polaris task fingerprints.")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    comp = sub.add_parser("compute")
    comp.add_argument("--command", required=True)
    comp.add_argument("--cwd", default=".")
    comp.add_argument("--task-name", default=None)

    args = parser.parse_args()

    if args.subcommand == "compute":
        fp = compute(args.command, args.cwd, args.task_name)
        print(json.dumps(fp, sort_keys=True))


if __name__ == "__main__":
    main()
