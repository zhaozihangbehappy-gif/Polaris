#!/usr/bin/env bash
# Trialogue v4 — PreToolUse hook: intercept WebSearch
#
# If a search endpoint is configured, routes through the sanitizing pipeline.
# If no search endpoint is configured, ALLOWS the native WebSearch to proceed
# (degraded mode — no sanitization, but search still works).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIPELINE="$(dirname "$SCRIPT_DIR")/pipeline.py"

# Read stdin
INPUT=$(cat)

TOOL_NAME=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null || echo "")

# Only intercept WebSearch
if [ "$TOOL_NAME" != "WebSearch" ]; then
    exit 0
fi

# Extract query from tool_input
QUERY=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('query',''))" 2>/dev/null || echo "")

if [ -z "$QUERY" ]; then
    exit 0
fi

# Check if search endpoint is configured by running a probe
# pipeline_search without endpoint returns "No search endpoint configured" — detect this
set +e
RESULT=$(python3 "$PIPELINE" search "$QUERY" 2>/dev/null)
PIPE_EXIT=$?
set -e

# If the result contains the "no endpoint" message, let native WebSearch through
if echo "$RESULT" | grep -q "No search endpoint configured"; then
    # No search endpoint — allow native WebSearch (degraded: no sanitization)
    exit 0
fi

if [ "$PIPE_EXIT" -ge 2 ]; then
    # Pipeline error — allow native WebSearch as fallback
    exit 0
fi

# Endpoint configured and working — return sanitized results
python3 -c "
import json, sys
cleaned = sys.stdin.read()
print(json.dumps({
    'hookSpecificOutput': {
        'hookEventName': 'PreToolUse',
        'permissionDecision': 'deny',
        'permissionDecisionReason': '[trialogue-guard] WebSearch intercepted. Results fetched and sanitized via security pipeline. For seamless access, use trialogue_search MCP tool.\n\n--- Sanitized results ---\n\n' + cleaned
    }
}))
" <<< "$RESULT"
