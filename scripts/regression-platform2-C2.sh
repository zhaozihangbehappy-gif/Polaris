#!/usr/bin/env bash
# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

set -euo pipefail
PASS=0; FAIL=0; TOTAL=0
SCRIPTS=Polaris/scripts

assert_eq() { TOTAL=$((TOTAL+1)); if [ "$1" = "$2" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: expected='$2' got='$1' — $3"; fi; }
assert_contains() { TOTAL=$((TOTAL+1)); if echo "$1" | grep -qF "$2"; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: output missing '$2' — $3"; fi; }

# --- Helper: 构造测试数据 ---
setup_store() {
    local DIR="$1"
    python3 -c "
import json, datetime
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
records = [
    {'task_fingerprint': {'matching_key': 'fb-test', 'command_key': 'fb-cmd'},
     'command': 'npm test', 'error_class': 'missing_dependency',
     'stderr_summary': 'Cannot find module X',
     'repair_classification': 'unknown',
     'avoidance_hints': [{'kind': 'set_env', 'vars': {'BAD': 'hint'}}],
     'recorded_at': now, 'asset_version': 2,
     'applied_count': 2, 'applied_fail_count': 2, 'stale': False,
     'rejected_by': None, 'source': 'auto'},
    {'task_fingerprint': {'matching_key': 'fb-test', 'command_key': 'fb-cmd'},
     'command': 'npm test', 'error_class': 'missing_dependency',
     'stderr_summary': 'Cannot find module Y',
     'repair_classification': 'unknown',
     'avoidance_hints': [{'kind': 'set_env', 'vars': {'GOOD': 'hint'}}],
     'recorded_at': now, 'asset_version': 2,
     'applied_count': 1, 'applied_fail_count': 0, 'stale': False,
     'rejected_by': None, 'source': 'auto'}
]
json.dump({'schema_version': 2, 'records': records}, open('$DIR/failure-records.json', 'w'))
"
}

# --- Test 1: reject 标记生效 ---
RTDIR=$(mktemp -d)
setup_store "$RTDIR"
python3 "$SCRIPTS/polaris_cli.py" feedback reject 0 --store "$RTDIR/failure-records.json" 2>&1
REC=$(python3 -c "import json; r=json.load(open('$RTDIR/failure-records.json'))['records'][0]; print(r['stale'], r['rejected_by'])")
assert_eq "$REC" "True user" "C2-T1: record 0 must be stale + rejected_by=user"
rm -rf "$RTDIR"

# --- Test 2: reject 后 query 不返回该记录的 hints ---
RTDIR=$(mktemp -d)
setup_store "$RTDIR"
python3 "$SCRIPTS/polaris_cli.py" feedback reject 0 --store "$RTDIR/failure-records.json" 2>&1
RESULT=$(python3 "$SCRIPTS/polaris_failure_records.py" query --matching-key fb-test --store "$RTDIR/failure-records.json" 2>&1)
VARS=$(echo "$RESULT" | python3 -c "import sys,json; h=json.load(sys.stdin).get('avoidance_hints',[]); print(','.join(list(h[0].get('vars',{}).keys())) if h else 'none')")
assert_eq "$VARS" "GOOD" "C2-T2: only non-rejected hints returned"
rm -rf "$RTDIR"

# --- Test 3: correct 创建高优先级记录 ---
RTDIR=$(mktemp -d)
setup_store "$RTDIR"
python3 "$SCRIPTS/polaris_cli.py" feedback correct 0 \
    --hint-kind set_env --hint-value '{"vars": {"CORRECT": "value"}}' \
    --store "$RTDIR/failure-records.json" 2>&1
TOTAL_RECS=$(python3 -c "import json; print(len(json.load(open('$RTDIR/failure-records.json'))['records']))")
assert_eq "$TOTAL_RECS" "3" "C2-T3: correction creates new record (total 3)"
LAST_SRC=$(python3 -c "import json; print(json.load(open('$RTDIR/failure-records.json'))['records'][-1]['source'])")
assert_eq "$LAST_SRC" "user_correction" "C2-T3: new record source is user_correction"
rm -rf "$RTDIR"

# --- Test 4: user_correction 优先于 auto ---
RTDIR=$(mktemp -d)
setup_store "$RTDIR"
python3 "$SCRIPTS/polaris_cli.py" feedback correct 0 \
    --hint-kind set_env --hint-value '{"vars": {"CORRECT": "value"}}' \
    --store "$RTDIR/failure-records.json" 2>&1
RESULT=$(python3 "$SCRIPTS/polaris_failure_records.py" query --matching-key fb-test --store "$RTDIR/failure-records.json" 2>&1)
FIRST_VAR=$(echo "$RESULT" | python3 -c "
import sys,json
h=json.load(sys.stdin).get('avoidance_hints',[])
print(list(h[0].get('vars',{}).keys())[0] if h else 'none')
")
assert_eq "$FIRST_VAR" "CORRECT" "C2-T4: user_correction hints come first"
rm -rf "$RTDIR"

# --- Test 5: feedback list 显示修正记录 ---
RTDIR=$(mktemp -d)
setup_store "$RTDIR"
python3 "$SCRIPTS/polaris_cli.py" feedback reject 0 --store "$RTDIR/failure-records.json" 2>&1 >/dev/null
python3 "$SCRIPTS/polaris_cli.py" feedback correct 0 \
    --hint-kind set_env --hint-value '{"vars": {"FIX": "1"}}' \
    --store "$RTDIR/failure-records.json" 2>&1 >/dev/null
OUT=$(python3 "$SCRIPTS/polaris_cli.py" feedback list --store "$RTDIR/failure-records.json" 2>&1)
assert_contains "$OUT" "rejected" "C2-T5: list shows rejected record"
assert_contains "$OUT" "user_correction" "C2-T5: list shows correction record"
rm -rf "$RTDIR"

# --- Test 6: reject 是幂等的 ---
RTDIR=$(mktemp -d)
setup_store "$RTDIR"
python3 "$SCRIPTS/polaris_cli.py" feedback reject 0 --store "$RTDIR/failure-records.json" 2>&1
python3 "$SCRIPTS/polaris_cli.py" feedback reject 0 --store "$RTDIR/failure-records.json" 2>&1
REC=$(python3 -c "import json; r=json.load(open('$RTDIR/failure-records.json'))['records'][0]; print(r['stale'], r['rejected_by'])")
assert_eq "$REC" "True user" "C2-T6: double reject is idempotent"
rm -rf "$RTDIR"

# --- Test 7: correct 保留原 task_fingerprint ---
RTDIR=$(mktemp -d)
setup_store "$RTDIR"
python3 "$SCRIPTS/polaris_cli.py" feedback correct 0 \
    --hint-kind set_env --hint-value '{"vars": {"X": "1"}}' \
    --store "$RTDIR/failure-records.json" 2>&1
ORIG_MK=$(python3 -c "import json; print(json.load(open('$RTDIR/failure-records.json'))['records'][0]['task_fingerprint']['matching_key'])")
NEW_MK=$(python3 -c "import json; print(json.load(open('$RTDIR/failure-records.json'))['records'][-1]['task_fingerprint']['matching_key'])")
assert_eq "$ORIG_MK" "$NEW_MK" "C2-T7: correction preserves original matching_key"
rm -rf "$RTDIR"

# --- Test 8: invalid hint kind 被拒绝 ---
RTDIR=$(mktemp -d)
setup_store "$RTDIR"
OUT=$(python3 "$SCRIPTS/polaris_cli.py" feedback correct 0 \
    --hint-kind "invalid_kind" --hint-value '{"x": 1}' \
    --store "$RTDIR/failure-records.json" 2>&1) || true
assert_contains "$OUT" "invalid hint kind" "C2-T8: invalid hint kind rejected with error"
rm -rf "$RTDIR"

echo "=== C2 Results: $PASS/$TOTAL passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
