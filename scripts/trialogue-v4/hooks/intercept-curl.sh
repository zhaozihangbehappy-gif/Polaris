#!/usr/bin/env bash
# Trialogue v4 — PreToolUse hook: intercept curl/wget in Bash commands
#
# Blocks curl/wget commands that fetch external content into agent context.
#
# Allow conditions (any match → allow):
#   1. No curl/wget/Invoke-WebRequest → not a network command
#   2. POST/PUT/PATCH/DELETE method → API call (sending, not ingesting)
#   3. -d/--data/--data-raw/--data-binary/--json → has request body (API call)
#   4. localhost/127.0.0.1/::1 target → local service
#
# Block conditions (even with pipes or -o):
#   - curl to external URL → blocked (agent can chain -o + cat, or pipe + print)
#   - wget to external URL → blocked
#
# Auth headers alone do NOT allow — authenticated GET still ingests content.
# -o/--output alone does NOT allow — agent can read the file in a follow-up.
# Pipe to processor does NOT allow — agent can pipe to `python3 -c 'print(sys.stdin.read())'`.

set -euo pipefail

# Read stdin
INPUT=$(cat)

TOOL_NAME=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null || echo "")

# Only intercept Bash
if [ "$TOOL_NAME" != "Bash" ]; then
    exit 0
fi

# Extract command
COMMAND=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null || echo "")

if [ -z "$COMMAND" ]; then
    exit 0
fi

# Check if command contains curl, wget, or Invoke-WebRequest
echo "$COMMAND" | grep -qiE '\b(curl|wget|Invoke-WebRequest)\b' || exit 0

# ── Allow conditions ─────────────────────────────────────────────────────

# 2. HTTP method other than GET (sending data, not ingesting)
echo "$COMMAND" | grep -qiE -- '-X\s*(POST|PUT|PATCH|DELETE)' && exit 0

# 3. Request body (API call pattern)
echo "$COMMAND" | grep -qiE -- '(-d\s|--data\b|--data-raw\b|--data-binary\b|--json\b)' && exit 0

# 4. Localhost targets (local service communication)
echo "$COMMAND" | grep -qiE -- '(localhost|127\.0\.0\.1|\[::1\]|0\.0\.0\.0)' && exit 0

# ── Everything else is blocked ───────────────────────────────────────────
# This includes:
# - Simple GET: curl https://external.com
# - GET with auth: curl -H "Authorization: ..." https://external.com
# - GET to file: curl -o file.html https://external.com
# - GET piped: curl https://external.com | python3 ...
# All of these ingest external content that bypasses sanitization.

python3 -c "
import json
print(json.dumps({
    'hookSpecificOutput': {
        'hookEventName': 'PreToolUse',
        'permissionDecision': 'deny',
        'permissionDecisionReason': '[trialogue-guard] Direct curl/wget content ingestion blocked. External content must go through the security pipeline. Use trialogue_fetch MCP tool instead.'
    }
}))
"
