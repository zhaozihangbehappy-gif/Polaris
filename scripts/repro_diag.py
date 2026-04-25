#!/usr/bin/env python3
# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

"""Focused reproduction diagnostics for a single ecosystem.

Usage:
  python3 scripts/repro_diag.py python
  python3 scripts/repro_diag.py node --json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import resource
import subprocess
import sys
from pathlib import Path


def make_preexec_fn(memory_limit_mb: int | None):
    if not memory_limit_mb:
        return None

    limit_bytes = memory_limit_mb * 1024 * 1024

    def _apply_limits() -> None:
        resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))

    return _apply_limits


def run_command(
    cmd: str,
    env: dict[str, str],
    timeout_s: int,
    memory_limit_mb: int | None = None,
) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env,
            preexec_fn=make_preexec_fn(memory_limit_mb),
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "TIMEOUT"
    except Exception as exc:  # pragma: no cover - defensive wrapper
        return 125, "", f"EXCEPTION: {exc}"


def evaluate_record(rec: dict, timeout_s: int, error_class: str, memory_limit_mb: int) -> dict:
    desc = rec.get("description", "")
    repro = rec.get("reproduction") or {}
    if not repro or not repro.get("command"):
        return {"status": "SKIP", "description": desc, "reason": "no_reproduction"}

    cmd = repro.get("command", "")
    fix_cmd = repro.get("fix_command", "") or cmd
    trigger_env = dict(repro.get("trigger_env", {}) or {})
    expected_match = repro.get("expected_stderr_match", "") or ""
    fix_env = dict(repro.get("fix_env", {}) or {})
    effective_mem_limit = memory_limit_mb if error_class == "resource_exhaustion" else None

    env1 = dict(os.environ)
    env1.update(trigger_env)
    rc1, out1, err1 = run_command(cmd, env1, timeout_s, effective_mem_limit)
    combined1 = f"{err1}{out1}"

    trigger_ok = False
    if expected_match:
        try:
            if re.search(expected_match, combined1, re.MULTILINE | re.DOTALL | re.IGNORECASE):
                trigger_ok = True
            elif rc1 != 0:
                trigger_ok = True
        except re.error as exc:
            return {"status": "FAIL", "description": desc, "reason": f"bad_regex:{exc}"}
    else:
        trigger_ok = rc1 != 0

    if not trigger_ok:
        snippet = combined1.replace("\n", " ")[:160]
        return {"status": "FAIL", "description": desc, "reason": f"trigger_no_error:{snippet}"}

    env2 = dict(os.environ)
    env2.update(trigger_env)
    env2.update(fix_env)
    for hint in rec.get("avoidance_hints", []) or []:
        if hint.get("kind") == "set_env":
            env2.update(hint.get("vars", {}) or {})

    rc2, out2, err2 = run_command(fix_cmd, env2, timeout_s, effective_mem_limit)
    combined2 = f"{err2}{out2}"

    if rc2 == 0 or combined2 != combined1:
        return {"status": "PASS", "description": desc, "reason": ""}

    return {"status": "FAIL", "description": desc, "reason": "fix_no_change"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ecosystem")
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument(
        "--resource-memory-limit-mb",
        type=int,
        default=int(os.environ.get("POLARIS_REPRO_RESOURCE_MEMORY_MB", "768")),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    project_dir = Path(__file__).resolve().parent.parent
    eco_dir = project_dir / "experience-packs" / args.ecosystem
    if not eco_dir.is_dir():
        print(f"missing ecosystem dir: {eco_dir}", file=sys.stderr)
        return 2

    results: list[dict] = []
    for pack_file in sorted(eco_dir.glob("*.json")):
        try:
            pack = json.loads(pack_file.read_text(encoding="utf-8"))
        except Exception as exc:
            results.append(
                {
                    "pack": pack_file.stem,
                    "index": -1,
                    "status": "FAIL",
                    "description": "",
                    "reason": f"load_error:{exc}",
                }
            )
            continue

        error_class = str(pack.get("error_class", "") or "")
        for idx, rec in enumerate(pack.get("records", []) or []):
            row = evaluate_record(
                rec,
                args.timeout,
                error_class,
                args.resource_memory_limit_mb,
            )
            row["pack"] = pack_file.stem
            row["index"] = idx
            results.append(row)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    skipped = sum(1 for r in results if r["status"] == "SKIP")
    print(f"{args.ecosystem}: {passed} pass, {failed} fail, {skipped} skip")
    for row in results:
        if row["status"] != "PASS":
            print(
                f"{row['pack']}[{row['index']}]: {row['status']} | "
                f"{row['description']} | {row['reason']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
