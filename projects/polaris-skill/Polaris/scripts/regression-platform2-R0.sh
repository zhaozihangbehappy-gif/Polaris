#!/usr/bin/env bash
set -euo pipefail
PASS=0; FAIL=0; TOTAL=0
SCRIPTS=Polaris/scripts

assert_eq() { TOTAL=$((TOTAL+1)); if [ "$1" = "$2" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: expected='$2' got='$1' — $3"; fi; }
assert_contains() { TOTAL=$((TOTAL+1)); if echo "$1" | grep -qF "$2"; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: output missing '$2' — $3"; fi; }
assert_file_exists() { TOTAL=$((TOTAL+1)); if [ -f "$1" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: file not found '$1' — $2"; fi; }
assert_file_not_exists() { TOTAL=$((TOTAL+1)); if [ ! -f "$1" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: file should not exist '$1' — $2"; fi; }

# --- Test 1: POLARIS_HOME 覆盖全局库路径 ---
CUSTOM_HOME=$(mktemp -d)
RESULT=$(POLARIS_HOME="$CUSTOM_HOME" python3 -c "
import sys; sys.path.insert(0, '$SCRIPTS')
from polaris_experience_store import resolve_global_dir
print(resolve_global_dir())
")
assert_eq "$RESULT" "$CUSTOM_HOME/experience" "R0-1: POLARIS_HOME overrides global dir"
rm -rf "$CUSTOM_HOME"

# --- Test 2: 默认全局库路径 ---
RESULT=$(python3 -c "
import sys, os; sys.path.insert(0, '$SCRIPTS')
os.environ.pop('POLARIS_HOME', None)
from polaris_experience_store import resolve_global_dir
from pathlib import Path
print(resolve_global_dir())
")
EXPECTED="$HOME/.polaris/experience"
assert_eq "$RESULT" "$EXPECTED" "R0-2: default global dir is ~/.polaris/experience"

# --- Test 3: resolve_paths 返回 (global, runtime) ---
RTDIR=$(mktemp -d)
RESULT=$(python3 -c "
import sys; sys.path.insert(0, '$SCRIPTS')
os.environ.pop('POLARIS_HOME', None) if 'os' in dir() else None
import os; os.environ.pop('POLARIS_HOME', None)
from polaris_experience_store import resolve_paths
from pathlib import Path
g, r = resolve_paths(Path('$RTDIR'))
print(f'{r is not None}')
")
assert_eq "$RESULT" "True" "R0-3: resolve_paths returns runtime dir when provided"
rm -rf "$RTDIR"

# --- Test 4: resolve_paths 无 runtime-dir → runtime 为 None ---
RESULT=$(python3 -c "
import sys, os; sys.path.insert(0, '$SCRIPTS')
os.environ.pop('POLARIS_HOME', None)
from polaris_experience_store import resolve_paths
g, r = resolve_paths(None)
print(f'{r is None}')
")
assert_eq "$RESULT" "True" "R0-4: resolve_paths returns None runtime when not provided"

# --- Test 5: atomic_write 成功写入 ---
TMPF=$(mktemp -d)/test-store.json
python3 -c "
import sys; sys.path.insert(0, '$SCRIPTS')
from polaris_experience_store import atomic_write
from pathlib import Path
ok = atomic_write(Path('$TMPF'), {'schema_version': 2, 'records': [{'x': 1}]})
print(ok)
" > /dev/null
assert_file_exists "$TMPF" "R0-5: atomic_write creates file"
CONTENT=$(python3 -c "import json; print(len(json.load(open('$TMPF'))['records']))")
assert_eq "$CONTENT" "1" "R0-5: written content is correct"
rm -rf "$(dirname "$TMPF")"

# --- Test 6: 并发写检测 — mtime 变化 → fail closed ---
TMPDIR_T6=$(mktemp -d)
STORE="$TMPDIR_T6/store.json"
echo '{"schema_version": 2, "records": []}' > "$STORE"
RESULT=$(python3 -c "
import sys, os, time; sys.path.insert(0, '$SCRIPTS')
from polaris_experience_store import atomic_write, safe_load
from pathlib import Path
# Read and get mtime
_, mtime = safe_load(Path('$STORE'))
# Simulate concurrent write: modify file externally
time.sleep(0.05)
Path('$STORE').write_text('{\"schema_version\": 2, \"records\": [{\"x\": 99}]}')
# Now try to write with stale mtime → should fail closed
ok = atomic_write(Path('$STORE'), {'schema_version': 2, 'records': [{'x': 0}]}, prior_mtime=mtime)
print(ok)
" 2>&1)
assert_contains "$RESULT" "False" "R0-6: concurrent write detected → fail closed"
assert_contains "$RESULT" "concurrent write" "R0-6: stderr reports concurrent write"
# Verify the file still has the concurrent writer's data (not overwritten)
VERIFY=$(python3 -c "import json; print(json.load(open('$STORE'))['records'][0]['x'])")
assert_eq "$VERIFY" "99" "R0-6: concurrent writer's data preserved (no silent overwrite)"
rm -rf "$TMPDIR_T6"

# --- Test 7: 损坏 JSON → .bak + 空库 + warning ---
TMPDIR_T7=$(mktemp -d)
STORE="$TMPDIR_T7/failure-records.json"
echo "THIS IS NOT JSON {{{" > "$STORE"
RESULT=$(python3 -c "
import sys; sys.path.insert(0, '$SCRIPTS')
from polaris_experience_store import safe_load
from pathlib import Path
payload, mtime = safe_load(Path('$STORE'))
print(len(payload.get('records', [])))
" 2>&1)
assert_contains "$RESULT" "warning" "R0-7: corrupt file triggers warning"
assert_contains "$RESULT" "0" "R0-7: returns empty store on corruption"
assert_file_exists "$STORE.bak" "R0-7: corrupt file renamed to .bak"
rm -rf "$TMPDIR_T7"

# --- Test 8: merge — dedup by (matching_key, recorded_at); same pair picks better; different pairs both survive ---
RESULT=$(python3 -c "
import sys; sys.path.insert(0, '$SCRIPTS')
from polaris_experience_store import merge_failure_stores
# Case: same (mk, recorded_at) → dedup to 1; different recorded_at → both survive
runtime = {'schema_version': 2, 'records': [
    {'task_fingerprint': {'matching_key': 'aaa'}, 'error_class': 'from_runtime',
     'avoidance_hints': [{'kind': 'set_env', 'vars': {'SRC': 'runtime'}}],
     'recorded_at': '2026-03-17T10:00:00Z', 'source': 'auto',
     'applied_count': 1, 'applied_fail_count': 0,
     'stale': False, 'rejected_by': None}
]}
global_s = {'schema_version': 2, 'records': [
    {'task_fingerprint': {'matching_key': 'aaa'}, 'error_class': 'from_global_same_ts',
     'avoidance_hints': [{'kind': 'set_env', 'vars': {'SRC': 'global'}}],
     'recorded_at': '2026-03-17T10:00:00Z', 'source': 'auto',
     'applied_count': 0, 'applied_fail_count': 0,
     'stale': False, 'rejected_by': None},
    {'task_fingerprint': {'matching_key': 'bbb'}, 'error_class': 'only_global',
     'avoidance_hints': [], 'recorded_at': '2026-03-15T10:00:00Z',
     'source': 'auto', 'applied_count': 0, 'applied_fail_count': 0,
     'stale': False, 'rejected_by': None}
]}
merged = merge_failure_stores(runtime, global_s)
recs = merged['records']
# aaa same timestamp → dedup to 1 (runtime wins by applied_count), bbb from global
aaa_recs = [r for r in recs if r['task_fingerprint']['matching_key'] == 'aaa']
bbb_recs = [r for r in recs if r['task_fingerprint']['matching_key'] == 'bbb']
print(f\"{aaa_recs[0]['error_class']},{bbb_recs[0]['error_class']},{len(recs)}\")
")
assert_eq "$RESULT" "from_runtime,only_global,2" "R0-8: same (mk,ts) deduped, runtime wins by applied_count; global-only included"

# --- Test 9: sync — 新记录追加到全局库 ---
TMPDIR_T9=$(mktemp -d)
GLOBAL_STORE="$TMPDIR_T9/global-failure-records.json"
echo '{"schema_version": 2, "records": []}' > "$GLOBAL_STORE"
RESULT=$(python3 -c "
import sys; sys.path.insert(0, '$SCRIPTS')
from polaris_experience_store import sync_failure_to_global
from pathlib import Path
import json
runtime = {'schema_version': 2, 'records': [
    {'task_fingerprint': {'matching_key': 'new-rec'}, 'error_class': 'test',
     'avoidance_hints': [], 'recorded_at': '2026-03-17T12:00:00Z',
     'source': 'auto', 'stale': False, 'rejected_by': None}
]}
ok = sync_failure_to_global(runtime, Path('$GLOBAL_STORE'))
store = json.load(open('$GLOBAL_STORE'))
print(f'{ok},{len(store[\"records\"])}')
")
assert_eq "$RESULT" "True,1" "R0-9: sync appends new record to global"
rm -rf "$TMPDIR_T9"

# --- Test 10: sync — stale 状态传播到全局库 ---
TMPDIR_T10=$(mktemp -d)
GLOBAL_STORE="$TMPDIR_T10/global-failure-records.json"
python3 -c "
import json
json.dump({'schema_version': 2, 'records': [
    {'task_fingerprint': {'matching_key': 'stale-test'}, 'error_class': 'test',
     'avoidance_hints': [], 'recorded_at': '2026-03-17T12:00:00Z',
     'source': 'auto', 'stale': False, 'rejected_by': None}
]}, open('$GLOBAL_STORE', 'w'))
"
RESULT=$(python3 -c "
import sys; sys.path.insert(0, '$SCRIPTS')
from polaris_experience_store import sync_failure_to_global
from pathlib import Path
import json
# Runtime has same record but marked stale
runtime = {'schema_version': 2, 'records': [
    {'task_fingerprint': {'matching_key': 'stale-test'}, 'error_class': 'test',
     'avoidance_hints': [], 'recorded_at': '2026-03-17T12:00:00Z',
     'source': 'auto', 'stale': True, 'rejected_by': 'user'}
]}
ok = sync_failure_to_global(runtime, Path('$GLOBAL_STORE'))
store = json.load(open('$GLOBAL_STORE'))
rec = store['records'][0]
print(f'{ok},{rec[\"stale\"]},{rec[\"rejected_by\"]}')
")
assert_eq "$RESULT" "True,True,user" "R0-10: stale+rejected propagates to global"
rm -rf "$TMPDIR_T10"

# --- Test 11: sync — 重复记录不追加 ---
TMPDIR_T11=$(mktemp -d)
GLOBAL_STORE="$TMPDIR_T11/global-failure-records.json"
python3 -c "
import json
json.dump({'schema_version': 2, 'records': [
    {'task_fingerprint': {'matching_key': 'existing'}, 'error_class': 'test',
     'avoidance_hints': [], 'recorded_at': '2026-03-17T12:00:00Z',
     'source': 'auto', 'stale': False, 'rejected_by': None}
]}, open('$GLOBAL_STORE', 'w'))
"
RESULT=$(python3 -c "
import sys; sys.path.insert(0, '$SCRIPTS')
from polaris_experience_store import sync_failure_to_global
from pathlib import Path
import json
runtime = {'schema_version': 2, 'records': [
    {'task_fingerprint': {'matching_key': 'existing'}, 'error_class': 'test',
     'avoidance_hints': [], 'recorded_at': '2026-03-17T12:00:00Z',
     'source': 'auto', 'stale': False, 'rejected_by': None}
]}
ok = sync_failure_to_global(runtime, Path('$GLOBAL_STORE'))
store = json.load(open('$GLOBAL_STORE'))
print(f'{ok},{len(store[\"records\"])}')
")
assert_eq "$RESULT" "True,1" "R0-11: duplicate record not appended"
rm -rf "$TMPDIR_T11"

# --- Test 12: 写入失败降级 — 不崩溃 ---
RESULT=$(python3 -c "
import sys; sys.path.insert(0, '$SCRIPTS')
from polaris_experience_store import atomic_write
from pathlib import Path
# Try to write to a non-writable path
ok = atomic_write(Path('/proc/polaris-fake/store.json'), {'records': []})
print(ok)
" 2>&1)
assert_contains "$RESULT" "False" "R0-12: write to bad path returns False"
assert_contains "$RESULT" "warning" "R0-12: degradation warning emitted"

echo "=== R0 Results: $PASS/$TOTAL passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
