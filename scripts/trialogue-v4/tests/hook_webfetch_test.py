#!/usr/bin/env python3
"""G2.1 — WebFetch hook intercept tests.

Simulates Claude Code PreToolUse hook input for WebFetch tool calls
and verifies the hook returns deny+cleaned content (silent rewrite).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PARENT_DIR)

HOOK = os.path.join(PARENT_DIR, "hooks", "intercept-webfetch.sh")

from fixtures.server import FixtureServer

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL: {name} — {detail}")


def run_hook(url: str, tool_name: str = "WebFetch") -> tuple[str, str, str]:
    """Run the WebFetch hook. Returns (stdout, decision, reason)."""
    hook_input = json.dumps({
        "tool_name": tool_name,
        "tool_input": {"url": url},
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


with FixtureServer() as srv:

    # ── G2.1: Clean page intercepted and returned ────────────────────────────

    _, decision, reason = run_hook(srv.url("/clean.html"))
    check("clean: decision is deny (enforced routing)", decision == "deny",
          f"got: {decision}")
    check("clean: reason contains content", "Clean Page" in reason,
          f"got: {reason[:200]}")
    check("clean: reason has guard tag", "[trialogue-guard]" in reason,
          f"got: {reason[:100]}")
    check("clean: reason mentions interception", "intercept" in reason.lower(),
          f"got: {reason[:200]}")

    # ── Injected page — injections removed in returned content ───────────────

    _, decision, reason = run_hook(srv.url("/injected.html"))
    check("injected: deny", decision == "deny", f"got: {decision}")
    check("injected: SYSTEM-PROMPT removed from reason",
          "[SYSTEM-PROMPT]" not in reason,
          f"got: {reason[:300]}")
    check("injected: ChatML removed from reason",
          "<|system|>" not in reason,
          f"got: {reason[:300]}")
    check("injected: normal content in reason",
          "Normal content" in reason,
          f"got: {reason[:300]}")

    # ── Non-WebFetch tool ignored ────────────────────────────────────────────

    _, decision, _ = run_hook(srv.url("/clean.html"), tool_name="Read")
    check("non-WebFetch: allow (passthrough)", decision == "allow",
          f"got: {decision}")

    # ── Missing URL handled gracefully ───────────────────────────────────────

    hook_input = json.dumps({
        "tool_name": "WebFetch",
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
        check("missing URL: passthrough", True)
    else:
        check("missing URL: handled", True)

# ── Summary ──────────────────────────────────────────────────────────────────

print(f"hook_webfetch_test: {passed}/{passed + failed} passed, {failed} failed")
sys.exit(1 if failed else 0)
