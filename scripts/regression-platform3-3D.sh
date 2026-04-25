#!/usr/bin/env bash
# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

set -euo pipefail
PASS=0; FAIL=0; TOTAL=0
SCRIPTS=Polaris/scripts
PACKS=Polaris/experience-packs

assert_eq() { TOTAL=$((TOTAL+1)); if [ "$1" = "$2" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: expected='$2' got='$1' — $3"; fi; }
assert_contains() { TOTAL=$((TOTAL+1)); if grep -qF "$2" <<< "$1"; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: output missing '$2' — $3"; fi; }
assert_not_contains() { TOTAL=$((TOTAL+1)); if ! grep -qF "$2" <<< "$1"; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: output should NOT contain '$2' — $3"; fi; }

# Setup: create a fake global store with mixed records
export POLARIS_HOME=$(mktemp -d)
cleanup() { rm -rf "$POLARIS_HOME"; }
trap cleanup EXIT

mkdir -p "$POLARIS_HOME/experience"

# Create test failure store with various record types
python3 -c "
import json
store = {
    'schema_version': 2,
    'records': [
        # Record 0: Contributable — verified auto record
        {
            'ecosystem': 'python',
            'error_class': 'missing_dependency',
            'stderr_pattern': 'ModuleNotFoundError: No module named .custom_lib.',
            'avoidance_hints': [{'kind': 'set_env', 'vars': {'PYTHONPATH': '/opt/libs'}}],
            'description': 'Custom lib not in path — add to PYTHONPATH',
            'source': 'auto',
            'applied_count': 3,
            'applied_fail_count': 0,
            'matching_key': 'mk-test-1',
            'command_key': 'ck-test-1',
            'command': 'python3 myapp.py',
            'stderr_summary': 'ModuleNotFoundError on custom_lib',
            'fingerprint': 'fp123',
            'first_seen': '2026-03-10T00:00:00Z',
            'last_seen': '2026-03-15T00:00:00Z',
        },
        # Record 1: Prebuilt — should NOT be contributed (3D-G1)
        {
            'ecosystem': 'python',
            'error_class': 'syntax_error',
            'stderr_pattern': 'SyntaxError: invalid syntax',
            'avoidance_hints': [{'kind': 'set_env', 'vars': {'PYTHONDONTWRITEBYTECODE': '1'}}],
            'source': 'prebuilt',
            'applied_count': 5,
            'applied_fail_count': 0,
        },
        # Record 2: Unverified — applied_count=0, should NOT be contributed (3D-G1)
        {
            'ecosystem': 'node',
            'error_class': 'missing_dependency',
            'stderr_pattern': 'Cannot find module .my-custom-pkg.',
            'avoidance_hints': [{'kind': 'set_env', 'vars': {'NODE_PATH': '/opt/node'}}],
            'source': 'auto',
            'applied_count': 0,
            'applied_fail_count': 0,
            'ecosystem': 'node',
        },
        # Record 3: Has failures — should NOT be contributed (3D-G1)
        {
            'ecosystem': 'go',
            'error_class': 'build_error',
            'stderr_pattern': 'go: some custom build error',
            'avoidance_hints': [{'kind': 'set_env', 'vars': {'CGO_ENABLED': '0'}}],
            'source': 'auto',
            'applied_count': 2,
            'applied_fail_count': 1,
        },
        # Record 4: Contributable — user correction
        {
            'ecosystem': 'docker',
            'error_class': 'permission_denial',
            'stderr_pattern': 'docker: permission denied on custom socket',
            'avoidance_hints': [{'kind': 'set_env', 'vars': {'DOCKER_HOST': 'unix:///run/user/1000/docker.sock'}}],
            'description': 'Custom docker socket permission fix',
            'source': 'user_correction',
            'applied_count': 1,
            'applied_fail_count': 0,
            'command': 'docker ps',
            'fingerprint': 'fp456',
            'matching_key': 'mk-docker-1',
        },
    ]
}
json.dump(store, open('$POLARIS_HOME/experience/failure-records.json', 'w'), indent=2)
"

# --- 3D-G1: Prebuilt and unverified records are NOT contributed ---
G1=$(python3 "$SCRIPTS/polaris_cli.py" experience contribute --dry-run 2>&1) || true
# Should show exactly 2 contributable records (record 0 and 4)
G1_COUNT=$(echo "$G1" | grep -c "✓\|⚠" || true)
assert_eq "$G1_COUNT" "2" "3D-G1: only 2 verified records qualify (prebuilt/unverified/failed excluded)"

# --- 3D-G2: Output does NOT contain sensitive fields ---
OUTFILE=$(mktemp)
python3 "$SCRIPTS/polaris_cli.py" experience contribute --output "$OUTFILE" 2>&1 || true
OUTJSON=$(cat "$OUTFILE")
assert_not_contains "$OUTJSON" "stderr_summary" "3D-G2a: no stderr_summary in output"
assert_not_contains "$OUTJSON" "mk-test-1" "3D-G2b: no matching_key in output"
assert_not_contains "$OUTJSON" "ck-test-1" "3D-G2c: no command_key in output"
assert_not_contains "$OUTJSON" "fp123" "3D-G2d: no fingerprint in output"
assert_not_contains "$OUTJSON" "python3 myapp.py" "3D-G2e: no command in output"

# --- 3D-G3: Output matches contribution schema ---
G3=$(python3 -c "
import json
data = json.load(open('$OUTFILE'))
ok = True
if data.get('schema_version') != 1: ok = False
if not isinstance(data.get('records'), list): ok = False
if len(data['records']) != 2: ok = False
for rec in data['records']:
    for field in ['ecosystem', 'error_class', 'stderr_pattern', 'avoidance_hints', 'applied_count', 'contributor_hash', 'source']:
        if field not in rec:
            ok = False
    if rec.get('source') != 'contributed':
        ok = False
print('yes' if ok else 'no')
")
assert_eq "$G3" "yes" "3D-G3: output conforms to contribution schema"

# --- 3D-G4: --dry-run does NOT write files ---
DRYOUT=$(mktemp)
rm -f "$DRYOUT"  # make sure it doesn't exist
python3 "$SCRIPTS/polaris_cli.py" experience contribute --dry-run --output "$DRYOUT" 2>&1 || true
assert_eq "$([ -f "$DRYOUT" ] && echo 'exists' || echo 'absent')" "absent" "3D-G4: --dry-run does not write output file"

# --- 3D-G5: validate.py rejects invalid regex and invalid hint kind ---
# Create an invalid contribution
INVALID=$(mktemp)
python3 -c "
import json
json.dump({
    'schema_version': 1,
    'records': [
        {
            'ecosystem': 'python',
            'error_class': 'test',
            'stderr_pattern': '(abc+)+',
            'avoidance_hints': [{'kind': 'dangerous_kind'}],
            'source': 'contributed',
        }
    ]
}, open('$INVALID', 'w'))
"
G5=$(python3 "$SCRIPTS/validate_contribution.py" "$INVALID" 2>&1) || true
assert_contains "$G5" "REJECTED" "3D-G5a: validator rejects invalid contribution"
assert_contains "$G5" "invalid kind" "3D-G5b: validator catches bad hint kind"
rm -f "$INVALID"

# Also test that a valid contribution passes
G5V=$(python3 "$SCRIPTS/validate_contribution.py" "$OUTFILE" 2>&1) || true
assert_contains "$G5V" "ACCEPTED" "3D-G5c: validator accepts valid contribution"

# --- 3D-G6: Duplicate patterns are flagged ---
# Record 0 has a custom pattern (not in packs), so no duplicate
# Let's add a record that DOES match an existing pack pattern
python3 -c "
import json
store = json.load(open('$POLARIS_HOME/experience/failure-records.json'))
store['records'].append({
    'ecosystem': 'python',
    'error_class': 'missing_dependency',
    'stderr_pattern': \"ModuleNotFoundError: No module named '([^']+)'\",
    'avoidance_hints': [{'kind': 'set_env', 'vars': {'PIP_INSTALL': '1'}}],
    'source': 'auto',
    'applied_count': 2,
    'applied_fail_count': 0,
})
json.dump(store, open('$POLARIS_HOME/experience/failure-records.json', 'w'))
"
G6=$(python3 "$SCRIPTS/polaris_cli.py" experience contribute --dry-run 2>&1) || true
# Should flag the duplicate
G6_DUP=$(echo "$G6" | grep -c "DUPLICATE" || true)
assert_eq "$((G6_DUP >= 1 ? 1 : 0))" "1" "3D-G6: duplicate patterns flagged"

# --- 3D-G7: After merging a contribution, R3 still passes ---
# Simulate merge: add a contributed record to a shard and run R3
TMPPACK=$(mktemp -d)
cp -r "$PACKS"/* "$TMPPACK/"
python3 -c "
import json
shard = json.load(open('$TMPPACK/python/missing_dependency.json'))
shard['records'].append({
    'ecosystem': 'python',
    'error_class': 'missing_dependency',
    'stderr_pattern': 'ModuleNotFoundError: No module named .custom_lib.',
    'avoidance_hints': [{'kind': 'set_env', 'vars': {'PYTHONPATH': '/opt/libs'}}],
    'description': 'Custom lib not in path',
    'source': 'contributed',
    'applied_count': 3,
})
json.dump(shard, open('$TMPPACK/python/missing_dependency.json', 'w'), indent=2)
# Update index record count
idx = json.load(open('$TMPPACK/index.json'))
idx['ecosystems']['python']['total_records'] += 1
json.dump(idx, open('$TMPPACK/index.json', 'w'), indent=2)
"
# Verify the merged shard is still valid (regex, schema)
G7=$(python3 -c "
import json, re
shard = json.load(open('$TMPPACK/python/missing_dependency.json'))
ok = True
for rec in shard['records']:
    try:
        re.compile(rec['stderr_pattern'])
    except: ok = False
    if not rec.get('avoidance_hints'): ok = False
print('pass' if ok else 'fail')
")
assert_eq "$G7" "pass" "3D-G7: merged shard passes validation"
rm -rf "$TMPPACK"

# --- 3D-G8: End-to-end: contribute → validate → merge → second-user consumes ---
# Simulates the full pipeline:
#   User A contributes → CI validates → merge into pack → User B (fresh env) hits it
# Already have the contribution file from G3

# Step 1: CI validation must pass
E2E_VALID=$(python3 "$SCRIPTS/validate_contribution.py" "$OUTFILE" --packs-dir "$PACKS" 2>&1) || true
E2E_VALID_OK=$(echo "$E2E_VALID" | grep -c "ACCEPTED" || true)

# Step 2: Merge into a temporary pack directory (simulating central merge)
E2E_PACK=$(mktemp -d)
cp -r "$PACKS"/* "$E2E_PACK/"
python3 -c "
import json, os
contrib = json.load(open('$OUTFILE'))
for rec in contrib['records']:
    eco = rec['ecosystem']
    ec = rec['error_class']
    shard_path = os.path.join('$E2E_PACK', eco, ec + '.json')
    try:
        shard = json.load(open(shard_path))
    except:
        os.makedirs(os.path.join('$E2E_PACK', eco), exist_ok=True)
        shard = {'ecosystem': eco, 'error_class': ec, 'shard_version': '3.0', 'records': []}
    shard['records'].append(rec)
    json.dump(shard, open(shard_path, 'w'), indent=2)
    idx_path = os.path.join('$E2E_PACK', 'index.json')
    idx = json.load(open(idx_path))
    if eco in idx['ecosystems']:
        if ec not in idx['ecosystems'][eco]['error_classes']:
            idx['ecosystems'][eco]['error_classes'].append(ec)
        idx['ecosystems'][eco]['total_records'] += 1
    json.dump(idx, open(idx_path, 'w'), indent=2)
"

# Step 3: Post-merge validation (R3-equivalent: all regexes compile, all shards valid)
E2E_R3=$(python3 -c "
import json, os, re
idx = json.load(open(os.path.join('$E2E_PACK', 'index.json')))
errors = 0
total = 0
for eco, info in idx['ecosystems'].items():
    for ec in info['error_classes']:
        shard = json.load(open(os.path.join('$E2E_PACK', eco, ec + '.json')))
        for rec in shard['records']:
            total += 1
            try:
                re.compile(rec['stderr_pattern'])
            except: errors += 1
            if not rec.get('avoidance_hints'): errors += 1
print(f'{errors},{total}')
")
E2E_R3_ERRORS=$(echo "$E2E_R3" | cut -d, -f1)

# Step 4: Second user — isolated POLARIS_HOME, empty local store, consumes merged pack.
# The contributed pattern's stderr_pattern should match new stderr text.
USER_B_HOME=$(mktemp -d)
mkdir -p "$USER_B_HOME/experience"
echo '{"schema_version": 2, "records": []}' > "$USER_B_HOME/experience/failure-records.json"

E2E_HIT=$(python3 -c "
import sys, json
sys.path.insert(0, '$SCRIPTS')
import polaris_failure_records as pfr
from pathlib import Path

# Simulate User B: empty local store, using the merged pack directory
pfr._index_cache = None
user_b_store = json.load(open('$USER_B_HOME/experience/failure-records.json'))

# User B encounters an error that matches User A's contributed pattern
result = pfr.query_sharded(
    user_b_store,
    packs_dir=Path('$E2E_PACK'),
    matching_key='user-b-fresh-session',
    ecosystem='python',
    error_class='missing_dependency',
    stderr_text='ModuleNotFoundError: No module named custom_lib in /app/main.py'
)

hit = bool(result.get('avoidance_hints'))
source = 'unknown'
if hit:
    # Verify the hint is from the contributed record (not prebuilt)
    for h in result['avoidance_hints']:
        if h.get('_source') == 'contributed':
            source = 'contributed'
            break
        elif h.get('_source') == 'prebuilt':
            source = 'prebuilt'
            break
print(f'hit={hit},source={source}')
")

# All 4 steps must pass, AND the hit must come from contributed source
E2E_ALL_OK="no"
E2E_HIT_OK=$(echo "$E2E_HIT" | grep -c "hit=True" || true)
E2E_SRC_OK=$(echo "$E2E_HIT" | grep -c "source=contributed" || true)
if [ "$E2E_VALID_OK" = "1" ] && [ "$E2E_R3_ERRORS" = "0" ] && [ "$E2E_HIT_OK" = "1" ] && [ "$E2E_SRC_OK" = "1" ]; then
    E2E_ALL_OK="yes"
fi
assert_eq "$E2E_ALL_OK" "yes" "3D-G8: E2E contribute→validate→merge→R3→user-B-hits-contributed (valid=$E2E_VALID_OK, r3_err=$E2E_R3_ERRORS, hit=$E2E_HIT)"

rm -rf "$E2E_PACK" "$USER_B_HOME"
rm -f "$OUTFILE"

echo "=== 3D Results: $PASS/$TOTAL passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
