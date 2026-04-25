#!/usr/bin/env bash
# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

set -euo pipefail
PASS=0; FAIL=0; TOTAL=0
SCRIPTS=Polaris/scripts

assert_eq() { TOTAL=$((TOTAL+1)); if [ "$1" = "$2" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: expected='$2' got='$1' — $3"; fi; }

# --- Test 1: 过期记录被跳过 ---
RTDIR=$(mktemp -d)
python3 -c "
import json, datetime
old = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=60)).isoformat()
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
records = [
    {'task_fingerprint': {'matching_key': 'aaa'}, 'command': 'cmd1', 'error_class': 'unknown',
     'stderr_summary': '', 'repair_classification': 'unknown',
     'avoidance_hints': [{'kind': 'set_env', 'vars': {'X': '1'}}],
     'recorded_at': old, 'asset_version': 2,
     'applied_count': 0, 'applied_fail_count': 0, 'stale': False, 'rejected_by': None, 'source': 'auto'},
    {'task_fingerprint': {'matching_key': 'aaa'}, 'command': 'cmd1', 'error_class': 'unknown',
     'stderr_summary': '', 'repair_classification': 'unknown',
     'avoidance_hints': [{'kind': 'set_env', 'vars': {'Y': '2'}}],
     'recorded_at': now, 'asset_version': 2,
     'applied_count': 0, 'applied_fail_count': 0, 'stale': False, 'rejected_by': None, 'source': 'auto'}
]
json.dump({'schema_version': 2, 'records': records}, open('$RTDIR/failure-records.json', 'w'))
"
RESULT=$(python3 "$SCRIPTS/polaris_failure_records.py" query --matching-key aaa --store "$RTDIR/failure-records.json" --ttl-days 30 2>&1)
HINT_COUNT=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('avoidance_hints',[])))")
assert_eq "$HINT_COUNT" "1" "B1-T1: only fresh record hints returned (expired skipped)"
rm -rf "$RTDIR"

# --- Test 2: stale 记录被跳过 ---
RTDIR=$(mktemp -d)
python3 -c "
import json, datetime
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
records = [
    {'task_fingerprint': {'matching_key': 'bbb'}, 'command': 'cmd2', 'error_class': 'unknown',
     'stderr_summary': '', 'repair_classification': 'unknown',
     'avoidance_hints': [{'kind': 'set_env', 'vars': {'X': '1'}}],
     'recorded_at': now, 'asset_version': 2,
     'applied_count': 5, 'applied_fail_count': 3, 'stale': True, 'rejected_by': None, 'source': 'auto'},
    {'task_fingerprint': {'matching_key': 'bbb'}, 'command': 'cmd2', 'error_class': 'unknown',
     'stderr_summary': '', 'repair_classification': 'unknown',
     'avoidance_hints': [{'kind': 'append_flags', 'flags': ['--verbose']}],
     'recorded_at': now, 'asset_version': 2,
     'applied_count': 1, 'applied_fail_count': 0, 'stale': False, 'rejected_by': None, 'source': 'auto'}
]
json.dump({'schema_version': 2, 'records': records}, open('$RTDIR/failure-records.json', 'w'))
"
RESULT=$(python3 "$SCRIPTS/polaris_failure_records.py" query --matching-key bbb --store "$RTDIR/failure-records.json" 2>&1)
HINT_COUNT=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('avoidance_hints',[])))")
assert_eq "$HINT_COUNT" "1" "B1-T2: only non-stale record hints returned"
rm -rf "$RTDIR"

# --- Test 3: update_applied 降权触发 ---
RTDIR=$(mktemp -d)
python3 -c "
import json, datetime
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
records = [
    {'task_fingerprint': {'matching_key': 'ccc'}, 'command': 'cmd3', 'error_class': 'unknown',
     'stderr_summary': '', 'repair_classification': 'unknown',
     'avoidance_hints': [{'kind': 'set_env', 'vars': {'X': '1'}}],
     'recorded_at': now, 'asset_version': 2,
     'applied_count': 0, 'applied_fail_count': 2, 'stale': False, 'rejected_by': None, 'source': 'auto'}
]
json.dump({'schema_version': 2, 'records': records}, open('$RTDIR/failure-records.json', 'w'))
"
python3 "$SCRIPTS/polaris_failure_records.py" update-applied --matching-key ccc --success false --store "$RTDIR/failure-records.json" 2>&1 >/dev/null
STALE=$(python3 -c "import json; r=json.load(open('$RTDIR/failure-records.json'))['records'][0]; print(r['stale'])")
assert_eq "$STALE" "True" "B1-T3: record should be stale after 3rd failure"
FAIL_COUNT=$(python3 -c "import json; r=json.load(open('$RTDIR/failure-records.json'))['records'][0]; print(r['applied_fail_count'])")
assert_eq "$FAIL_COUNT" "3" "B1-T3: applied_fail_count should be 3"
rm -rf "$RTDIR"

