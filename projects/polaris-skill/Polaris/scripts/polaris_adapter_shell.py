#!/usr/bin/env python3
"""Real shell-command execution adapter for Polaris Phase 1.

Runs a user-provided shell command, captures stdout/stderr/exit code,
and produces a runner-result-compatible artifact. Supports structured
experience hints from the restricted primitive set.
"""
import argparse
import json
import shlex
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


SUPPORTED_HINT_KINDS = {"append_flags", "set_env", "rewrite_cwd", "set_timeout"}

DEFAULT_TIMEOUT_MS = 60000


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def apply_hints(command: str, cwd: str, timeout_ms: int,
                experience_hints: dict) -> tuple[str, str, int, list[dict], list[dict]]:
    """Apply structured experience hints. Returns (command, cwd, timeout_ms, applied, rejected)."""
    applied = []
    rejected = []
    env_vars = {}

    all_hints = experience_hints.get("prefer", []) + experience_hints.get("avoid", [])

    # avoid wins over prefer for same kind — collect avoid kinds
    avoid_kinds = {h.get("kind") for h in experience_hints.get("avoid", [])}

    for hint in all_hints:
        kind = hint.get("kind")
        if kind not in SUPPORTED_HINT_KINDS:
            rejected.append({"hint": hint, "reason": f"unsupported hint kind: {kind}"})
            continue

        # If this is a prefer-hint but an avoid-hint of same kind exists, skip (avoid wins)
        is_prefer = hint in experience_hints.get("prefer", [])
        if is_prefer and kind in avoid_kinds:
            rejected.append({"hint": hint, "reason": "conflict: avoid-hint of same kind takes precedence"})
            continue

        if kind == "append_flags":
            flags = hint.get("flags", [])
            if flags:
                command = command + " " + " ".join(shlex.quote(f) for f in flags)
                applied.append({"kind": "append_flags", "flags": flags})

        elif kind == "set_env":
            new_vars = hint.get("vars", {})
            env_vars.update(new_vars)
            applied.append({"kind": "set_env", "vars": new_vars})

        elif kind == "rewrite_cwd":
            new_cwd = hint.get("cwd")
            if new_cwd:
                cwd = new_cwd
                applied.append({"kind": "rewrite_cwd", "cwd": new_cwd})

        elif kind == "set_timeout":
            new_timeout = hint.get("timeout_ms")
            if new_timeout and isinstance(new_timeout, (int, float)):
                timeout_ms = int(new_timeout)
                applied.append({"kind": "set_timeout", "timeout_ms": timeout_ms})

    return command, cwd, timeout_ms, applied, rejected


def execute(command: str, cwd: str, timeout_ms: int, env_overrides: dict | None = None) -> dict:
    """Execute a shell command and return structured result."""
    env = None
    if env_overrides:
        import os
        env = dict(os.environ)
        env.update(env_overrides)

    timeout_s = max(1, timeout_ms / 1000)
    start = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout_s,
            env=env,
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        return {
            "status": "ok" if proc.returncode == 0 else "failed",
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "duration_ms": duration_ms,
        }
    except subprocess.TimeoutExpired:
        duration_ms = int((time.monotonic() - start) * 1000)
        return {
            "status": "failed",
            "exit_code": -1,
            "stdout": "",
            "stderr": f"command timed out after {timeout_s}s",
            "duration_ms": duration_ms,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute a real shell command through Polaris.")
    parser.add_argument("--command", required=True)
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--timeout-ms", type=int, default=DEFAULT_TIMEOUT_MS)
    parser.add_argument("--output", required=True)
    parser.add_argument("--goal", default="")
    parser.add_argument("--adapter", default="shell-command")
    parser.add_argument("--experience-hints-json", default="{}")
    parser.add_argument("--applied-rules-json", default="[]")
    parser.add_argument("--selected-pattern-json", default="{}")
    parser.add_argument("--execution-contract-json", default="{}")
    args = parser.parse_args()

    experience_hints = json.loads(args.experience_hints_json)
    applied_rules = json.loads(args.applied_rules_json)
    selected_pattern = json.loads(args.selected_pattern_json)
    contract = json.loads(args.execution_contract_json)

    command = args.command
    cwd = args.cwd
    timeout_ms = args.timeout_ms

    # Apply experience hints
    applied_hints = []
    rejected_hints = []
    env_overrides = {}
    if experience_hints.get("prefer") or experience_hints.get("avoid"):
        command, cwd, timeout_ms, applied_hints, rejected_hints = apply_hints(
            command, cwd, timeout_ms, experience_hints
        )
        # Collect env vars from applied hints
        for ah in applied_hints:
            if ah["kind"] == "set_env":
                env_overrides.update(ah["vars"])

    # Execute
    result = execute(command, cwd, timeout_ms, env_overrides if env_overrides else None)

    # Build runner-result-compatible output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    strategy = contract.get("strategy", {})
    payload = {
        "ts": now(),
        "goal": args.goal,
        "adapter": args.adapter,
        "command": command,
        "original_command": args.command,
        "cwd": cwd,
        "status": result["status"],
        "exit_code": result["exit_code"],
        "stdout": result["stdout"][:10000],
        "stderr": result["stderr"][:10000],
        "duration_ms": result["duration_ms"],
        "applied_rule_ids": [r.get("rule_id") for r in applied_rules],
        "applied_rule_layers": [r.get("layer") for r in applied_rules],
        "selected_pattern": selected_pattern.get("pattern_id"),
        "execution_contract": contract,
        "strategy": strategy,
        "executed_ordering": ["execute"],
        "stage_results": [{"step": "execute", "status": result["status"], "details": {
            "exit_code": result["exit_code"],
            "duration_ms": result["duration_ms"],
        }}],
        "experience_applied": applied_hints,
        "experience_rejected": rejected_hints,
    }

    if result["status"] == "ok":
        payload["result"] = {
            "summary": f"Shell command completed: exit {result['exit_code']}",
            "used_pattern_guidance": bool(selected_pattern),
            "used_rule_guidance": bool(applied_rules),
            "stage_count": 1,
        }

    if result["status"] == "failed":
        payload["error"] = result["stderr"][:500] or f"exit code {result['exit_code']}"

    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # Print status for orchestrator to capture
    out = {"status": result["status"], "output": str(output_path), "adapter": args.adapter}
    if result["status"] == "failed":
        print(json.dumps(out, sort_keys=True))
        raise SystemExit(result["stderr"][:200] or f"exit code {result['exit_code']}")
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
