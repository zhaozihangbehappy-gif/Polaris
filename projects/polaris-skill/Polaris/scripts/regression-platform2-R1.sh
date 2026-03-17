#!/usr/bin/env bash
set -euo pipefail
PASS=0; FAIL=0; TOTAL=0
SCRIPTS=Polaris/scripts

assert_eq() { TOTAL=$((TOTAL+1)); if [ "$1" = "$2" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: expected='$2' got='$1' — $3"; fi; }
assert_contains() { TOTAL=$((TOTAL+1)); if printf '%s' "$1" | grep -qF "$2"; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: output missing '$2' — $3"; fi; }
assert_file_exists() { TOTAL=$((TOTAL+1)); if [ -f "$1" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: file not found '$1' — $2"; fi; }

# Use isolated POLARIS_HOME for all tests (don't touch user's real ~/.polaris)
export POLARIS_HOME=$(mktemp -d)
cleanup() { rm -rf "$POLARIS_HOME"; }
trap cleanup EXIT

# --- Test 1: 第一次失败 → 关终端 → 新 session 命中上次记录 ---
RTDIR1=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "false" --runtime-dir "$RTDIR1" 2>&1 || true
# Verify global library was written
assert_file_exists "$POLARIS_HOME/experience/failure-records.json" "R1-1: global failure store created"
GLOBAL_COUNT=$(python3 -c "
import json
try:
    r=json.load(open('$POLARIS_HOME/experience/failure-records.json'))['records']
    print(len([x for x in r if x.get('source') != 'prebuilt']))
except: print(0)
")
assert_eq "$((GLOBAL_COUNT > 0 ? 1 : 0))" "1" "R1-1: global store has failure record"

# New session (different runtime-dir) should pick up global experience
RTDIR2=$(mktemp -d)
OUT2=$(python3 "$SCRIPTS/polaris_cli.py" run "false" --runtime-dir "$RTDIR2" 2>&1) || true
# Check that experience hints were loaded from global
HINTS=$(python3 -c "
import json
try:
    state = json.load(open('$RTDIR2/execution-state.json'))
    hints_raw = state.get('artifacts', {}).get('experience_hints')
    if isinstance(hints_raw, str):
        hints = json.loads(hints_raw)
    else:
        hints = hints_raw or {}
    print(len(hints.get('avoid', [])))
except: print(0)
")
assert_eq "$((HINTS > 0 ? 1 : 0))" "1" "R1-1: new session gets experience from global library"
rm -rf "$RTDIR1" "$RTDIR2"

# --- Test 2: POLARIS_HOME 覆盖 ---
CUSTOM_HOME=$(mktemp -d)
RTDIR=$(mktemp -d)
POLARIS_HOME="$CUSTOM_HOME" python3 "$SCRIPTS/polaris_cli.py" run "false" --runtime-dir "$RTDIR" 2>&1 || true
assert_file_exists "$CUSTOM_HOME/experience/failure-records.json" "R1-2: custom POLARIS_HOME used"
rm -rf "$CUSTOM_HOME" "$RTDIR"

# --- Test 3: 全局库损坏 → 降级运行 → 不崩溃 ---
rm -rf "$POLARIS_HOME/experience"
mkdir -p "$POLARIS_HOME/experience"
echo "CORRUPT JSON {{{" > "$POLARIS_HOME/experience/failure-records.json"
RTDIR=$(mktemp -d)
T3_OUTFILE=$(mktemp)
python3 "$SCRIPTS/polaris_cli.py" run "echo recovery-test" --runtime-dir "$RTDIR" >"$T3_OUTFILE" 2>&1 || true
# Check warning directly in file (avoids bash variable size limits)
TOTAL=$((TOTAL+1)); if grep -qF "warning" "$T3_OUTFILE"; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: output missing 'warning' — R1-3: corrupt global triggers warning"; fi
rm -f "$T3_OUTFILE"
# Execution should still complete
STATUS=$(python3 -c "
import json
try: print(json.load(open('$RTDIR/execution-state.json'))['status'])
except: print('error')
")
assert_eq "$STATUS" "completed" "R1-3: execution completes despite corrupt global"
# Corrupt file should be backed up
assert_file_exists "$POLARIS_HOME/experience/failure-records.json.bak" "R1-3: corrupt file backed up"
rm -rf "$RTDIR"
# Clean up for subsequent tests
rm -f "$POLARIS_HOME/experience/failure-records.json.bak"

# --- Test 4: 传 --runtime-dir 时全局库仍被写入（双写）---
RTDIR=$(mktemp -d)
# Remove any prior global records
rm -f "$POLARIS_HOME/experience/failure-records.json"
python3 "$SCRIPTS/polaris_cli.py" run "false" --runtime-dir "$RTDIR" 2>&1 || true
# Both should have records
RT_COUNT=$(python3 -c "
import json
try:
    r=json.load(open('$RTDIR/failure-records.json'))['records']
    print(len([x for x in r if x.get('source') != 'prebuilt']))
except: print(0)
")
GL_COUNT=$(python3 -c "
import json
try:
    r=json.load(open('$POLARIS_HOME/experience/failure-records.json'))['records']
    print(len([x for x in r if x.get('source') != 'prebuilt']))
except: print(0)
")
assert_eq "$((RT_COUNT > 0 ? 1 : 0))" "1" "R1-4: runtime-dir has failure record"
assert_eq "$((GL_COUNT > 0 ? 1 : 0))" "1" "R1-4: global library also has failure record (dual-write)"
rm -rf "$RTDIR"

# --- Test 5: 不传 --runtime-dir 时全局库被写入 ---
rm -f "$POLARIS_HOME/experience/failure-records.json"
python3 "$SCRIPTS/polaris_cli.py" run "false" 2>&1 || true
GL_COUNT=$(python3 -c "
import json
try:
    r=json.load(open('$POLARIS_HOME/experience/failure-records.json'))['records']
    print(len([x for x in r if x.get('source') != 'prebuilt']))
except: print(0)
")
assert_eq "$((GL_COUNT > 0 ? 1 : 0))" "1" "R1-5: no --runtime-dir still writes to global"

# --- Test 6: 同 matching_key 新 session 命中来自全局库 ---
# First: run a specific command that fails
rm -f "$POLARIS_HOME/experience/failure-records.json"
RTDIR_A=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "python3 -c 'import nonexistent_xyz'" --runtime-dir "$RTDIR_A" 2>&1 || true
# Get the matching_key
MK=$(python3 -c "
import json
state = json.load(open('$RTDIR_A/execution-state.json'))
fp_raw = state.get('artifacts', {}).get('task_fingerprint', '{}')
if isinstance(fp_raw, str):
    import json as j
    fp = j.loads(fp_raw)
else:
    fp = fp_raw
print(fp.get('matching_key', ''))
")
# Second: new runtime-dir, same command → should hit global experience
RTDIR_B=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "python3 -c 'import nonexistent_xyz'" --runtime-dir "$RTDIR_B" 2>&1 || true
# Check experience_hints come from global (the record's matching_key matches)
HINTS_B=$(python3 -c "
import json
state = json.load(open('$RTDIR_B/execution-state.json'))
hints_raw = state.get('artifacts', {}).get('experience_hints')
if isinstance(hints_raw, str):
    hints = json.loads(hints_raw)
else:
    hints = hints_raw or {}
avoid = hints.get('avoid', [])
print(len(avoid))
")
assert_eq "$((HINTS_B > 0 ? 1 : 0))" "1" "R1-6: new session hits global library by matching_key"
rm -rf "$RTDIR_A" "$RTDIR_B"

# --- Test 7: stderr 经验摘要显示 global library 来源 ---
rm -f "$POLARIS_HOME/experience/failure-records.json"
RTDIR_C=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "false" --runtime-dir "$RTDIR_C" 2>&1 || true
RTDIR_D=$(mktemp -d)
OUT_D=$(python3 "$SCRIPTS/polaris_cli.py" run "false" --runtime-dir "$RTDIR_D" 2>&1) || true
assert_contains "$OUT_D" "global library" "R1-7: stderr mentions global library source"
rm -rf "$RTDIR_C" "$RTDIR_D"

# --- Test 8: 成功命令也同步到全局库 ---
rm -f "$POLARIS_HOME/experience/success-patterns.json"
RTDIR=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "echo global-success-test" --runtime-dir "$RTDIR" 2>&1 || true
GL_PAT=$(python3 -c "
import json
try:
    p=json.load(open('$POLARIS_HOME/experience/success-patterns.json'))['patterns']
    print(len(p))
except: print(0)
")
assert_eq "$((GL_PAT > 0 ? 1 : 0))" "1" "R1-8: success patterns synced to global"
rm -rf "$RTDIR"

echo "=== R1 Results: $PASS/$TOTAL passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
