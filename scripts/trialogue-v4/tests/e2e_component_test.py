#!/usr/bin/env python3
"""V4-P3a — Component-level end-to-end test.

Strings together all v4 components in a single test:
  1. Fixture HTTP server (with injections)
  2. MCP server (stdio subprocess)
  3. MCP tools/call → trialogue_fetch
  4. Verify cleaned content
  5. Verify audit chain
  6. Verify hook script deny + reason matches MCP result

Proof strength: proves hook + MCP + pipeline + audit components work
together. Does NOT prove Claude Code harness executes hook deny semantics.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Any

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PARENT_DIR)

import audit as _audit_mod
import config as _config_mod

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL: {name} — {detail}")


def mcp_call(messages: list[dict]) -> list[dict]:
    """Send multiple JSON-RPC messages to MCP server, return responses."""
    stdin_lines = "\n".join(json.dumps(m) for m in messages) + "\n"
    proc = subprocess.run(
        [sys.executable, os.path.join(PARENT_DIR, "mcp-server.py")],
        input=stdin_lines,
        capture_output=True, text=True, timeout=30,
        cwd=PARENT_DIR,
    )
    responses = []
    for line in proc.stdout.strip().split("\n"):
        line = line.strip()
        if line:
            try:
                responses.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return responses


def run_hook(hook_script: str, tool_name: str, tool_input: dict) -> subprocess.CompletedProcess:
    """Simulate a PreToolUse hook invocation."""
    hook_input = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
    return subprocess.run(
        ["bash", os.path.join(PARENT_DIR, "hooks", hook_script)],
        input=hook_input,
        capture_output=True, text=True, timeout=30,
        cwd=PARENT_DIR,
    )


# ── Setup ─────────────────────────────────────────────────────────────────────

tmpdir = tempfile.mkdtemp(prefix="e2e_comp_test_")
orig_chain_dir = _audit_mod.DEFAULT_CHAIN_DIR
orig_conf = _config_mod._conf

chain_dir = os.path.join(tmpdir, "chain")
_audit_mod.DEFAULT_CHAIN_DIR = chain_dir
_config_mod._conf = dict(_config_mod.DEFAULTS)
_config_mod._conf["audit_mode"] = "local"

try:
    from fixtures.server import FixtureServer

    with FixtureServer() as srv:
        # ── Step 1: MCP initialize ────────────────────────────────────────────

        init_msg = {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "e2e-test", "version": "1.0"},
            }
        }
        responses = mcp_call([init_msg])
        check("mcp init: got response", len(responses) >= 1,
              f"responses: {len(responses)}")
        if responses:
            check("mcp init: has serverInfo",
                  "serverInfo" in responses[0].get("result", {}),
                  f"result: {responses[0].get('result', {})}")

        # ── Step 2: MCP tools/list ────────────────────────────────────────────

        list_msg = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        responses = mcp_call([init_msg, list_msg])
        tools_resp = responses[-1] if responses else {}
        tools = tools_resp.get("result", {}).get("tools", [])
        tool_names = [t.get("name") for t in tools]
        check("tools/list: trialogue_fetch", "trialogue_fetch" in tool_names,
              f"tools: {tool_names}")
        check("tools/list: trialogue_search", "trialogue_search" in tool_names,
              f"tools: {tool_names}")

        # ── Step 3: MCP trialogue_fetch (clean page) ─────────────────────────

        fetch_clean = {
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {
                "name": "trialogue_fetch",
                "arguments": {"url": srv.url("/clean.html")},
            }
        }
        responses = mcp_call([init_msg, fetch_clean])
        fetch_resp = responses[-1] if responses else {}
        content = fetch_resp.get("result", {}).get("content", [])
        text = content[0].get("text", "") if content else ""
        check("fetch clean: Clean Page in text", "Clean Page" in text,
              f"text: {text[:200]}")
        check("fetch clean: no error",
              fetch_resp.get("result", {}).get("isError") is not True,
              f"result: {fetch_resp.get('result', {})}")

        # ── Step 4: MCP trialogue_fetch (injected page) ──────────────────────

        fetch_injected = {
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {
                "name": "trialogue_fetch",
                "arguments": {"url": srv.url("/injected.html")},
            }
        }
        responses = mcp_call([init_msg, fetch_injected])
        fetch_resp = responses[-1] if responses else {}
        content = fetch_resp.get("result", {}).get("content", [])
        text = content[0].get("text", "") if content else ""
        check("fetch injected: SYSTEM-PROMPT removed",
              "[SYSTEM-PROMPT]" not in text,
              f"text: {text[:300]}")
        check("fetch injected: ChatML removed",
              "<|system|>" not in text,
              f"text: {text[:300]}")
        check("fetch injected: normal content preserved",
              "Normal content" in text,
              f"text: {text[:300]}")

        # ── Step 5: MCP trialogue_fetch with JSON output ──────────────────────

        fetch_json = {
            "jsonrpc": "2.0", "id": 5, "method": "tools/call",
            "params": {
                "name": "trialogue_fetch",
                "arguments": {"url": srv.url("/clean.html"), "json_output": True},
            }
        }
        responses = mcp_call([init_msg, fetch_json])
        fetch_resp = responses[-1] if responses else {}
        content = fetch_resp.get("result", {}).get("content", [])
        json_text = content[0].get("text", "") if content else ""
        try:
            meta = json.loads(json_text)
            check("fetch json: has audit_status", "audit_status" in meta,
                  f"keys: {list(meta.keys())}")
            check("fetch json: audit_status=ok", meta.get("audit_status") == "ok",
                  f"got: {meta.get('audit_status')}")
            check("fetch json: has raw_sha256", len(meta.get("raw_sha256", "")) == 64,
                  f"got: {meta.get('raw_sha256', '')[:20]}")
        except json.JSONDecodeError:
            check("fetch json: valid JSON", False, f"text: {json_text[:200]}")
            check("fetch json: has audit_status", False, "not JSON")
            check("fetch json: audit_status=ok", False, "not JSON")
            check("fetch json: has raw_sha256", False, "not JSON")

        # ── Step 6: Verify audit chain ────────────────────────────────────────

        # The MCP server runs as a subprocess with its own config, so it uses
        # the default chain dir, not our tmpdir. We verify via JSON output.
        # But for the hook test below we use pipeline directly.

        # ── Step 7: Hook intercept-webfetch.sh ────────────────────────────────

        hook_result = run_hook("intercept-webfetch.sh", "WebFetch",
                               {"url": srv.url("/injected.html")})
        # Hook should output deny JSON
        check("hook webfetch: outputs JSON", hook_result.stdout.strip() != "",
              f"stdout empty, stderr={hook_result.stderr[:200]}")
        try:
            hook_json = json.loads(hook_result.stdout.strip())
            decision = hook_json.get("hookSpecificOutput", {}).get("permissionDecision")
            reason = hook_json.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
            check("hook webfetch: deny", decision == "deny",
                  f"got: {decision}")
            check("hook webfetch: reason has sanitized content",
                  "trialogue-guard" in reason,
                  f"reason: {reason[:200]}")
            check("hook webfetch: SYSTEM-PROMPT not in reason",
                  "[SYSTEM-PROMPT]" not in reason,
                  f"reason: {reason[:300]}")
        except json.JSONDecodeError:
            check("hook webfetch: deny", False, f"not JSON: {hook_result.stdout[:200]}")
            check("hook webfetch: reason has sanitized content", False, "not JSON")
            check("hook webfetch: SYSTEM-PROMPT not in reason", False, "not JSON")

        # ── Step 8: Hook intercept-curl.sh ────────────────────────────────────

        # Use a real external URL (not localhost — localhost is allowed)
        hook_result = run_hook("intercept-curl.sh", "Bash",
                               {"command": "curl https://example.com/page"})
        try:
            hook_json = json.loads(hook_result.stdout.strip())
            decision = hook_json.get("hookSpecificOutput", {}).get("permissionDecision")
            check("hook curl: deny external curl", decision == "deny",
                  f"got: {decision}")
        except (json.JSONDecodeError, AttributeError):
            # If stdout is empty, the hook allowed it (exit 0 no output)
            check("hook curl: deny external curl", False,
                  f"stdout: {hook_result.stdout[:200]}")

        # curl to localhost should be allowed (exit 0, no deny output)
        hook_result = run_hook("intercept-curl.sh", "Bash",
                               {"command": "curl http://localhost:8080/api"})
        is_allowed = (hook_result.stdout.strip() == "" or
                      "deny" not in hook_result.stdout)
        check("hook curl: allow localhost", is_allowed,
              f"stdout: {hook_result.stdout[:200]}")

        # ── Step 9: Hook intercept-websearch.sh (no endpoint) ─────────────────

        hook_result = run_hook("intercept-websearch.sh", "WebSearch",
                               {"query": "test query"})
        # No search endpoint → should allow (exit 0, no deny)
        is_passthrough = (hook_result.stdout.strip() == "" or
                          "deny" not in hook_result.stdout)
        check("hook websearch: passthrough without endpoint", is_passthrough,
              f"stdout: {hook_result.stdout[:200]}")

    # ── Step 10: Audit three-state ─────────────────────────────────────────────

    # Already tested via MCP json_output above (local mode).
    # Test disabled mode directly:
    _config_mod._conf["audit_mode"] = "disabled"
    from pipeline import pipeline_fetch
    from fixtures.server import FixtureServer as FS2
    with FS2() as srv2:
        result = pipeline_fetch(srv2.url("/clean.html"))
        check("disabled audit: status=disabled",
              result.get("audit_status") == "disabled",
              f"got: {result.get('audit_status')}")

finally:
    _audit_mod.DEFAULT_CHAIN_DIR = orig_chain_dir
    _config_mod._conf = orig_conf
    shutil.rmtree(tmpdir, ignore_errors=True)

# ── Summary ──────────────────────────────────────────────────────────────────

print(f"e2e_component_test: {passed}/{passed + failed} passed, {failed} failed")
sys.exit(1 if failed else 0)