# --- Test 4: schema v1 → v2 自动迁移 ---
RTDIR=$(mktemp -d)
python3 -c "
import json
records = [
    {'task_fingerprint': {'matching_key': 'ddd'}, 'command': 'cmd4', 'error_class': 'unknown',
     'stderr_summary': '', 'repair_classification': 'unknown',
     'avoidance_hints': [{'kind': 'set_env', 'vars': {'X': '1'}}],
     'recorded_at': '2026-03-16T00:00:00Z', 'asset_version': 2}
]
json.dump({'schema_version': 1, 'records': records}, open('$RTDIR/failure-records.json', 'w'))
"
RESULT=$(python3 "$SCRIPTS/polaris_failure_records.py" query --matching-key ddd --store "$RTDIR/failure-records.json" 2>&1)
HINT_COUNT=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('avoidance_hints',[])))")
assert_eq "$HINT_COUNT" "1" "B1-T4: v1 record migrated and queryable"
HAS_FIELDS=$(python3 -c "
import json
r=json.load(open('$RTDIR/failure-records.json'))['records'][0]
print('applied_count' in r and 'stale' in r and 'source' in r)
")
assert_eq "$HAS_FIELDS" "True" "B1-T4: migrated record has v2 fields"
rm -rf "$RTDIR"

# --- Test 5: TTL 基于 UTC ---
RTDIR=$(mktemp -d)
python3 -c "
import json, datetime
# Record exactly 29 days old — should NOT be expired with 30-day TTL
ts = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=29)).isoformat()
records = [
    {'task_fingerprint': {'matching_key': 'eee'}, 'command': 'cmd5', 'error_class': 'unknown',
     'stderr_summary': '', 'repair_classification': 'unknown',
     'avoidance_hints': [{'kind': 'set_env', 'vars': {'Z': '1'}}],
     'recorded_at': ts, 'asset_version': 2,
     'applied_count': 0, 'applied_fail_count': 0, 'stale': False, 'rejected_by': None, 'source': 'auto'}
]
json.dump({'schema_version': 2, 'records': records}, open('$RTDIR/failure-records.json', 'w'))
"
RESULT=$(python3 "$SCRIPTS/polaris_failure_records.py" query --matching-key eee --store "$RTDIR/failure-records.json" --ttl-days 30 2>&1)
HINT_COUNT=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('avoidance_hints',[])))")
assert_eq "$HINT_COUNT" "1" "B1-T5: 29-day-old record not expired with 30-day TTL"
rm -rf "$RTDIR"

# --- Test 6: stale 是单向的 — update_applied success=true 不能恢复 ---
RTDIR=$(mktemp -d)
python3 -c "
import json, datetime
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
records = [
    {'task_fingerprint': {'matching_key': 'fff'}, 'command': 'cmd6', 'error_class': 'unknown',
     'stderr_summary': '', 'repair_classification': 'unknown',
     'avoidance_hints': [{'kind': 'set_env', 'vars': {'X': '1'}}],
     'recorded_at': now, 'asset_version': 2,
     'applied_count': 5, 'applied_fail_count': 3, 'stale': True, 'rejected_by': None, 'source': 'auto'}
]
json.dump({'schema_version': 2, 'records': records}, open('$RTDIR/failure-records.json', 'w'))
"
python3 "$SCRIPTS/polaris_failure_records.py" update-applied --matching-key fff --success true --store "$RTDIR/failure-records.json" 2>&1 >/dev/null
STALE=$(python3 -c "import json; r=json.load(open('$RTDIR/failure-records.json'))['records'][0]; print(r['stale'])")
assert_eq "$STALE" "True" "B1-T6: stale record stays stale even after success"
rm -rf "$RTDIR"

# --- Test 7: record CLI 子命令正常工作 ---
RTDIR=$(mktemp -d)
python3 "$SCRIPTS/polaris_failure_records.py" record \
    --store "$RTDIR/failure-records.json" \
    --fingerprint-json '{"matching_key": "cli-test"}' \
    --command-str "echo hello" \
    --error-class "test_error" \
    --avoidance-hints-json '[{"kind": "set_env", "vars": {"X": "1"}}]' 2>&1 >/dev/null
REC_COUNT=$(python3 -c "import json; print(len(json.load(open('$RTDIR/failure-records.json'))['records']))")
assert_eq "$REC_COUNT" "1" "B1-T7: record CLI writes one record"
REC_CMD=$(python3 -c "import json; print(json.load(open('$RTDIR/failure-records.json'))['records'][0]['command'])")
assert_eq "$REC_CMD" "echo hello" "B1-T7: record CLI stores correct command"
rm -rf "$RTDIR"

echo "=== B1 Results: $PASS/$TOTAL passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
