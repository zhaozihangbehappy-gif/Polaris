#!/usr/bin/env python3
"""V4-C1 — Egress control tests.

Tests the egress.py module's user management, iptables rule logic,
status reporting, and degradation behavior. Since tests typically run
without root, most tests verify the pattern_only fallback path.
"""
from __future__ import annotations

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PARENT_DIR)

import egress

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL: {name} — {detail}")


# ── Module constants ──────────────────────────────────────────────────────────

check("TRIALOGUE_USER defined", egress.TRIALOGUE_USER == "_trialogue",
      f"got: {egress.TRIALOGUE_USER}")
check("CHAIN_NAME defined", egress.CHAIN_NAME == "TRIALOGUE_EGRESS",
      f"got: {egress.CHAIN_NAME}")
check("CONTROLLED_PORTS has 80", 80 in egress.CONTROLLED_PORTS,
      f"got: {egress.CONTROLLED_PORTS}")
check("CONTROLLED_PORTS has 443", 443 in egress.CONTROLLED_PORTS,
      f"got: {egress.CONTROLLED_PORTS}")
check("SUDOERS_FILE defined", egress.SUDOERS_FILE == "/etc/sudoers.d/trialogue-guard",
      f"got: {egress.SUDOERS_FILE}")

# ── Status reports current state ──────────────────────────────────────────────

status = egress.get_status()
check("status: has egress_mode", "egress_mode" in status,
      f"keys: {list(status.keys())}")
check("status: has user_exists", "user_exists" in status,
      f"keys: {list(status.keys())}")
check("status: has has_root", "has_root" in status,
      f"keys: {list(status.keys())}")
check("status: has iptables_available", "iptables_available" in status,
      f"keys: {list(status.keys())}")

# ── Enable without root → pattern_only ────────────────────────────────────────

has_root = os.geteuid() == 0

if not has_root:
    mode, msg = egress.enable_egress()
    check("no root: falls back to pattern_only", mode == "pattern_only",
          f"mode={mode}, msg={msg}")
    check("no root: message mentions root", "root" in msg.lower() or "pattern" in msg.lower(),
          f"msg={msg}")

    # Disable without root
    ok, msg = egress.disable_egress()
    check("no root: disable reports root needed", not ok or "not available" in msg.lower(),
          f"ok={ok}, msg={msg}")

    # ensure_sudoers without root → fails
    ok, msg = egress.ensure_sudoers()
    check("no root: sudoers fails", not ok,
          f"ok={ok}, msg={msg}")

    # _install_iptables without root → fails
    ok, msg = egress._install_iptables()
    # Either already installed (ok=True) or fails without root
    check("no root: install either succeeds (already there) or fails gracefully",
          isinstance(ok, bool) and isinstance(msg, str),
          f"ok={ok}, msg={msg}")
else:
    # WITH root — actually test iptables rules
    # Enable
    mode, msg = egress.enable_egress()
    check("root: mode is kernel or pattern_only", mode in ("kernel", "pattern_only"),
          f"mode={mode}")

    if mode == "kernel":
        check("root: kernel msg mentions trialogue", "_trialogue" in msg,
              f"msg={msg}")

        # Status should show kernel
        status = egress.get_status()
        check("root: status shows kernel", status.get("egress_mode") == "kernel",
              f"status={status}")
        check("root: chain exists", status.get("chain_exists") == "yes",
              f"status={status}")

        # MCP config must use sudo -u _trialogue in kernel mode
        prefix = egress.mcp_command_prefix()
        check("root+kernel: mcp_prefix is sudo wrapper",
              prefix == ["sudo", "-u", "_trialogue"],
              f"got: {prefix}")

        # Sudoers rule must exist for kernel mode
        ok, msg = egress.ensure_sudoers()
        check("root+kernel: sudoers created", ok, f"msg={msg}")
        check("root+kernel: sudoers file exists",
              os.path.exists(egress.SUDOERS_FILE),
              f"file: {egress.SUDOERS_FILE}")

        # Verify iptables rules actually list the _trialogue UID
        uid = egress._get_uid("_trialogue")
        verify = subprocess.run(
            ["iptables", "-n", "-L", egress.CHAIN_NAME],
            capture_output=True, text=True, timeout=5,
        )
        check("root+kernel: rules mention owner match",
              str(uid) in verify.stdout or "owner" in verify.stdout.lower(),
              f"iptables output: {verify.stdout[:300]}")

        # Disable
        ok, msg = egress.disable_egress()
        check("root: disable ok", ok, f"msg={msg}")

        # Status after disable
        status = egress.get_status()
        check("root: chain gone after disable", status.get("chain_exists") == "no",
              f"status={status}")

# ── MCP command prefix ────────────────────────────────────────────────────────

prefix = egress.mcp_command_prefix()
if egress._user_exists("_trialogue"):
    check("mcp_prefix: sudo -u _trialogue when user exists",
          prefix == ["sudo", "-u", "_trialogue"],
          f"got: {prefix}")
else:
    check("mcp_prefix: empty when no user", prefix == [],
          f"got: {prefix}")

# ── MCP config rewrite invariant ──────────────────────────────────────────────

# The critical invariant: if _trialogue user exists AND egress is kernel mode,
# the MCP server MUST run as _trialogue, not as the current user.
# mcp_command_prefix() is the bridge — trialogue CLI uses it (via _build_mcp_config)
# to rewrite the MCP config command to "sudo -u _trialogue python3 mcp-server.py".

if egress._user_exists("_trialogue"):
    prefix = egress.mcp_command_prefix()
    check("mcp config invariant: _trialogue user → sudo prefix",
          prefix == ["sudo", "-u", "_trialogue"],
          f"got: {prefix}")
else:
    check("mcp config invariant: no user → empty prefix",
          egress.mcp_command_prefix() == [],
          f"got: {egress.mcp_command_prefix()}")

# trialogue_cli_test.py verifies the actual settings.json content
# when --egress is used (non-root → no sudo; root → sudo -u _trialogue).

# ── CLI entry point ───────────────────────────────────────────────────────────

import subprocess

result = subprocess.run(
    [sys.executable, os.path.join(PARENT_DIR, "egress.py"), "status"],
    capture_output=True, text=True, timeout=10,
)
check("CLI status: exit 0", result.returncode == 0,
      f"exit={result.returncode}, stderr={result.stderr[:200]}")
check("CLI status: shows egress_mode", "egress_mode" in result.stdout,
      f"stdout={result.stdout[:200]}")

result = subprocess.run(
    [sys.executable, os.path.join(PARENT_DIR, "egress.py")],
    capture_output=True, text=True, timeout=10,
)
check("CLI no args: exit 2", result.returncode == 2,
      f"exit={result.returncode}")

# ── Summary ──────────────────────────────────────────────────────────────────

print(f"egress_test: {passed}/{passed + failed} passed, {failed} failed")
sys.exit(1 if failed else 0)
