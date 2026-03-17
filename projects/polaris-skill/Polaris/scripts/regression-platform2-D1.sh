#!/usr/bin/env bash
set -euo pipefail
PASS=0; FAIL=0; TOTAL=0
SCRIPTS=Polaris/scripts

assert_eq() { TOTAL=$((TOTAL+1)); if [ "$1" = "$2" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: expected='$2' got='$1' — $3"; fi; }
assert_contains() { TOTAL=$((TOTAL+1)); if echo "$1" | grep -qF "$2"; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: output missing '$2' — $3"; fi; }

# R1: Isolate from global experience library
export POLARIS_HOME=$(mktemp -d)
trap 'rm -rf "$POLARIS_HOME"' EXIT

# --- Test 1: 执行后 event-log 包含 adapter 事件 ---
RTDIR=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "echo adapter-trace-test" --runtime-dir "$RTDIR" 2>&1 || true
HAS_SELECTED=$(python3 -c "
import json
events=[json.loads(l) for l in open('$RTDIR/runtime-events.jsonl') if l.strip()]
print(any(e.get('type')=='adapter_selected' for e in events))
")
HAS_OUTCOME=$(python3 -c "
import json
events=[json.loads(l) for l in open('$RTDIR/runtime-events.jsonl') if l.strip()]
print(any(e.get('type')=='adapter_outcome' for e in events))
")
assert_eq "$HAS_SELECTED" "True" "D1-T1: event-log must contain adapter_selected"
assert_eq "$HAS_OUTCOME" "True" "D1-T1: event-log must contain adapter_outcome"
rm -rf "$RTDIR"

# --- Test 2: adapter_selected 事件结构完整 ---
RTDIR=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "echo structure-test" --runtime-dir "$RTDIR" 2>&1 || true
FIELDS=$(python3 -c "
import json
events=[json.loads(l) for l in open('$RTDIR/runtime-events.jsonl') if l.strip()]
sel=[e for e in events if e.get('type')=='adapter_selected']
if not sel:
    print(False)
else:
    s = sel[0]
    required={'type','ts','adapter','score','scenario_fingerprint','cache_hit'}
    print(required.issubset(set(s.keys())))
")
assert_eq "$FIELDS" "True" "D1-T2: adapter_selected has all required fields"
rm -rf "$RTDIR"

# --- Test 3: adapter_outcome 事件包含 duration ---
RTDIR=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "echo timing-test" --runtime-dir "$RTDIR" 2>&1 || true
DURATION=$(python3 -c "
import json
events=[json.loads(l) for l in open('$RTDIR/runtime-events.jsonl') if l.strip()]
out=[e for e in events if e.get('type')=='adapter_outcome']
print(out[0].get('duration_ms', -1) if out else -1)
")
assert_eq "$((DURATION > 0 ? 1 : 0))" "1" "D1-T3: duration_ms must be positive"
rm -rf "$RTDIR"

# --- Test 4: stats 显示 adapter 维度 ---
RTDIR=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "echo stats-1" --runtime-dir "$RTDIR" 2>&1 || true
python3 "$SCRIPTS/polaris_cli.py" run "echo stats-2" --runtime-dir "$RTDIR" --resume 2>&1 || true
OUT=$(python3 "$SCRIPTS/polaris_stats.py" --runtime-dir "$RTDIR" 2>&1)
assert_contains "$OUT" "Adapter Performance" "D1-T4: stats must show adapter section"
assert_contains "$OUT" "calls" "D1-T4: stats must show call counts"
assert_contains "$OUT" "success" "D1-T4: stats must show success rate"
rm -rf "$RTDIR"

# --- Test 5: 失败执行的 outcome 事件正确 ---
RTDIR=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "false" --runtime-dir "$RTDIR" 2>&1 || true
SUCCESS_FLAG=$(python3 -c "
import json
events=[json.loads(l) for l in open('$RTDIR/runtime-events.jsonl') if l.strip()]
out=[e for e in events if e.get('type')=='adapter_outcome']
print(out[0].get('success', True) if out else 'missing')
")
assert_eq "$SUCCESS_FLAG" "False" "D1-T5: failed command → success=false in outcome"
rm -rf "$RTDIR"

# --- Test 6: adapter_outcome 的 success 与 execution-state.json 一致 ---
RTDIR=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "echo consistency-test" --runtime-dir "$RTDIR" 2>&1 || true
STATE_STATUS=$(python3 -c "import json; print(json.load(open('$RTDIR/execution-state.json')).get('status',''))")
EVENT_SUCCESS=$(python3 -c "
import json
events=[json.loads(l) for l in open('$RTDIR/runtime-events.jsonl') if l.strip()]
out=[e for e in events if e.get('type')=='adapter_outcome']
print(out[0].get('success', False) if out else 'missing')
")
EXPECTED_SUCCESS="True"
if [ "$STATE_STATUS" != "completed" ]; then EXPECTED_SUCCESS="False"; fi
assert_eq "$EVENT_SUCCESS" "$EXPECTED_SUCCESS" "D1-T6: outcome success matches state status"
rm -rf "$RTDIR"

# --- Test 7: stats adapter 计数与 event-log 事件数一致 ---
RTDIR=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "echo count-1" --runtime-dir "$RTDIR" 2>&1 || true
python3 "$SCRIPTS/polaris_cli.py" run "echo count-2" --runtime-dir "$RTDIR" --resume 2>&1 || true
EVENT_COUNT=$(python3 -c "
import json
events=[json.loads(l) for l in open('$RTDIR/runtime-events.jsonl') if l.strip()]
print(len([e for e in events if e.get('type')=='adapter_outcome']))
")
STATS_COUNT=$(python3 -c "
import json, sys
sys.path.insert(0, '$SCRIPTS')
import polaris_cli
from pathlib import Path
stats = polaris_cli._build_stats(Path('$RTDIR'))
total = sum(s['calls'] for s in stats.get('adapter_stats', {}).values())
print(total)
")
assert_eq "$EVENT_COUNT" "$STATS_COUNT" "D1-T7: stats call count matches event-log count"
rm -rf "$RTDIR"

echo "=== D1 Results: $PASS/$TOTAL passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
