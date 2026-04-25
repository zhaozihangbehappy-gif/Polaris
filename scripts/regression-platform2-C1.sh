#!/usr/bin/env bash
# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

set -euo pipefail
PASS=0; FAIL=0; TOTAL=0
SCRIPTS=Polaris/scripts

assert_eq() { TOTAL=$((TOTAL+1)); if [ "$1" = "$2" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: expected='$2' got='$1' — $3"; fi; }
assert_contains() { TOTAL=$((TOTAL+1)); if echo "$1" | grep -qF "$2"; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: output missing '$2' — $3"; fi; }

# R1: Isolate from global experience library
export POLARIS_HOME=$(mktemp -d)
_c1_cleanup() { rm -rf "$POLARIS_HOME"; }
trap _c1_cleanup EXIT

# --- Test 1: npm 命令自动加载 node pack ---
RTDIR=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "npm test" --runtime-dir "$RTDIR" 2>&1 || true
PREBUILT_COUNT=$(python3 -c "
import json
try:
    r=json.load(open('$RTDIR/failure-records.json'))['records']
    print(len([x for x in r if x.get('source')=='prebuilt' and x.get('ecosystem')=='node']))
except: print(0)
")
assert_eq "$((PREBUILT_COUNT > 0 ? 1 : 0))" "1" "C1-T1: node prebuilt records loaded"
rm -rf "$RTDIR"

# --- Test 2: --no-prebuilt 禁止加载 ---
rm -rf "$POLARIS_HOME/experience"
RTDIR=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "npm test" --no-prebuilt --runtime-dir "$RTDIR" 2>&1 || true
PREBUILT_COUNT=$(python3 -c "
import json
try:
    r=json.load(open('$RTDIR/failure-records.json'))['records']
    print(len([x for x in r if x.get('source')=='prebuilt']))
except: print(0)
")
assert_eq "$PREBUILT_COUNT" "0" "C1-T2: no prebuilt records with --no-prebuilt"
rm -rf "$RTDIR"

# --- Test 3: 幂等性 — 第二次运行不重复加载 ---
rm -rf "$POLARIS_HOME/experience"
RTDIR=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "npm test" --runtime-dir "$RTDIR" 2>&1 || true
COUNT1=$(python3 -c "
import json
try:
    r=json.load(open('$RTDIR/failure-records.json'))['records']
    print(len([x for x in r if x.get('source')=='prebuilt']))
except: print(0)
")
python3 "$SCRIPTS/polaris_cli.py" run "npm test" --runtime-dir "$RTDIR" --resume 2>&1 || true
COUNT2=$(python3 -c "
import json
try:
    r=json.load(open('$RTDIR/failure-records.json'))['records']
    print(len([x for x in r if x.get('source')=='prebuilt']))
except: print(0)
")
assert_eq "$COUNT1" "$COUNT2" "C1-T3: prebuilt records not duplicated on second run"
rm -rf "$RTDIR"

# --- Test 4: reset-prebuilt 只删 prebuilt ---
rm -rf "$POLARIS_HOME/experience"
RTDIR=$(mktemp -d)
# Manually create a store with both prebuilt and auto records
python3 -c "
import json, datetime
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
records = [
    {'task_fingerprint': {'matching_key': 'pb1'}, 'command': 'prebuilt-node',
     'error_class': 'missing_dependency', 'stderr_summary': '', 'repair_classification': 'prebuilt',
     'avoidance_hints': [{'kind': 'set_env', 'vars': {'X': '1'}}],
     'recorded_at': now, 'asset_version': 2,
     'applied_count': 0, 'applied_fail_count': 0, 'stale': False, 'rejected_by': None,
     'source': 'prebuilt', 'ecosystem': 'node'},
    {'task_fingerprint': {'matching_key': 'user-rec'}, 'command': 'user-cmd',
     'error_class': 'unknown', 'stderr_summary': '', 'repair_classification': 'unknown',
     'avoidance_hints': [], 'recorded_at': now, 'asset_version': 2,
     'applied_count': 0, 'applied_fail_count': 0, 'stale': False, 'rejected_by': None,
     'source': 'auto'}
]
json.dump({'schema_version': 2, 'records': records}, open('$RTDIR/failure-records.json', 'w'))
"
python3 "$SCRIPTS/polaris_cli.py" experience reset-prebuilt --runtime-dir "$RTDIR" 2>&1
REMAINING=$(python3 -c "
import json
r=json.load(open('$RTDIR/failure-records.json'))['records']
prebuilt=len([x for x in r if x.get('source')=='prebuilt'])
auto=len([x for x in r if x.get('source')=='auto'])
print(f'{prebuilt},{auto}')
")
assert_eq "$REMAINING" "0,1" "C1-T4: prebuilt deleted, auto preserved"
rm -rf "$RTDIR"

# --- Test 5: python 命令加载 python pack ---
RTDIR=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "python3 -m pytest" --runtime-dir "$RTDIR" 2>&1 || true
PREBUILT_ECO=$(python3 -c "
import json
try:
    r=json.load(open('$RTDIR/failure-records.json'))['records']
    ecos=set(x.get('ecosystem','') for x in r if x.get('source')=='prebuilt')
    print(','.join(sorted(ecos)))
except: print('')
")
assert_contains "$PREBUILT_ECO" "python" "C1-T5: python prebuilt loaded for pytest command"
rm -rf "$RTDIR"

# --- Test 6: go 命令加载 go pack ---
RTDIR=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "go test ./..." --runtime-dir "$RTDIR" 2>&1 || true
PREBUILT_ECO=$(python3 -c "
import json
try:
    r=json.load(open('$RTDIR/failure-records.json'))['records']
    ecos=set(x.get('ecosystem','') for x in r if x.get('source')=='prebuilt')
    print(','.join(sorted(ecos)))
except: print('')
")
assert_contains "$PREBUILT_ECO" "go" "C1-T6: go prebuilt loaded for go test command"
rm -rf "$RTDIR"

# --- Test 7: experience pack 格式符合 schema v2 ---
python3 -c "
import json, sys
for eco in ['node', 'python', 'go']:
    pack = json.load(open(f'Polaris/experience-packs/{eco}.json'))
    assert 'ecosystem' in pack, f'{eco}: missing ecosystem field'
    assert 'pack_version' in pack, f'{eco}: missing pack_version'
    valid_kinds = {'append_flags', 'set_env', 'rewrite_cwd', 'set_timeout', 'set_locale', 'create_dir', 'retry_with_backoff', 'install_package'}
    for rec in pack['records']:
        for hint in rec.get('avoidance_hints', []):
            assert hint['kind'] in valid_kinds, f'{eco}: invalid hint kind {hint[\"kind\"]}'
print('pack_schema_ok')
"
SCHEMA_OK=$?
assert_eq "$SCHEMA_OK" "0" "C1-T7: all experience packs use valid hint primitives"

# --- Test 8: 预置经验能被真实 fingerprint + error_class 的 query 命中 (discount=0.5) ---
rm -rf "$POLARIS_HOME/experience"
RTDIR=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "npm --version" --no-prebuilt --runtime-dir "$RTDIR" 2>&1 || true
# 手动加载 node pack
python3 -c "
import sys; sys.path.insert(0, '$SCRIPTS')
import polaris_failure_records as pfr
from pathlib import Path
store_path = Path('$RTDIR/failure-records.json')
store = pfr.load_store(store_path)
import json
pack = json.load(open('Polaris/experience-packs/node.json'))
for i, prec in enumerate(pack['records']):
    fp = {'matching_key': f'prebuilt-node-{i:04x}', 'command_key': 'prebuilt-node',
          'raw_descriptor': prec.get('stderr_pattern',''), 'normalized_descriptor': prec.get('stderr_pattern','')}
    pfr.record(store, fp, 'prebuilt-node', prec.get('error_class','unknown'),
               prec.get('description',''), 'prebuilt', prec.get('avoidance_hints',[]),
               source='prebuilt', ecosystem='node')
pfr.write_store(store_path, store)
"
FP=$(python3 "$SCRIPTS/polaris_task_fingerprint.py" compute --command "npm test" --cwd "$RTDIR" 2>&1)
MK=$(echo "$FP" | python3 -c "import sys,json; print(json.load(sys.stdin)['matching_key'])")
CK=$(echo "$FP" | python3 -c "import sys,json; print(json.load(sys.stdin)['command_key'])")

# 8a: query with matching error_class → discount=0.5, hints applicable
RESULT=$(python3 "$SCRIPTS/polaris_failure_records.py" query --matching-key "$MK" --command-key "$CK" --ecosystem node --error-class missing_dependency --store "$RTDIR/failure-records.json" 2>&1)
TIER=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('match_tier',''))")
HINT_COUNT=$(echo "$RESULT" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('avoidance_hints',[])))")
DISCOUNT=$(echo "$RESULT" | python3 -c "import sys,json; h=json.load(sys.stdin).get('avoidance_hints',[]); print(h[0].get('confidence_discount', -1) if h else -1)")
assert_eq "$TIER" "ecosystem" "C1-T8a: prebuilt hit via ecosystem tier with error_class"
assert_eq "$((HINT_COUNT > 0 ? 1 : 0))" "1" "C1-T8a: prebuilt hints returned"
assert_eq "$DISCOUNT" "0.5" "C1-T8a: error_class-matched discount is 0.5 (at apply threshold)"

# 8b: query without error_class → discount=0.4, below adapter apply threshold
RESULT_NO_EC=$(python3 "$SCRIPTS/polaris_failure_records.py" query --matching-key "$MK" --command-key "$CK" --ecosystem node --store "$RTDIR/failure-records.json" 2>&1)
DISCOUNT_NO_EC=$(echo "$RESULT_NO_EC" | python3 -c "import sys,json; h=json.load(sys.stdin).get('avoidance_hints',[]); print(h[0].get('confidence_discount', -1) if h else -1)")
assert_eq "$DISCOUNT_NO_EC" "0.4" "C1-T8b: no error_class → discount 0.4 (below apply threshold)"

# 8c: query with non-matching error_class → falls back to 0.4
RESULT_WRONG_EC=$(python3 "$SCRIPTS/polaris_failure_records.py" query --matching-key "$MK" --command-key "$CK" --ecosystem node --error-class nonexistent_class --store "$RTDIR/failure-records.json" 2>&1)
DISCOUNT_WRONG=$(echo "$RESULT_WRONG_EC" | python3 -c "import sys,json; h=json.load(sys.stdin).get('avoidance_hints',[]); print(h[0].get('confidence_discount', -1) if h else -1)")
assert_eq "$DISCOUNT_WRONG" "0.4" "C1-T8c: wrong error_class → falls back to 0.4"
rm -rf "$RTDIR"

# --- Test 9: e2e — orchestrator 传 error_class 给 ecosystem query ---
# 模拟: 首次运行 npm 命令失败 → 记录 error_class=missing_dependency
# 第二次运行 → orchestrator 查到 prior error_class → 传给 query → prebuilt 匹配 → discount=0.5
rm -rf "$POLARIS_HOME/experience"
RTDIR=$(mktemp -d)
# 首次: 跑一个会失败的 npm 命令（prebuilt 已自动加载）
python3 "$SCRIPTS/polaris_cli.py" run "node -e \"require('nonexistent_module_xyz_123')\"" --runtime-dir "$RTDIR" 2>&1 || true
# 验证失败记录存在且有 error_class
HAS_FAILURE=$(python3 -c "
import json
try:
    r=json.load(open('$RTDIR/failure-records.json'))['records']
    auto_recs = [x for x in r if x.get('source') != 'prebuilt']
    print(len(auto_recs) > 0 and auto_recs[-1].get('error_class','') != '')
except: print(False)
")
assert_eq "$HAS_FAILURE" "True" "C1-T9a: first run records failure with error_class"
# 拿到记录的 error_class
RECORDED_EC=$(python3 -c "
import json
r=json.load(open('$RTDIR/failure-records.json'))['records']
auto_recs = [x for x in r if x.get('source') != 'prebuilt']
print(auto_recs[-1].get('error_class','none') if auto_recs else 'none')
")
# 第二次: resume 运行同命令 → 验证 experience_hints 里有 discount >= 0.5 的 hints
python3 "$SCRIPTS/polaris_cli.py" run "node -e \"require('nonexistent_module_xyz_123')\"" --runtime-dir "$RTDIR" --resume 2>&1 || true
# 检查 execution-state.json 里 experience_hints.avoid 的 discount
APPLIED_DISCOUNTS=$(python3 -c "
import json
try:
    state = json.load(open('$RTDIR/execution-state.json'))
    hints_raw = state.get('artifacts', {}).get('experience_hints')
    if isinstance(hints_raw, str):
        hints = json.loads(hints_raw)
    else:
        hints = hints_raw or {}
    avoids = hints.get('avoid', [])
    discounts = [h.get('confidence_discount', 1.0) for h in avoids]
    # Check if any hint has discount >= 0.5 (from error_class-matched prebuilt)
    has_applicable = any(d >= 0.5 for d in discounts)
    print(has_applicable)
except Exception as e:
    print(f'error: {e}')
")
assert_eq "$APPLIED_DISCOUNTS" "True" "C1-T9b: second run gets ecosystem hints with discount >= 0.5 (error_class wired)"
rm -rf "$RTDIR"

# --- Test 10: POLARIS_NO_PREBUILT=1 env var 禁止加载 ---
rm -rf "$POLARIS_HOME/experience"
RTDIR=$(mktemp -d)
POLARIS_NO_PREBUILT=1 python3 "$SCRIPTS/polaris_cli.py" run "npm test" --runtime-dir "$RTDIR" 2>&1 || true
PREBUILT_COUNT=$(python3 -c "
import json
try:
    r=json.load(open('$RTDIR/failure-records.json'))['records']
    print(len([x for x in r if x.get('source')=='prebuilt']))
except: print(0)
")
assert_eq "$PREBUILT_COUNT" "0" "C1-T8: POLARIS_NO_PREBUILT=1 blocks prebuilt loading"
rm -rf "$RTDIR"

echo "=== C1 Results: $PASS/$TOTAL passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
