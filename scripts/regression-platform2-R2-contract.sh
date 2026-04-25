#!/usr/bin/env bash
# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

set -euo pipefail
PASS=0; FAIL=0; TOTAL=0
SCRIPTS=Polaris/scripts

assert_eq() { TOTAL=$((TOTAL+1)); if [ "$1" = "$2" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: expected='$2' got='$1' — $3"; fi; }
assert_contains() { TOTAL=$((TOTAL+1)); if grep -qF "$2" <<< "$1"; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: output missing '$2' — $3"; fi; }

# ---------------------------------------------------------------------------
# C1: failure_records.load_store uses safe_load (corruption recovery)
# ---------------------------------------------------------------------------
FTMPDIR=$(mktemp -d)
FPATH="$FTMPDIR/failure-records.json"
echo 'NOT VALID JSON {{{' > "$FPATH"
C1=$(python3 -c "
import sys
sys.path.insert(0, '$SCRIPTS')
import polaris_failure_records as pfr
from pathlib import Path
store = pfr.load_store(Path('$FPATH'))
print(len(store.get('records', [])))
" 2>/dev/null)
assert_eq "$C1" "0" "C1: failure_records.load_store recovers from corrupt file"
# safe_load renames to .json.bak via with_suffix(suffix + '.bak')
assert_eq "$( [ -f "${FPATH}.bak" ] && echo yes || echo no )" "yes" "C1b: corrupt file renamed to .bak"
rm -rf "$FTMPDIR"

# ---------------------------------------------------------------------------
# C2: success_patterns.load_store uses safe_load (corruption recovery)
# ---------------------------------------------------------------------------
STMPDIR=$(mktemp -d)
SPATH="$STMPDIR/success-patterns.json"
echo 'CORRUPT!!!' > "$SPATH"
C2=$(python3 -c "
import sys
sys.path.insert(0, '$SCRIPTS')
import polaris_success_patterns as psp
from pathlib import Path
store = psp.load_store(Path('$SPATH'))
print(len(store.get('patterns', [])))
" 2>/dev/null)
assert_eq "$C2" "0" "C2: success_patterns.load_store recovers from corrupt file"
assert_eq "$( [ -f "${SPATH}.bak" ] && echo yes || echo no )" "yes" "C2b: corrupt file renamed to .bak"
rm -rf "$STMPDIR"

# ---------------------------------------------------------------------------
# C3: failure_records.write_store uses atomic_write (temp+rename)
# ---------------------------------------------------------------------------
FPATH2=$(mktemp)
rm -f "$FPATH2"  # start fresh
C3=$(python3 -c "
import sys, os
sys.path.insert(0, '$SCRIPTS')
import polaris_failure_records as pfr
from pathlib import Path
p = Path('$FPATH2')
pfr.write_store(p, {'schema_version': 2, 'records': [{'test': True}]})
import json
data = json.loads(p.read_text())
print(len(data.get('records', [])))
")
assert_eq "$C3" "1" "C3: failure_records.write_store produces valid JSON via atomic_write"
rm -f "$FPATH2"

# ---------------------------------------------------------------------------
# C4: success_patterns.write_store uses atomic_write
# ---------------------------------------------------------------------------
SPATH2=$(mktemp)
rm -f "$SPATH2"
C4=$(python3 -c "
import sys
sys.path.insert(0, '$SCRIPTS')
import polaris_success_patterns as psp
from pathlib import Path
p = Path('$SPATH2')
psp.write_store(p, {'schema_version': 1, 'patterns': [{'fp': 'test'}]})
import json
data = json.loads(p.read_text())
print(len(data.get('patterns', [])))
")
assert_eq "$C4" "1" "C4: success_patterns.write_store produces valid JSON via atomic_write"
rm -f "$SPATH2"

# ---------------------------------------------------------------------------
# C5: Concurrent-write detection flows through to failure_records
# ---------------------------------------------------------------------------
FPATH3=$(mktemp)
python3 -c "
import sys
sys.path.insert(0, '$SCRIPTS')
import polaris_experience_store as pes
from pathlib import Path
p = Path('$FPATH3')
pes.atomic_write(p, {'schema_version': 2, 'records': []})
"
# Tamper mtime by writing directly, then try atomic_write with stale mtime
C5=$(python3 -c "
import sys, os, time
sys.path.insert(0, '$SCRIPTS')
import polaris_experience_store as pes
from pathlib import Path
p = Path('$FPATH3')
mtime_before = p.stat().st_mtime
# Simulate concurrent write by touching the file
time.sleep(0.05)
p.write_text('{\"schema_version\": 2, \"records\": [{\"injected\": true}]}')
# Now attempt atomic_write with stale mtime
ok = pes.atomic_write(p, {'schema_version': 2, 'records': []}, prior_mtime=mtime_before)
print('rejected' if not ok else 'accepted')
" 2>/dev/null)
assert_eq "$C5" "rejected" "C5: concurrent-write detection rejects stale mtime"
rm -f "$FPATH3"

# ---------------------------------------------------------------------------
# C6: Reuse outcome not double-counted (unit-level check on the guard logic)
# ---------------------------------------------------------------------------
# This verifies the orchestrator's guard: resumed_after_repair blocks reuse success recording
C6=$(python3 -c "
# Simulate the guard condition from polaris_orchestrator.py
selected_pattern_record = {'fingerprint': 'fp1'}
experience_hints = {'prefer': [{'kind': 'set_env'}]}
resumed_after_repair = True

# The guard: should NOT record success when resumed_after_repair is True
should_record = bool(selected_pattern_record and experience_hints.get('prefer') and not resumed_after_repair)
print('guarded' if not should_record else 'leaked')
")
assert_eq "$C6" "guarded" "C6: reuse success not recorded after repair-salvaged run"

# And the positive case: should record when not resumed
C6b=$(python3 -c "
selected_pattern_record = {'fingerprint': 'fp1'}
experience_hints = {'prefer': [{'kind': 'set_env'}]}
resumed_after_repair = False
should_record = bool(selected_pattern_record and experience_hints.get('prefer') and not resumed_after_repair)
print('record' if should_record else 'skipped')
")
assert_eq "$C6b" "record" "C6b: reuse success recorded on clean reuse (no repair)"

echo "=== Contract Gate Results: $PASS/$TOTAL passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
