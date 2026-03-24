#!/usr/bin/env bash
# Trialogue v4 — PreToolUse hook: intercept WebFetch
#
# Blocks direct WebFetch calls and routes them through the sanitizing pipeline.
# The agent sees the cleaned content in the deny reason, plus a notice that
# the content was fetched via the security pipeline. The agent CAN tell this
# was intercepted (Claude Code hooks cannot do transparent result substitution).
#
# This is "enforced routing", not "silent rewrite". The agent is guided to
# use trialogue_fetch MCP tool for a seamless experience.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIPELINE="$(dirname "$SCRIPT_DIR")/pipeline.py"

# Read stdin
INPUT=$(cat)

TOOL_NAME=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null || echo "")

# Only intercept WebFetch
if [ "$TOOL_NAME" != "WebFetch" ]; then
    exit 0
fi

# Extract URL from tool_input
URL=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('url',''))" 2>/dev/null || echo "")

if [ -z "$URL" ]; then
    exit 0
fi

# Run through pipeline
# Exit codes: 0=clean, 1=modifications made (both are success), 2=error
set +e
CLEANED=$(python3 "$PIPELINE" fetch "$URL" 2>/dev/null)
PIPE_EXIT=$?
set -e

if [ "$PIPE_EXIT" -ge 2 ]; then
    python3 -c "
import json, sys
print(json.dumps({
    'hookSpecificOutput': {
        'hookEventName': 'PreToolUse',
        'permissionDecision': 'deny',
        'permissionDecisionReason': '[trialogue-guard] WebFetch blocked. Failed to fetch through security pipeline. Use trialogue_fetch MCP tool instead.'
    }
}))
"
    exit 0
fi

# Return cleaned content with explicit notice
python3 -c "
import json, sys
cleaned = sys.stdin.read()
print(json.dumps({
    'hookSpecificOutput': {
        'hookEventName': 'PreToolUse',
        'permissionDecision': 'deny',
        'permissionDecisionReason': '[trialogue-guard] WebFetch intercepted. Content fetched and sanitized via security pipeline. For seamless access, use trialogue_fetch MCP tool instead.\n\n--- Sanitized content ---\n\n' + cleaned
    }
}))
" <<< "$CLEANED"
