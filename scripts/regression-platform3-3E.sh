#!/usr/bin/env bash
# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

set -euo pipefail
PASS=0; FAIL=0; TOTAL=0
SCRIPTS=Polaris/scripts

assert_eq() { TOTAL=$((TOTAL+1)); if [ "$1" = "$2" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: expected='$2' got='$1' — $3"; fi; }
assert_contains() { TOTAL=$((TOTAL+1)); if grep -qF "$2" <<< "$1"; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: output missing '$2' — $3"; fi; }
assert_not_contains() { TOTAL=$((TOTAL+1)); if ! grep -qF "$2" <<< "$1"; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: output should NOT contain '$2' — $3"; fi; }

# --- 3E-G1: Prebuilt hit → "community knowledge base" ---
# Test the display function directly with a mock state that has prebuilt-sourced hints
G1=$(python3 -c "
import sys, json
sys.path.insert(0, '$SCRIPTS')
from polaris_cli import _emit_experience_summary
from pathlib import Path
import tempfile, os

# Create a temp runtime dir with a mock state
tmpdir = Path(tempfile.mkdtemp())
state = {
    'status': 'blocked',
    'artifacts': {
        'autofix_hints': json.dumps([
            {'kind': 'set_env', 'vars': {'LC_ALL': 'C.UTF-8'}, '_source': 'prebuilt', '_applied_count': 0, 'confidence_discount': 0.7}
        ]),
        'autofix_result': 'success',
        'failure_record_written': 'true',
    }
}

import io, contextlib
buf = io.StringIO()
with contextlib.redirect_stderr(buf):
    _emit_experience_summary(state, tmpdir)
output = buf.getvalue()
print(output, end='')
" 2>&1)
assert_contains "$G1" "community knowledge base" "3E-G1: prebuilt hit shows 'community knowledge base'"

# --- 3E-G2: Contributed hit → "verified in N deployments" ---
G2=$(python3 -c "
import sys, json
sys.path.insert(0, '$SCRIPTS')
from polaris_cli import _emit_experience_summary
from pathlib import Path
import tempfile, io, contextlib

tmpdir = Path(tempfile.mkdtemp())
state = {
    'status': 'blocked',
    'artifacts': {
        'autofix_hints': json.dumps([
            {'kind': 'set_env', 'vars': {'DOCKER_HOST': 'unix:///run/user/1000/docker.sock'}, '_source': 'contributed', '_applied_count': 2341, 'confidence_discount': 0.7}
        ]),
        'autofix_result': 'success',
        'failure_record_written': 'true',
    }
}

buf = io.StringIO()
with contextlib.redirect_stderr(buf):
    _emit_experience_summary(state, tmpdir)
output = buf.getvalue()
print(output, end='')
" 2>&1)
assert_contains "$G2" "verified in 2,341 deployments" "3E-G2: contributed hit shows 'verified in N deployments'"

# --- 3E-G3: No hit → no noise ---
G3=$(python3 -c "
import sys, json
sys.path.insert(0, '$SCRIPTS')
from polaris_cli import _emit_experience_summary
from pathlib import Path
import tempfile, io, contextlib

tmpdir = Path(tempfile.mkdtemp())
state = {
    'status': 'completed',
    'artifacts': {}
}

buf = io.StringIO()
with contextlib.redirect_stderr(buf):
    _emit_experience_summary(state, tmpdir)
output = buf.getvalue()
print(repr(output))
" 2>&1)
# Should have no experience-related output
assert_not_contains "$G3" "auto-fix" "3E-G3a: no hit → no auto-fix message"
assert_not_contains "$G3" "community knowledge base" "3E-G3b: no hit → no source label"
assert_not_contains "$G3" "verified in" "3E-G3c: no hit → no deployment count"

# --- 3E-G4: Platform 2 R5 still passes ---
G4_OUT=$(bash "$SCRIPTS/regression-platform2-R5.sh" 2>&1 | tail -1)
assert_contains "$G4_OUT" "passed, 0 failed" "3E-G4: Platform 2 R5 all pass (no regression)"

echo "=== 3E Results: $PASS/$TOTAL passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
