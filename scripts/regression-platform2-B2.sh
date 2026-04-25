#!/usr/bin/env bash
# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

set -euo pipefail
PASS=0; FAIL=0; TOTAL=0
SCRIPTS=Polaris/scripts

assert_eq() { TOTAL=$((TOTAL+1)); if [ "$1" = "$2" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: expected='$2' got='$1' — $3"; fi; }

# --- 预计算 fingerprint ---
FP_DIR_A=$(python3 "$SCRIPTS/polaris_task_fingerprint.py" compute --command "npm test" --cwd "/project-a" 2>&1)
FP_DIR_B=$(python3 "$SCRIPTS/polaris_task_fingerprint.py" compute --command "npm test" --cwd "/project-b" 2>&1)
FP_OTHER=$(python3 "$SCRIPTS/polaris_task_fingerprint.py" compute --command "go test" --cwd "/project-a" 2>&1)

MK_A=$(echo "$FP_DIR_A" | python3 -c "import sys,json; print(json.load(sys.stdin)['matching_key'])")
MK_B=$(echo "$FP_DIR_B" | python3 -c "import sys,json; print(json.load(sys.stdin)['matching_key'])")
CK_A=$(echo "$FP_DIR_A" | python3 -c "import sys,json; print(json.load(sys.stdin)['command_key'])")
CK_B=$(echo "$FP_DIR_B" | python3 -c "import sys,json; print(json.load(sys.stdin)['command_key'])")
CK_OTHER=$(echo "$FP_OTHER" | python3 -c "import sys,json; print(json.load(sys.stdin)['command_key'])")

# --- Test 1: 同命令不同目录 → matching_key 不同，command_key 相同 ---
if [ "$MK_A" != "$MK_B" ]; then MK_DIFF=1; else MK_DIFF=0; fi
assert_eq "$MK_DIFF" "1" "B2-T1: different cwd → different matching_key"
assert_eq "$CK_A" "$CK_B" "B2-T1: same command → same command_key"

# --- Test 2: 不同命令 → command_key 不同 ---
if [ "$CK_A" != "$CK_OTHER" ]; then CK_DIFF=1; else CK_DIFF=0; fi
assert_eq "$CK_DIFF" "1" "B2-T2: different command → different command_key"

# --- Test 3: exact match 优先 ---
RTDIR=$(mktemp -d)
python3 -c "
import json, datetime
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
records = [
    {'task_fingerprint': {'matching_key': '$MK_A', 'command_key': '$CK_A'},
     'command': 'npm test', 'error_class': 'missing_dependency',
     'stderr_summary': '', 'repair_classification': 'unknown',
     'avoidance_hints': [{'kind': 'set_env', 'vars': {'FROM': 'exact'}}],
     'recorded_at': now, 'asset_version': 2,
     'applied_count': 0, 'applied_fail_count': 0, 'stale': False, 'rejected_by': None, 'source': 'auto'}
]
json.dump({'schema_version': 2, 'records': records}, open('$RTDIR/failure-records.json', 'w'))
"
RESULT=$(python3 "$SCRIPTS/polaris_failure_records.py" query --matching-key "$MK_A" --command-key "$CK_A" --store "$RTDIR/failure-records.json" 2>&1)
TIER=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('match_tier',''))")
assert_eq "$TIER" "exact" "B2-T3: same cwd → exact match"

# --- Test 4: command_only fallback ---
RESULT=$(python3 "$SCRIPTS/polaris_failure_records.py" query --matching-key "$MK_B" --command-key "$CK_B" --store "$RTDIR/failure-records.json" 2>&1)
TIER=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('match_tier',''))")
DISCOUNT=$(echo "$RESULT" | python3 -c "import sys,json; h=json.load(sys.stdin).get('avoidance_hints',[]); print(h[0].get('confidence_discount',1.0) if h else 'none')")
assert_eq "$TIER" "command_only" "B2-T4: different cwd → command_only fallback"
assert_eq "$DISCOUNT" "0.6" "B2-T4: confidence discount must be 0.6"

# --- Test 5: 完全不同命令 → 无匹配 ---
MK_X=$(echo "$FP_OTHER" | python3 -c "import sys,json; print(json.load(sys.stdin)['matching_key'])")
RESULT=$(python3 "$SCRIPTS/polaris_failure_records.py" query --matching-key "$MK_X" --command-key "$CK_OTHER" --store "$RTDIR/failure-records.json" 2>&1)
HINT_COUNT=$(echo "$RESULT" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('avoidance_hints',[])))")
assert_eq "$HINT_COUNT" "0" "B2-T5: different command → no match"
rm -rf "$RTDIR"

# --- Test 6: 旧记录无 command_key → exact match 仍工作，fallback 不可用但不报错 ---
RTDIR=$(mktemp -d)
python3 -c "
import json, datetime
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
records = [
    {'task_fingerprint': {'matching_key': '$MK_A'},
     'command': 'npm test', 'error_class': 'unknown',
     'stderr_summary': '', 'repair_classification': 'unknown',
     'avoidance_hints': [{'kind': 'set_env', 'vars': {'OLD': '1'}}],
     'recorded_at': now, 'asset_version': 2,
     'applied_count': 0, 'applied_fail_count': 0, 'stale': False, 'rejected_by': None, 'source': 'auto'}
]
json.dump({'schema_version': 2, 'records': records}, open('$RTDIR/failure-records.json', 'w'))
"
# Exact match still works
RESULT=$(python3 "$SCRIPTS/polaris_failure_records.py" query --matching-key "$MK_A" --command-key "$CK_A" --store "$RTDIR/failure-records.json" 2>&1)
TIER=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('match_tier',''))")
assert_eq "$TIER" "exact" "B2-T6a: old record without command_key → exact match works"
# Fallback with different matching_key → no match (not error)
RESULT=$(python3 "$SCRIPTS/polaris_failure_records.py" query --matching-key "$MK_B" --command-key "$CK_B" --store "$RTDIR/failure-records.json" 2>&1)
TIER=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('match_tier',''))")
assert_eq "$TIER" "none" "B2-T6b: old record without command_key → fallback gracefully returns none"
rm -rf "$RTDIR"

# --- Test 7: adapter skips hints with confidence_discount < 0.5 ---
python3 -c "
import sys; sys.path.insert(0, '$SCRIPTS')
from polaris_adapter_shell import apply_hints
cmd, cwd, timeout, applied, rejected = apply_hints(
    'npm test', '/tmp', 60000,
    {'avoid': [
        {'kind': 'set_env', 'vars': {'GOOD': '1'}, 'confidence_discount': 1.0},
        {'kind': 'set_env', 'vars': {'BAD': '1'}, 'confidence_discount': 0.4},
        {'kind': 'set_env', 'vars': {'EDGE': '1'}, 'confidence_discount': 0.5},
    ], 'prefer': []}
)
applied_vars = [list(a.get('vars',{}).keys())[0] for a in applied if a.get('kind')=='set_env']
rejected_reasons = [r['reason'] for r in rejected]
assert 'GOOD' in applied_vars, f'GOOD should be applied: {applied_vars}'
assert 'EDGE' in applied_vars, f'EDGE (0.5) should be applied: {applied_vars}'
assert any('0.4' in r for r in rejected_reasons), f'BAD should be rejected: {rejected_reasons}'
assert 'BAD' not in applied_vars, f'BAD should NOT be applied: {applied_vars}'
print('confidence_filter_ok')
" 2>&1
FILTER_OK=$?
assert_eq "$FILTER_OK" "0" "B2-T7: adapter respects confidence_discount threshold"

echo "=== B2 Results: $PASS/$TOTAL passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
