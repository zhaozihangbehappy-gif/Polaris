#!/usr/bin/env python3
"""G4.1-G4.8 — Trialogue unified CLI tests.

Tests guard on/off, settings injection/removal, precompile, verification,
rollback on failure, and status output. Uses a temp directory for settings
to avoid modifying the real Claude Code config.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
TRIALOGUE = os.path.join(PARENT_DIR, "trialogue")

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL: {name} — {detail}")


def run_trialogue(args: list[str], cwd: str = "", env_extra: dict | None = None) -> subprocess.CompletedProcess:
    """Run the trialogue CLI with given args."""
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, TRIALOGUE] + args,
        capture_output=True, text=True, timeout=30,
        cwd=cwd or PARENT_DIR, env=env,
    )


# ── Setup temp environment ───────────────────────────────────────────────────

tmpdir = tempfile.mkdtemp(prefix="trialogue_cli_test_")

try:
    # Create a fake .claude dir to simulate project-level settings
    claude_dir = os.path.join(tmpdir, ".claude")
    os.makedirs(claude_dir, exist_ok=True)
    settings_path = os.path.join(claude_dir, "settings.json")

    # Write initial empty settings
    with open(settings_path, "w") as f:
        json.dump({"customKey": "preserve_me"}, f)

    # ── G4.1: guard on writes MCP + hooks ────────────────────────────────────

    result = run_trialogue(["guard", "on"], cwd=tmpdir)
    check("G4.1: guard on exit 0", result.returncode == 0,
          f"exit={result.returncode}, stderr={result.stderr[:200]}")

    settings = json.loads(open(settings_path).read())
    check("G4.1: MCP server added",
          "trialogue-guard" in settings.get("mcpServers", {}),
          f"mcpServers keys: {list(settings.get('mcpServers', {}).keys())}")

    # Hooks must be {"hooks": {"PreToolUse": [...]}} format
    hooks_obj = settings.get("hooks", {})
    check("G4.1: hooks is dict", isinstance(hooks_obj, dict),
          f"hooks type: {type(hooks_obj)}")
    pre_hooks = hooks_obj.get("PreToolUse", [])
    check("G4.1: PreToolUse has 3 entries", len(pre_hooks) >= 3,
          f"PreToolUse count: {len(pre_hooks)}")

    # Check hook IDs
    hook_ids = [h.get("_trialogue_id", "") for h in pre_hooks]
    check("G4.1: webfetch hook", "guard-webfetch" in hook_ids, f"hook_ids: {hook_ids}")
    check("G4.1: websearch hook", "guard-websearch" in hook_ids, f"hook_ids: {hook_ids}")
    check("G4.1: curl hook", "guard-curl" in hook_ids, f"hook_ids: {hook_ids}")

    # Verify matcher values match tool names (not event names)
    matchers = {h.get("matcher", "") for h in pre_hooks if h.get("_trialogue_id", "").startswith("guard-")}
    check("G4.1: matcher=WebFetch", "WebFetch" in matchers, f"matchers: {matchers}")
    check("G4.1: matcher=WebSearch", "WebSearch" in matchers, f"matchers: {matchers}")
    check("G4.1: matcher=Bash", "Bash" in matchers, f"matchers: {matchers}")

    # ── G4.8: Precompile ─────────────────────────────────────────────────────

    pycache = os.path.join(PARENT_DIR, "__pycache__")
    check("G4.8: __pycache__ exists", os.path.exists(pycache), f"path: {pycache}")
    if os.path.exists(pycache):
        pyc_files = [f for f in os.listdir(pycache) if f.endswith(".pyc")]
        check("G4.8: has .pyc files", len(pyc_files) > 0, f"files: {pyc_files}")

    # ── Guard on is idempotent ───────────────────────────────────────────────

    result = run_trialogue(["guard", "on"], cwd=tmpdir)
    check("guard on idempotent: exit 0", result.returncode == 0,
          f"exit={result.returncode}")
    check("guard on idempotent: already on message",
          "already ON" in result.stdout,
          f"stdout: {result.stdout[:200]}")

    # ── G4.2: guard off removes v4 config, preserves custom ─────────────────

    # Add a custom hook to PreToolUse that should survive guard off
    settings = json.loads(open(settings_path).read())
    settings["hooks"]["PreToolUse"].append({
        "matcher": "Edit",
        "hooks": [{"type": "command", "command": "echo custom"}],
        "_custom_id": "my-custom-hook",
    })
    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)

    result = run_trialogue(["guard", "off"], cwd=tmpdir)
    check("G4.2: guard off exit 0", result.returncode == 0,
          f"exit={result.returncode}, stderr={result.stderr[:200]}")

    settings = json.loads(open(settings_path).read())
    check("G4.2: MCP removed",
          "trialogue-guard" not in settings.get("mcpServers", {}),
          f"mcpServers: {list(settings.get('mcpServers', {}).keys())}")

    # Custom hook preserved in PreToolUse
    pre_hooks = settings.get("hooks", {}).get("PreToolUse", [])
    custom_found = any(h.get("_custom_id") == "my-custom-hook" for h in pre_hooks)
    check("G4.2: custom hook preserved", custom_found,
          f"PreToolUse hooks: {pre_hooks}")

    # Guard hooks removed
    guard_hooks = [h for h in pre_hooks if h.get("_trialogue_id", "").startswith("guard-")]
    check("G4.2: guard hooks removed", len(guard_hooks) == 0,
          f"guard hooks: {guard_hooks}")

    # Custom key preserved
    check("G4.2: customKey preserved", settings.get("customKey") == "preserve_me",
          f"customKey: {settings.get('customKey')}")

    # ── Guard off is idempotent ──────────────────────────────────────────────

    result = run_trialogue(["guard", "off"], cwd=tmpdir)
    check("guard off idempotent: exit 0", result.returncode == 0)
    check("guard off idempotent: already off message",
          "already OFF" in result.stdout,
          f"stdout: {result.stdout[:200]}")

    # ── G4.7: status output ──────────────────────────────────────────────────

    # Status when guard is off
    result = run_trialogue(["status"], cwd=tmpdir)
    check("G4.7: status exit 0", result.returncode == 0,
          f"exit={result.returncode}")
    check("G4.7: status shows OFF when off",
          "OFF" in result.stdout,
          f"stdout: {result.stdout[:200]}")

    # Turn guard on and check status
    run_trialogue(["guard", "on"], cwd=tmpdir)
    result = run_trialogue(["status"], cwd=tmpdir)
    check("G4.7: status shows ON when on",
          "ON" in result.stdout,
          f"stdout: {result.stdout[:200]}")
    check("G4.7: status shows hooks",
          "hook" in result.stdout.lower() or "Hook" in result.stdout,
          f"stdout: {result.stdout[:200]}")

    # Clean up for next tests
    run_trialogue(["guard", "off"], cwd=tmpdir)

    # ── B2: allowlist conflict detection ─────────────────────────────────────

    # Reset: guard off first
    run_trialogue(["guard", "off"], cwd=tmpdir)

    # Create settings with WebFetch in allowlist
    conflict_settings = {
        "permissions": {"allow": ["WebFetch", "Read", "Edit"]},
    }
    with open(settings_path, "w") as f:
        json.dump(conflict_settings, f, indent=2)

    # guard on should FAIL (non-zero) due to allowlist conflict
    result = run_trialogue(["guard", "on"], cwd=tmpdir)
    check("B2: guard on fails with allowlist conflict", result.returncode != 0,
          f"exit={result.returncode}, stdout={result.stdout[:300]}")
    check("B2: error mentions WebFetch",
          "WebFetch" in result.stdout,
          f"stdout: {result.stdout[:300]}")
    check("B2: error mentions --fix",
          "--fix" in result.stdout,
          f"stdout: {result.stdout[:300]}")

    # Verify settings were NOT modified (no MCP added since guard on failed)
    after_fail = json.loads(open(settings_path).read())
    check("B2: no MCP after failed guard on",
          "trialogue-guard" not in after_fail.get("mcpServers", {}),
          f"mcpServers: {list(after_fail.get('mcpServers', {}).keys())}")

    # guard on --fix should succeed: removes conflict, then enables guard
    result = run_trialogue(["guard", "on", "--fix"], cwd=tmpdir)
    check("B2: guard on --fix exit 0", result.returncode == 0,
          f"exit={result.returncode}, stdout={result.stdout[:300]}, stderr={result.stderr[:300]}")

    # Verify WebFetch removed from allowlist
    fixed_settings = json.loads(open(settings_path).read())
    allow_list = fixed_settings.get("permissions", {}).get("allow", [])
    check("B2: WebFetch removed from allowlist", "WebFetch" not in allow_list,
          f"allow: {allow_list}")
    # Other tools preserved
    check("B2: Read preserved in allowlist", "Read" in allow_list,
          f"allow: {allow_list}")
    check("B2: Edit preserved in allowlist", "Edit" in allow_list,
          f"allow: {allow_list}")
    # Guard is now on
    check("B2: MCP added after --fix",
          "trialogue-guard" in fixed_settings.get("mcpServers", {}),
          f"mcpServers: {list(fixed_settings.get('mcpServers', {}).keys())}")

    # No conflict → guard on works without --fix
    run_trialogue(["guard", "off"], cwd=tmpdir)
    # Rewrite settings without conflicting tools
    clean_settings = {"permissions": {"allow": ["Read", "Edit"]}}
    with open(settings_path, "w") as f:
        json.dump(clean_settings, f, indent=2)
    result = run_trialogue(["guard", "on"], cwd=tmpdir)
    check("B2: no conflict → guard on succeeds", result.returncode == 0,
          f"exit={result.returncode}, stderr={result.stderr[:200]}")

    # Clean up
    run_trialogue(["guard", "off"], cwd=tmpdir)

    # ── C1: --egress flag (non-root → pattern_only, MCP not rewritten) ──────

    run_trialogue(["guard", "off"], cwd=tmpdir)
    with open(settings_path, "w") as f:
        json.dump({}, f)

    result = run_trialogue(["guard", "on", "--egress"], cwd=tmpdir)
    check("C1: guard on --egress exit 0 (non-root degrades)", result.returncode == 0,
          f"exit={result.returncode}, stderr={result.stderr[:200]}")
    check("C1: output mentions pattern",
          "pattern" in result.stdout.lower(),
          f"stdout: {result.stdout[:300]}")

    # Verify MCP config is NOT rewritten to sudo (no root → no kernel mode)
    settings = json.loads(open(settings_path).read())
    mcp_config = settings.get("mcpServers", {}).get("trialogue-guard", {})
    check("C1: MCP command is python (not sudo) without root",
          mcp_config.get("command", "") != "sudo",
          f"mcp_config: {mcp_config}")

    # The full chain for root + kernel mode is:
    #   1. enable_egress() creates _trialogue user + iptables rules
    #   2. ensure_sudoers() writes NOPASSWD rule
    #   3. _build_mcp_config(as_trialogue_user=True) → command="sudo"
    #   4. _verify_mcp(mcp_config=new_config) verifies sudo launch works
    #   5. If step 4 fails → rollback to pattern_only + restore MCP config
    # Steps 1-5 require root so we can't test end-to-end here.
    # egress_test.py root branch covers steps 1-3.
    # The re-verify logic (step 4-5) is structural — tested by code inspection.

    run_trialogue(["guard", "off"], cwd=tmpdir)

    # ── Usage help ───────────────────────────────────────────────────────────

    result = run_trialogue([])
    check("no args: shows usage", result.returncode == 2,
          f"exit={result.returncode}")
    check("no args: shows help text", "guard" in result.stdout.lower(),
          f"stdout: {result.stdout[:200]}")

    result = run_trialogue(["guard"])
    check("guard no subcommand: exit 2", result.returncode == 2,
          f"exit={result.returncode}")

    # ── Unknown command ──────────────────────────────────────────────────────

    result = run_trialogue(["foo"])
    check("unknown cmd: exit 2", result.returncode == 2,
          f"exit={result.returncode}")

finally:
    shutil.rmtree(tmpdir, ignore_errors=True)

# ── Summary ──────────────────────────────────────────────────────────────────

print(f"trialogue_cli_test: {passed}/{passed + failed} passed, {failed} failed")
sys.exit(1 if failed else 0)
