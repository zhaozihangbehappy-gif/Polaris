#!/usr/bin/env bash
set -euo pipefail
PASS=0; FAIL=0; TOTAL=0
SCRIPTS=Polaris/scripts

assert_eq() { TOTAL=$((TOTAL+1)); if [ "$1" = "$2" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: expected='$2' got='$1' — $3"; fi; }

# ---------------------------------------------------------------------------
# Gate: merge_failure_stores — stale runtime must NOT shadow updated global
# ---------------------------------------------------------------------------

# M1: Global has stale=true, runtime has stale=false (same key) → merged picks global (stale wins)
M1=$(python3 -c "
import json, sys
sys.path.insert(0, '$SCRIPTS')
import polaris_experience_store as pes

runtime = {'schema_version': 2, 'records': [
    {'task_fingerprint': {'matching_key': 'k1'}, 'recorded_at': 't1',
     'stale': False, 'applied_count': 0, 'applied_fail_count': 0, 'source': 'auto'}
]}
glob = {'schema_version': 2, 'records': [
    {'task_fingerprint': {'matching_key': 'k1'}, 'recorded_at': 't1',
     'stale': True, 'applied_count': 2, 'applied_fail_count': 2, 'source': 'auto'}
]}
merged = pes.merge_failure_stores(runtime, glob)
rec = merged['records'][0]
print('ok' if rec.get('stale') is True else 'bad')
")
assert_eq "$M1" "ok" "M1: global stale=true beats runtime stale=false"

# M2: Global has higher applied_count → merged picks global
M2=$(python3 -c "
import json, sys
sys.path.insert(0, '$SCRIPTS')
import polaris_experience_store as pes

runtime = {'schema_version': 2, 'records': [
    {'task_fingerprint': {'matching_key': 'k2'}, 'recorded_at': 't2',
     'stale': False, 'applied_count': 0, 'applied_fail_count': 0, 'source': 'auto'}
]}
glob = {'schema_version': 2, 'records': [
    {'task_fingerprint': {'matching_key': 'k2'}, 'recorded_at': 't2',
     'stale': False, 'applied_count': 5, 'applied_fail_count': 1, 'source': 'auto'}
]}
merged = pes.merge_failure_stores(runtime, glob)
rec = merged['records'][0]
print(rec.get('applied_count', 0))
")
assert_eq "$M2" "5" "M2: global higher applied_count wins over stale runtime copy"

# M3: Runtime-only and global-only records both included
M3=$(python3 -c "
import json, sys
sys.path.insert(0, '$SCRIPTS')
import polaris_experience_store as pes

runtime = {'schema_version': 2, 'records': [
    {'task_fingerprint': {'matching_key': 'rt_only'}, 'recorded_at': 't3',
     'stale': False, 'applied_count': 0, 'applied_fail_count': 0, 'source': 'auto'}
]}
glob = {'schema_version': 2, 'records': [
    {'task_fingerprint': {'matching_key': 'gl_only'}, 'recorded_at': 't4',
     'stale': False, 'applied_count': 0, 'applied_fail_count': 0, 'source': 'auto'}
]}
merged = pes.merge_failure_stores(runtime, glob)
mks = {r['task_fingerprint']['matching_key'] for r in merged['records']}
print('ok' if mks == {'rt_only', 'gl_only'} else 'bad')
")
assert_eq "$M3" "ok" "M3: disjoint records both included"

# ---------------------------------------------------------------------------
# Gate: merge_success_stores — stale runtime must NOT shadow updated global
# ---------------------------------------------------------------------------

# M4: Global has newer updated_at → merged picks global version
M4=$(python3 -c "
import json, sys
sys.path.insert(0, '$SCRIPTS')
import polaris_experience_store as pes

runtime = {'schema_version': 1, 'patterns': [
    {'fingerprint': 'fp1', 'confidence': 70, 'updated_at': '2025-01-01T00:00:00'}
]}
glob = {'schema_version': 1, 'patterns': [
    {'fingerprint': 'fp1', 'confidence': 85, 'updated_at': '2025-06-01T00:00:00'}
]}
merged = pes.merge_success_stores(runtime, glob)
pat = merged['patterns'][0]
print(pat.get('confidence', 0))
")
assert_eq "$M4" "85" "M4: global newer updated_at wins over stale runtime pattern"

# M5: Global has stale=true, runtime doesn't → merged picks global (stale wins)
M5=$(python3 -c "
import json, sys
sys.path.insert(0, '$SCRIPTS')
import polaris_experience_store as pes

runtime = {'schema_version': 1, 'patterns': [
    {'fingerprint': 'fp2', 'confidence': 80, 'stale': False, 'updated_at': '2025-03-01T00:00:00'}
]}
glob = {'schema_version': 1, 'patterns': [
    {'fingerprint': 'fp2', 'confidence': 60, 'stale': True, 'updated_at': '2025-03-02T00:00:00'}
]}
merged = pes.merge_success_stores(runtime, glob)
pat = merged['patterns'][0]
print('ok' if pat.get('stale') is True else 'bad')
")
assert_eq "$M5" "ok" "M5: global stale=true wins over runtime stale=false"

# M6: Disjoint fingerprints both included
M6=$(python3 -c "
import json, sys
sys.path.insert(0, '$SCRIPTS')
import polaris_experience_store as pes

runtime = {'schema_version': 1, 'patterns': [
    {'fingerprint': 'rt_fp', 'confidence': 70, 'updated_at': '2025-01-01T00:00:00'}
]}
glob = {'schema_version': 1, 'patterns': [
    {'fingerprint': 'gl_fp', 'confidence': 80, 'updated_at': '2025-01-01T00:00:00'}
]}
merged = pes.merge_success_stores(runtime, glob)
fps = {p['fingerprint'] for p in merged['patterns']}
print('ok' if fps == {'rt_fp', 'gl_fp'} else 'bad')
")
assert_eq "$M6" "ok" "M6: disjoint success patterns both included"

# ---------------------------------------------------------------------------
# Gate: multi-hint accumulation — same matching_key, different recorded_at
# ---------------------------------------------------------------------------

# M7: Two global records for same key with different hints both survive merge
M7=$(python3 -c "
import json, sys
sys.path.insert(0, '$SCRIPTS')
import polaris_experience_store as pes

runtime = {'schema_version': 2, 'records': []}
glob = {'schema_version': 2, 'records': [
    {'task_fingerprint': {'matching_key': 'same_task'}, 'recorded_at': 't1',
     'avoidance_hints': [{'kind': 'set_env', 'vars': {'A': '1'}}],
     'stale': False, 'applied_count': 0, 'applied_fail_count': 0, 'source': 'auto'},
    {'task_fingerprint': {'matching_key': 'same_task'}, 'recorded_at': 't2',
     'avoidance_hints': [{'kind': 'rewrite_cwd', 'cwd': '/tmp'}],
     'stale': False, 'applied_count': 0, 'applied_fail_count': 0, 'source': 'auto'}
]}
merged = pes.merge_failure_stores(runtime, glob)
recs = merged['records']
hints_kinds = sorted([r['avoidance_hints'][0]['kind'] for r in recs])
print(','.join(hints_kinds))
")
assert_eq "$M7" "rewrite_cwd,set_env" "M7: two records for same key with different hints both survive"

# M8: Runtime and global each have different records for same key → both survive
M8=$(python3 -c "
import json, sys
sys.path.insert(0, '$SCRIPTS')
import polaris_experience_store as pes

runtime = {'schema_version': 2, 'records': [
    {'task_fingerprint': {'matching_key': 'same_task'}, 'recorded_at': 't3',
     'avoidance_hints': [{'kind': 'set_timeout', 'timeout_ms': 5000}],
     'stale': False, 'applied_count': 0, 'applied_fail_count': 0, 'source': 'auto'}
]}
glob = {'schema_version': 2, 'records': [
    {'task_fingerprint': {'matching_key': 'same_task'}, 'recorded_at': 't4',
     'avoidance_hints': [{'kind': 'append_flags', 'flags': ['--verbose']}],
     'stale': False, 'applied_count': 0, 'applied_fail_count': 0, 'source': 'auto'}
]}
merged = pes.merge_failure_stores(runtime, glob)
recs = merged['records']
hints_kinds = sorted([r['avoidance_hints'][0]['kind'] for r in recs])
print(f'{len(recs)},{','.join(hints_kinds)}')
")
assert_eq "$M8" "2,append_flags,set_timeout" "M8: runtime+global records with same key but different timestamps both survive"

# M9: Same (mk, recorded_at) pair in both stores → deduplicated to one, picks better
M9=$(python3 -c "
import json, sys
sys.path.insert(0, '$SCRIPTS')
import polaris_experience_store as pes

runtime = {'schema_version': 2, 'records': [
    {'task_fingerprint': {'matching_key': 'dup_task'}, 'recorded_at': 't5',
     'avoidance_hints': [{'kind': 'set_env'}],
     'stale': False, 'applied_count': 0, 'applied_fail_count': 0, 'source': 'auto'}
]}
glob = {'schema_version': 2, 'records': [
    {'task_fingerprint': {'matching_key': 'dup_task'}, 'recorded_at': 't5',
     'avoidance_hints': [{'kind': 'set_env'}],
     'stale': True, 'applied_count': 3, 'applied_fail_count': 3, 'source': 'auto'}
]}
merged = pes.merge_failure_stores(runtime, glob)
recs = merged['records']
print(f'{len(recs)},{recs[0].get(\"stale\")}')
")
assert_eq "$M9" "1,True" "M9: same (mk,recorded_at) deduped to one, stale version wins"

# ---------------------------------------------------------------------------
# Gate: legacy bare-list format loaded through safe_load
# ---------------------------------------------------------------------------

# M10: success_patterns.load_store handles legacy bare-list JSON
M10=$(python3 -c "
import sys, json, tempfile
sys.path.insert(0, '$SCRIPTS')
import polaris_success_patterns as psp
from pathlib import Path

# Write a bare-list legacy file
tmp = tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w')
json.dump([{'pattern_id': 'legacy1', 'confidence': 70}], tmp)
tmp.close()
store = psp.load_store(Path(tmp.name))
print(f'{len(store.get(\"patterns\", []))},{store[\"patterns\"][0].get(\"pattern_id\")}')
import os; os.unlink(tmp.name)
" 2>/dev/null)
assert_eq "$M10" "1,legacy1" "M10: bare-list success-patterns loaded without corruption"

# M11: safe_load wraps bare list into dict using default_factory hint
M11=$(python3 -c "
import sys, json, tempfile
sys.path.insert(0, '$SCRIPTS')
import polaris_experience_store as pes
from pathlib import Path

# Bare list file, patterns-style default
tmp = tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w')
json.dump([{'fp': 'x'}], tmp)
tmp.close()
payload, _ = pes.safe_load(Path(tmp.name), default_factory={'schema_version': 1, 'patterns': []})
print(f'{type(payload).__name__},{len(payload.get(\"patterns\", []))}')
import os; os.unlink(tmp.name)
" 2>/dev/null)
assert_eq "$M11" "dict,1" "M11: safe_load wraps bare list into patterns dict"

echo "=== Merge Gate Results: $PASS/$TOTAL passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
