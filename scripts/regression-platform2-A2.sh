#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT/.."
PASS=0; FAIL=0; TOTAL=0

assert_contains() { TOTAL=$((TOTAL+1)); if grep -qF "$2" <<< "$1"; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: output missing '$2' — $3"; fi; }
assert_not_contains() { TOTAL=$((TOTAL+1)); if grep -qF "$2" <<< "$1"; then FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: output should NOT contain '$2' — $3"; else PASS=$((PASS+1)); fi; }

# R1: Isolate from global experience library
export POLARIS_HOME=$(mktemp -d)
trap 'rm -rf "$POLARIS_HOME"' EXIT

# --- Test 1: first successful run → learned + success pattern captured ---
RTDIR=$(mktemp -d)
OUT=$(python3 Polaris/scripts/polaris_cli.py run "echo first-success" --runtime-dir "$RTDIR" 2>&1)
assert_contains "$OUT" "[polaris]" "A2-T1: must have [polaris] prefix"
assert_contains "$OUT" "learned" "A2-T1: must indicate learning happened"
assert_contains "$OUT" "success pattern captured" "A2-T1: success pattern message"
rm -rf "$RTDIR"

# --- Test 2: first failure → learned + hint kinds ---
RTDIR=$(mktemp -d)
OUT=$(python3 Polaris/scripts/polaris_cli.py run "false" --runtime-dir "$RTDIR" 2>&1) || true
assert_contains "$OUT" "[polaris]" "A2-T2: must have [polaris] prefix"
assert_contains "$OUT" "learned" "A2-T2: must indicate learning happened"
assert_contains "$OUT" "stored for next run" "A2-T2: must indicate persistence"
rm -rf "$RTDIR"

# --- Test 3: second run with same runtime dir → experience applied ---
RTDIR=$(mktemp -d)
# First: fail to write experience
python3 Polaris/scripts/polaris_cli.py run "python3 -c 'import nonexistent_module_xyz'" --runtime-dir "$RTDIR" >/dev/null 2>/dev/null || true
# Second: same command same dir, should hit experience (capture stderr only)
OUT2=$(python3 Polaris/scripts/polaris_cli.py run "python3 -c 'import nonexistent_module_xyz'" --runtime-dir "$RTDIR" 2>&1 >/dev/null) || true
assert_contains "$OUT2" "applied" "A2-T3: must indicate experience was applied"
assert_contains "$OUT2" "avoidance hints" "A2-T3: must mention avoidance hints"
rm -rf "$RTDIR"

# --- Test 4: brand-new task → first run message ---
RTDIR=$(mktemp -d)
OUT=$(python3 Polaris/scripts/polaris_cli.py run "echo brand-new-task" --runtime-dir "$RTDIR" 2>&1)
assert_contains "$OUT" "first run" "A2-T4: must indicate no prior experience"
rm -rf "$RTDIR"

# --- Test 5: experience summary goes to stderr, not stdout ---
RTDIR=$(mktemp -d)
STDOUT_ONLY=$(python3 Polaris/scripts/polaris_cli.py run "echo stderr-test" --runtime-dir "$RTDIR" 2>/dev/null) || true
assert_not_contains "$STDOUT_ONLY" "[polaris] " "A2-T5: experience summary must not appear on stdout"
rm -rf "$RTDIR"

# --- Test 6: prior success patterns for THIS task → must NOT say "first run" ---
RTDIR=$(mktemp -d)
mkdir -p "$RTDIR"
# Compute matching_key for "echo test-task-6" with cwd=$RTDIR
MATCH_KEY=$(python3 -c "
import sys; sys.path.insert(0, 'Polaris/scripts')
import polaris_task_fingerprint as ptf
print(ptf.compute('echo test-task-6', '$RTDIR')['matching_key'])
")
echo '{"schema_version":1,"records":[]}' > "$RTDIR/failure-records.json"
python3 -c "
import json
json.dump({'schema_version': 1, 'patterns': [{
    'pattern_id': 'pat-1', 'fingerprint': 'x', 'summary': 's',
    'trigger': 'auto', 'sequence': ['s1'], 'outcome': 'ok',
    'evidence': [], 'adapter': 'shell-command', 'tags': [],
    'modes': ['micro'], 'confidence': 80, 'lifecycle_state': 'validated',
    'best_lifecycle_state': 'validated', 'selection_count': 1,
    'validation_count': 1, 'evidence_count': 1, 'promotion_count': 0,
    'last_validated_at': '2026-03-16T00:00:00Z',
    'last_selected_at': '2026-03-16T00:00:00Z', 'asset_version': 2,
    'task_fingerprint': {'matching_key': '$MATCH_KEY', 'raw_descriptor': 'echo test-task-6'}
}]}, open('$RTDIR/success-patterns.json', 'w'))
"
python3 -c "
import sys; sys.path.insert(0, 'Polaris/scripts')
from polaris_cli import _emit_experience_summary, _has_prior_experience_for_task
from pathlib import Path
rd = Path('$RTDIR')
had_prior = _has_prior_experience_for_task(rd, '$MATCH_KEY')
state = {'status': 'completed', 'artifacts': {}}
_emit_experience_summary(state, rd, had_prior)
" 2>&1 | tee /dev/stderr | grep -qF "first run" && FOUND_FIRST_RUN=1 || FOUND_FIRST_RUN=0
assert_not_contains "$FOUND_FIRST_RUN" "1" "A2-T6: must NOT say 'first run' when task has prior success patterns"
rm -rf "$RTDIR"

# --- Test 7: consolidation failed → must NOT claim "success pattern captured" ---
RTDIR=$(mktemp -d)
mkdir -p "$RTDIR"
echo '{"schema_version":1,"records":[]}' > "$RTDIR/failure-records.json"
echo '{"schema_version":1,"patterns":[]}' > "$RTDIR/success-patterns.json"
python3 -c "
import json, sys
sys.path.insert(0, 'Polaris/scripts')
from polaris_cli import _emit_experience_summary, _has_prior_experience_for_task
from pathlib import Path
rd = Path('$RTDIR')
had_prior = _has_prior_experience_for_task(rd, 'nonexistent-key')
state = {
    'status': 'completed',
    'artifacts': {
        'learning_summary': json.dumps({
            'success_markers': 1, 'processed_items': 0,
            'retained_items': 1, 'promoted_patterns': [],
            'merged_patterns': [], 'promoted_rules': [],
            'merged_rules': [], 'failed_patterns': [], 'failed_rules': [],
            'queued_items': 1, 'rule_candidates': 0
        })
    }
}
_emit_experience_summary(state, rd, had_prior)
" 2>&1 | tee /dev/stderr | grep -qF "success pattern captured" && FOUND_CAPTURED=1 || FOUND_CAPTURED=0
assert_not_contains "$FOUND_CAPTURED" "1" "A2-T7: must NOT claim 'captured' when consolidation failed"
rm -rf "$RTDIR"

# --- Test 8: cross-task isolation — task-B in same dir as task-A → must say "first run" for task-B ---
RTDIR=$(mktemp -d)
# Run task-A first to populate experience
python3 Polaris/scripts/polaris_cli.py run "echo task-A-isolation" --runtime-dir "$RTDIR" >/dev/null 2>/dev/null || true
# Now run task-B (different command) → should see "first run" despite task-A experience existing
OUT8=$(python3 Polaris/scripts/polaris_cli.py run "echo task-B-isolation" --runtime-dir "$RTDIR" 2>&1)
assert_contains "$OUT8" "first run" "A2-T8: different task in same dir must say 'first run'"
rm -rf "$RTDIR"

# --- Test 9: avoid vs prefer hint separation ---
RTDIR=$(mktemp -d)
mkdir -p "$RTDIR"
echo '{"schema_version":1,"records":[]}' > "$RTDIR/failure-records.json"
echo '{"schema_version":1,"patterns":[]}' > "$RTDIR/success-patterns.json"
python3 -c "
import json, sys
sys.path.insert(0, 'Polaris/scripts')
from polaris_cli import _emit_experience_summary
from pathlib import Path
state = {
    'status': 'completed',
    'artifacts': {
        'experience_hints': json.dumps({
            'avoid': [],
            'prefer': [{'kind': 'set_env', 'vars': {'X': '1'}}]
        })
    }
}
_emit_experience_summary(state, Path('$RTDIR'), True)
" 2>/tmp/polaris-t9-out.txt
T9_OUT=$(cat /tmp/polaris-t9-out.txt)
assert_contains "$T9_OUT" "strategy hints from success patterns" "A2-T9: prefer-only hints must say 'strategy hints'"
assert_not_contains "$T9_OUT" "avoidance hints from previous failures" "A2-T9: prefer-only hints must NOT say 'avoidance hints'"
rm -rf "$RTDIR" /tmp/polaris-t9-out.txt

echo "=== A2 Results: $PASS/$TOTAL passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
