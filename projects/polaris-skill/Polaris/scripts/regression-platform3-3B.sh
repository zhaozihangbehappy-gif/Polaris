#!/usr/bin/env bash
set -euo pipefail
PASS=0; FAIL=0; TOTAL=0
SCRIPTS=Polaris/scripts

assert_eq() { TOTAL=$((TOTAL+1)); if [ "$1" = "$2" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: expected='$2' got='$1' — $3"; fi; }

# --- 3B-G1: HINT_KINDS contains 8 kinds ---
G1=$(python3 -c "
import sys
sys.path.insert(0, '$SCRIPTS')
import polaris_failure_records as pfr
print(len(pfr.HINT_KINDS))
")
assert_eq "$G1" "8" "3B-G1: HINT_KINDS contains 8 kinds"

# --- 3B-G2: adapter has apply logic for every kind ---
G2=$(python3 -c "
import sys
sys.path.insert(0, '$SCRIPTS')
import polaris_adapter_shell as pas
print(len(pas.SUPPORTED_HINT_KINDS))
")
assert_eq "$G2" "8" "3B-G2: adapter SUPPORTED_HINT_KINDS = 8"

# --- 3B-G3: install_package rejected under standard profile ---
G3=$(python3 -c "
import sys
sys.path.insert(0, '$SCRIPTS')
import polaris_adapter_shell as pas
cmd, cwd, timeout, applied, rejected = pas.apply_hints(
    'pip install foo', '.', 60000,
    {'prefer': [], 'avoid': [{'kind': 'install_package', 'package': 'foo', 'confidence_discount': 0.7}]}
)
install_rejected = any(r['hint']['kind'] == 'install_package' for r in rejected)
install_applied = any(a['kind'] == 'install_package' for a in applied)
print(f'rejected={install_rejected},applied={install_applied}')
")
assert_eq "$G3" "rejected=True,applied=False" "3B-G3: install_package rejected by default"

# --- 3B-G4: R4a safe set = 7 kinds, no install_package ---
G4=$(python3 -c "
import sys, ast
# Read the SAFE_AUTOFIX_KINDS from orchestrator source
with open('$SCRIPTS/polaris_orchestrator.py') as f:
    src = f.read()
# Find the set literal
import re
m = re.search(r'_SAFE_AUTOFIX_KINDS = (\{[^}]+\})', src)
if m:
    kinds = ast.literal_eval(m.group(1))
    has_install = 'install_package' in kinds
    print(f'{len(kinds)},install={has_install}')
else:
    print('not_found')
")
assert_eq "$G4" "7,install=False" "3B-G4: R4a safe set = 7 kinds, no install_package"

# --- 3B-G5: non-allowlist flags rejected ---
G5=$(python3 -c "
import sys
sys.path.insert(0, '$SCRIPTS')
import polaris_adapter_shell as pas
cmd, cwd, timeout, applied, rejected = pas.apply_hints(
    'npm install', '.', 60000,
    {'prefer': [], 'avoid': [{'kind': 'append_flags', 'flags': ['--yes', '--rm-rf-slash', '-q'], 'confidence_discount': 0.7}]}
)
# --yes and -q are in allowlist, --rm-rf-slash is not
safe_applied = any(a['kind'] == 'append_flags' and '--yes' in a.get('flags', []) for a in applied)
unsafe_rejected = any('--rm-rf-slash' in str(r) for r in rejected)
print(f'safe={safe_applied},unsafe_rejected={unsafe_rejected}')
")
assert_eq "$G5" "safe=True,unsafe_rejected=True" "3B-G5: non-allowlist flag rejected, allowlist flag applied"

# --- 3B-G6: Platform 2 R4a still passes ---
R4A_RESULT=$(bash Polaris/scripts/regression-platform2-R4a.sh 2>&1 | tail -1)
R4A_OK=$(echo "$R4A_RESULT" | grep -c "0 failed" || true)
assert_eq "$R4A_OK" "1" "3B-G6: Platform 2 R4a regression passes"

# --- 3B-G7: create_dir scoping — absolute, escape, deep paths rejected ---
G7=$(python3 -c "
import sys, tempfile, os
sys.path.insert(0, '$SCRIPTS')
import polaris_adapter_shell as pas

cwd = tempfile.mkdtemp()
results = []

# absolute path → rejected
_, _, _, app, rej = pas.apply_hints('ls', cwd, 60000,
    {'prefer': [], 'avoid': [{'kind': 'create_dir', 'target': '/etc/evil', 'confidence_discount': 0.7}]})
results.append('abs_reject' if any(r['hint']['kind'] == 'create_dir' for r in rej) else 'abs_pass')

# escape cwd → rejected
_, _, _, app, rej = pas.apply_hints('ls', cwd, 60000,
    {'prefer': [], 'avoid': [{'kind': 'create_dir', 'target': '../../../tmp/evil', 'confidence_discount': 0.7}]})
results.append('escape_reject' if any(r['hint']['kind'] == 'create_dir' for r in rej) else 'escape_pass')

# too deep → rejected
_, _, _, app, rej = pas.apply_hints('ls', cwd, 60000,
    {'prefer': [], 'avoid': [{'kind': 'create_dir', 'target': 'a/b/c/d', 'confidence_discount': 0.7}]})
results.append('deep_reject' if any(r['hint']['kind'] == 'create_dir' for r in rej) else 'deep_pass')

# sibling prefix attack: ../cwdname2 resolves to a path that
# startswith(cwd) but is actually a sibling directory → must be rejected
sibling_name = os.path.basename(cwd) + '2'
sibling_target = '../' + sibling_name
_, _, _, app, rej = pas.apply_hints('ls', cwd, 60000,
    {'prefer': [], 'avoid': [{'kind': 'create_dir', 'target': sibling_target, 'confidence_discount': 0.7}]})
sibling_was_rejected = any(r['hint']['kind'] == 'create_dir' for r in rej)
sibling_exists = os.path.isdir(os.path.join(os.path.dirname(cwd), sibling_name))
results.append('sibling_reject' if sibling_was_rejected and not sibling_exists else 'sibling_ESCAPE')

# valid path → applied
_, _, _, app, rej = pas.apply_hints('ls', cwd, 60000,
    {'prefer': [], 'avoid': [{'kind': 'create_dir', 'target': 'sub/dir', 'confidence_discount': 0.7}]})
results.append('valid_apply' if any(a['kind'] == 'create_dir' for a in app) else 'valid_fail')
created = os.path.isdir(os.path.join(cwd, 'sub', 'dir'))
results.append('exists' if created else 'not_exists')

import shutil
shutil.rmtree(cwd)
# Clean up sibling if it was created (should not exist after fix)
sibling_full = os.path.join(os.path.dirname(cwd), sibling_name)
if os.path.exists(sibling_full):
    shutil.rmtree(sibling_full)
print(','.join(results))
")
assert_eq "$G7" "abs_reject,escape_reject,deep_reject,sibling_reject,valid_apply,exists" "3B-G7: create_dir scoping enforced (includes sibling prefix attack)"

echo "=== 3B Results: $PASS/$TOTAL passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
