#!/usr/bin/env bash
# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT/.."
PASS=0; FAIL=0; TOTAL=0

assert_eq() { TOTAL=$((TOTAL+1)); if [ "$1" = "$2" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: expected='$2' got='$1' — $3"; fi; }
# Fix #6: use here-string instead of echo|grep to avoid SIGPIPE with pipefail
assert_contains() { TOTAL=$((TOTAL+1)); if grep -qF "$2" <<< "$1"; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: output missing '$2' — $3"; fi; }

# --- Test 1: empty experience store ---
RTDIR=$(mktemp -d)
mkdir -p "$RTDIR"
OUT=$(python3 Polaris/scripts/polaris_stats.py --runtime-dir "$RTDIR" 2>&1)
assert_contains "$OUT" "no experience recorded yet" "A3-T1: empty store message"
rm -rf "$RTDIR"

# --- Test 2: constructed records, verify counts match ---
RTDIR=$(mktemp -d)
mkdir -p "$RTDIR"
python3 -c "
import json, datetime
now = datetime.datetime.now(datetime.UTC).isoformat()
records = []
for i in range(5):
    records.append({
        'task_fingerprint': {'raw_descriptor': f'cmd-{i}', 'normalized_descriptor': f'cmd-{i}', 'matching_key': f'key{i:04x}'},
        'command': f'cmd-{i}',
        'error_class': 'missing_dependency' if i < 3 else 'permission_denial',
        'stderr_summary': 'err',
        'repair_classification': 'unknown',
        'avoidance_hints': [{'kind': 'set_env', 'vars': {'X': '1'}}],
        'recorded_at': now,
        'asset_version': 2
    })
json.dump({'schema_version': 1, 'records': records}, open('$RTDIR/failure-records.json', 'w'), indent=2)

patterns = []
for i in range(3):
    patterns.append({
        'pattern_id': f'pat-{i}',
        'fingerprint': f'pat-{i}',
        'summary': f'pattern {i}',
        'trigger': 'auto',
        'sequence': ['step1'],
        'outcome': 'ok',
        'evidence': [],
        'adapter': 'shell-command',
        'tags': [],
        'modes': ['standard'],
        'confidence': 80,
        'lifecycle_state': 'validated' if i < 2 else 'preferred',
        'best_lifecycle_state': 'preferred',
        'selection_count': 1,
        'validation_count': 1,
        'evidence_count': 1,
        'promotion_count': 0,
        'last_validated_at': now,
        'last_selected_at': now,
        'asset_version': 2
    })
json.dump({'schema_version': 1, 'patterns': patterns}, open('$RTDIR/success-patterns.json', 'w'), indent=2)
"
OUT=$(python3 Polaris/scripts/polaris_stats.py --runtime-dir "$RTDIR" 2>&1)
assert_contains "$OUT" "5 total" "A3-T2: failure records count must be 5"
assert_contains "$OUT" "3 total" "A3-T2: success patterns count must be 3"
assert_contains "$OUT" "missing_dependency" "A3-T2: must show error class breakdown"
assert_contains "$OUT" "permission_denial" "A3-T2: must show error class breakdown"
assert_contains "$OUT" "validated" "A3-T2: must show lifecycle breakdown"
rm -rf "$RTDIR"

# --- Test 3: --json output is valid JSON (Fix #6: feed via stdin not argv) ---
RTDIR=$(mktemp -d)
mkdir -p "$RTDIR"
echo '{"schema_version":1,"records":[]}' > "$RTDIR/failure-records.json"
echo '{"schema_version":1,"patterns":[]}' > "$RTDIR/success-patterns.json"
python3 Polaris/scripts/polaris_stats.py --runtime-dir "$RTDIR" --json | python3 -c "import json,sys; json.load(sys.stdin)"
assert_eq "$?" "0" "A3-T3: --json output must be valid JSON"
rm -rf "$RTDIR"

# --- Test 4: CLI stats subcommand works ---
RTDIR=$(mktemp -d)
mkdir -p "$RTDIR"
OUT=$(python3 Polaris/scripts/polaris_cli.py stats --runtime-dir "$RTDIR" 2>&1)
assert_contains "$OUT" "no experience recorded yet" "A3-T4: CLI stats subcommand works"
rm -rf "$RTDIR"

# --- Test 5: --json with constructed data has correct fields ---
RTDIR=$(mktemp -d)
mkdir -p "$RTDIR"
python3 -c "
import json
json.dump({'schema_version': 1, 'records': [
    {'error_class': 'timeout', 'recorded_at': '2026-03-16T00:00:00Z', 'task_fingerprint': {}, 'command': 'test', 'avoidance_hints': []}
]}, open('$RTDIR/failure-records.json', 'w'))
json.dump({'schema_version': 1, 'patterns': []}, open('$RTDIR/success-patterns.json', 'w'))
"
FR_COUNT=$(python3 Polaris/scripts/polaris_stats.py --runtime-dir "$RTDIR" --json | python3 -c "import json,sys; print(json.load(sys.stdin)['failure_records'])")
assert_eq "$FR_COUNT" "1" "A3-T5: JSON failure_records count must be 1"
rm -rf "$RTDIR"

# --- Test 6 (Fix #3): corrupt JSON shape — records is a dict not list → safe downgrade ---
RTDIR=$(mktemp -d)
mkdir -p "$RTDIR"
echo '{"schema_version":1,"records":{"bad":"shape"}}' > "$RTDIR/failure-records.json"
echo '{"schema_version":1,"patterns":"not-a-list"}' > "$RTDIR/success-patterns.json"
T6_EXIT=0
# Capture stdout (JSON) only; warnings go to stderr (fd2) which we discard for assertion
OUT=$(python3 Polaris/scripts/polaris_stats.py --runtime-dir "$RTDIR" --json 2>/dev/null) || T6_EXIT=$?
assert_eq "$T6_EXIT" "0" "A3-T6: corrupt shape must not crash"
# Should output valid JSON with 0 counts
echo "$OUT" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['failure_records']==0 and d['success_patterns']==0" 2>/dev/null
assert_eq "$?" "0" "A3-T6: corrupt files must report 0 records"
rm -rf "$RTDIR"

# --- Test 7 (Fix #5): --json schema stable — empty store has same fields as non-empty ---
RTDIR_EMPTY=$(mktemp -d)
RTDIR_FULL=$(mktemp -d)
mkdir -p "$RTDIR_EMPTY" "$RTDIR_FULL"
python3 -c "
import json
json.dump({'schema_version':1,'records':[{'error_class':'x','recorded_at':'2026-01-01T00:00:00Z','task_fingerprint':{},'command':'x','avoidance_hints':[]}]}, open('$RTDIR_FULL/failure-records.json','w'))
json.dump({'schema_version':1,'patterns':[]}, open('$RTDIR_FULL/success-patterns.json','w'))
"
KEYS_EMPTY=$(python3 Polaris/scripts/polaris_stats.py --runtime-dir "$RTDIR_EMPTY" --json | python3 -c "import json,sys; print(','.join(sorted(json.load(sys.stdin).keys())))")
KEYS_FULL=$(python3 Polaris/scripts/polaris_stats.py --runtime-dir "$RTDIR_FULL" --json | python3 -c "import json,sys; print(','.join(sorted(json.load(sys.stdin).keys())))")
assert_eq "$KEYS_EMPTY" "$KEYS_FULL" "A3-T7: empty and non-empty --json must have identical field sets"
rm -rf "$RTDIR_EMPTY" "$RTDIR_FULL"

# --- Test 8: runtime-events.jsonl parsed for completed runs ---
RTDIR=$(mktemp -d)
mkdir -p "$RTDIR"
echo '{"schema_version":1,"records":[]}' > "$RTDIR/failure-records.json"
echo '{"schema_version":1,"patterns":[]}' > "$RTDIR/success-patterns.json"
# Real event format: state journal entries written by polaris_report.py
printf '{"phase":"planning","status":"in_progress","summary":"planning","ts":"2026-03-16T00:00:00Z","run_id":"r1"}\n' > "$RTDIR/runtime-events.jsonl"
printf '{"phase":"completed","status":"completed","summary":"done","ts":"2026-03-16T00:00:01Z","run_id":"r1"}\n' >> "$RTDIR/runtime-events.jsonl"
printf '{"phase":"planning","status":"in_progress","summary":"planning","ts":"2026-03-16T00:01:00Z","run_id":"r2"}\n' >> "$RTDIR/runtime-events.jsonl"
printf '{"phase":"completed","status":"completed","summary":"done","ts":"2026-03-16T00:01:01Z","run_id":"r2"}\n' >> "$RTDIR/runtime-events.jsonl"
RUNS=$(python3 Polaris/scripts/polaris_stats.py --runtime-dir "$RTDIR" --json | python3 -c "import json,sys; print(json.load(sys.stdin)['total_runs'])")
assert_eq "$RUNS" "2" "A3-T8: runtime-events.jsonl must count 2 completed runs"
rm -rf "$RTDIR"

# --- Test 9: non-completed events must NOT inflate run count ---
RTDIR=$(mktemp -d)
mkdir -p "$RTDIR"
echo '{"schema_version":1,"records":[]}' > "$RTDIR/failure-records.json"
echo '{"schema_version":1,"patterns":[]}' > "$RTDIR/success-patterns.json"
# Mix: 1 completed + 2 non-completed state transitions
printf '{"phase":"planning","status":"in_progress","summary":"planning","ts":"2026-03-16T00:00:00Z","run_id":"r1"}\n' > "$RTDIR/runtime-events.jsonl"
printf '{"phase":"executing","status":"in_progress","summary":"executing","ts":"2026-03-16T00:00:01Z","run_id":"r1"}\n' >> "$RTDIR/runtime-events.jsonl"
printf '{"phase":"completed","status":"completed","summary":"done","ts":"2026-03-16T00:00:02Z","run_id":"r1"}\n' >> "$RTDIR/runtime-events.jsonl"
RUNS=$(python3 Polaris/scripts/polaris_stats.py --runtime-dir "$RTDIR" --json | python3 -c "import json,sys; print(json.load(sys.stdin)['total_runs'])")
assert_eq "$RUNS" "1" "A3-T9: non-completed events must NOT inflate run count"
rm -rf "$RTDIR"

echo "=== A3 Results: $PASS/$TOTAL passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
