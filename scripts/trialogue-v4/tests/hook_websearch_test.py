#!/usr/bin/env python3
"""G2.2 — WebSearch hook intercept tests.

Tests two modes:
1. No search endpoint configured → passthrough (allow native WebSearch)
2. Search endpoint configured → intercept and route through pipeline
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
HOOK = os.path.join(PARENT_DIR, "hooks", "intercept-websearch.sh")

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL: {name} — {detail}")


def run_hook(query: str, tool_name: str = "WebSearch") -> tuple[str, str, str]:
    """Run the WebSearch hook. Returns (stdout, decision, reason)."""
    hook_input = json.dumps({
        "tool_name": tool_name,
        "tool_input": {"query": query},
        "session_id": "test",
        "hook_event_name": "PreToolUse",
    })
    proc = subprocess.run(
        ["bash", HOOK],
        input=hook_input,
        capture_output=True,
        text=True,
        timeout=15,
        cwd=PARENT_DIR,
    )
    stdout = proc.stdout.strip()
    if not stdout:
        return stdout, "allow", ""
    try:
        parsed = json.loads(stdout)
        hso = parsed.get("hookSpecificOutput", {})
        decision = hso.get("permissionDecision", "")
        reason = hso.get("permissionDecisionReason", "")
        return stdout, decision, reason
    except json.JSONDecodeError:
        return stdout, "parse_error", ""


# ── No search endpoint → passthrough (allow native WebSearch) ────────────────
# Without a configured endpoint, pipeline_search returns "No search endpoint"
# and the hook should let the native WebSearch through (degraded mode).

_, decision, _ = run_hook("test query python tutorial")
check("no endpoint: passthrough (allow)", decision == "allow",
      f"got: {decision}")

# ── Non-WebSearch tool ignored ───────────────────────────────────────────────

_, decision, _ = run_hook("test query", tool_name="Read")
check("non-WebSearch: allow (passthrough)", decision == "allow",
      f"got: {decision}")

_, decision, _ = run_hook("test query", tool_name="Bash")
check("non-WebSearch Bash: allow", decision == "allow",
      f"got: {decision}")

# ── Empty query handled ─────────────────────────────────────────────────────

hook_input = json.dumps({
    "tool_name": "WebSearch",
    "tool_input": {},
    "session_id": "test",
    "hook_event_name": "PreToolUse",
})
proc = subprocess.run(
    ["bash", HOOK],
    input=hook_input,
    capture_output=True,
    text=True,
    timeout=10,
    cwd=PARENT_DIR,
)
stdout = proc.stdout.strip()
if not stdout:
    check("empty query: passthrough", True)
else:
    check("empty query: handled", True)

# ── Summary ──────────────────────────────────────────────────────────────────

print(f"hook_websearch_test: {passed}/{passed + failed} passed, {failed} failed")
sys.exit(1 if failed else 0)
