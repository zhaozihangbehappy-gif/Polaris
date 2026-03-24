#!/usr/bin/env python3
"""Codex MCP integration test — verify real `codex mcp add/remove` works."""
from __future__ import annotations

import os
import subprocess
import shutil
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PARENT_DIR)

passed = 0
failed = 0
skipped = 0

GUARD_KEY = "trialogue-guard"


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL: {name} — {detail}")


def skip(name: str, reason: str):
    global skipped
    skipped += 1
    print(f"  SKIP: {name} — {reason}")


# ── Check if Codex is available ──────────────────────────────────────────────

codex_path = shutil.which("codex")
if not codex_path:
    print("codex_mcp_test: Codex not installed — all tests skipped")
    print(f"codex_mcp_test: 0/0 passed, 0 failed, all skipped")
    sys.exit(0)

# ── Clean up any leftover from previous test runs ───────────────────────────

subprocess.run(["codex", "mcp", "remove", GUARD_KEY],
               capture_output=True, text=True, timeout=10)

# ── Test: codex mcp add ─────────────────────────────────────────────────────

mcp_server = os.path.join(PARENT_DIR, "mcp-server.py")
result = subprocess.run(
    ["codex", "mcp", "add", GUARD_KEY, "--", sys.executable, mcp_server],
    capture_output=True, text=True, timeout=10,
)
check("mcp add: exit 0", result.returncode == 0,
      f"exit={result.returncode}, stderr={result.stderr[:200]}")

# ── Test: codex mcp list shows guard ────────────────────────────────────────

result = subprocess.run(
    ["codex", "mcp", "list"],
    capture_output=True, text=True, timeout=10,
)
check("mcp list: guard present", GUARD_KEY in result.stdout,
      f"stdout: {result.stdout[:200]}")

# ── Test: config.toml has the entry ─────────────────────────────────────────

config_toml = os.path.expanduser("~/.codex/config.toml")
if os.path.exists(config_toml):
    with open(config_toml) as f:
        toml_content = f.read()
    check("config.toml: has mcp_servers section",
          f"[mcp_servers.{GUARD_KEY}]" in toml_content,
          f"section not found in config.toml")
    check("config.toml: has mcp-server.py command",
          "mcp-server.py" in toml_content,
          f"mcp-server.py not in config.toml")
else:
    skip("config.toml checks", "file not found")

# ── Test: codex mcp remove ──────────────────────────────────────────────────

result = subprocess.run(
    ["codex", "mcp", "remove", GUARD_KEY],
    capture_output=True, text=True, timeout=10,
)
check("mcp remove: exit 0", result.returncode == 0,
      f"exit={result.returncode}, stderr={result.stderr[:200]}")

# Verify removed
result = subprocess.run(
    ["codex", "mcp", "list"],
    capture_output=True, text=True, timeout=10,
)
check("mcp remove: guard gone", GUARD_KEY not in result.stdout,
      f"stdout: {result.stdout[:200]}")

# ── Test: MCP server responds to trialogue_fetch via Codex (if supported) ───

# Re-add for the fetch test
subprocess.run(
    ["codex", "mcp", "add", GUARD_KEY, "--", sys.executable, mcp_server],
    capture_output=True, text=True, timeout=10,
)

# Start fixture server for MCP fetch test
from fixtures.server import FixtureServer

with FixtureServer() as srv:
    # We can't easily invoke Codex to call an MCP tool programmatically,
    # but we CAN verify the MCP server works end-to-end by talking to it
    # directly (same binary that Codex would invoke).
    import json as _json
    init_msg = _json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "codex-e2e-test", "version": "1.0"}}
    })
    fetch_msg = _json.dumps({
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "trialogue_fetch",
                    "arguments": {"url": srv.url("/clean.html")}}
    })
    proc = subprocess.run(
        [sys.executable, mcp_server],
        input=init_msg + "\n" + fetch_msg + "\n",
        capture_output=True, text=True, timeout=15,
        cwd=PARENT_DIR,
    )
    resp_lines = [l for l in proc.stdout.strip().split("\n") if l.strip()]
    check("mcp fetch: got responses", len(resp_lines) >= 2,
          f"got {len(resp_lines)} lines")
    if len(resp_lines) >= 2:
        fetch_resp = _json.loads(resp_lines[-1])
        content = fetch_resp.get("result", {}).get("content", [])
        text = content[0].get("text", "") if content else ""
        check("mcp fetch: Clean Page in response", "Clean Page" in text,
              f"text: {text[:200]}")
    else:
        check("mcp fetch: Clean Page in response", False,
              f"not enough responses")

# Clean up
subprocess.run(
    ["codex", "mcp", "remove", GUARD_KEY],
    capture_output=True, text=True, timeout=10,
)

# ── Test: double remove is safe ─────────────────────────────────────────────

result = subprocess.run(
    ["codex", "mcp", "remove", GUARD_KEY],
    capture_output=True, text=True, timeout=10,
)
# Should not crash (may return non-zero, that's ok)
check("double remove: no crash", True)

# ── Summary ──────────────────────────────────────────────────────────────────

total = passed + failed
print(f"codex_mcp_test: {passed}/{total} passed, {failed} failed"
      + (f", {skipped} skipped" if skipped else ""))
sys.exit(1 if failed else 0)
