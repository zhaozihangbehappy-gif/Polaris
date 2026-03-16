#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT/.."
PASS=0; FAIL=0; TOTAL=0

assert_eq() { TOTAL=$((TOTAL+1)); if [ "$1" = "$2" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: expected='$2' got='$1' — $3"; fi; }
assert_contains() { TOTAL=$((TOTAL+1)); if echo "$1" | grep -qF "$2"; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: output missing '$2' — $3"; fi; }
assert_file_exists() { TOTAL=$((TOTAL+1)); if [ -f "$1" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: file not found '$1' — $2"; fi; }

# --- Test 1: successful command, full lifecycle ---
RTDIR=$(mktemp -d)
python3 Polaris/scripts/polaris_cli.py run "echo hello-polaris" --runtime-dir "$RTDIR" >/dev/null 2>&1
EXIT=$?
assert_eq "$EXIT" "0" "A1-T1: echo command should exit 0"
assert_file_exists "$RTDIR/execution-state.json" "A1-T1: state file must exist"
STATUS=$(python3 -c "import json; print(json.load(open('$RTDIR/execution-state.json'))['status'])")
assert_eq "$STATUS" "completed" "A1-T1: final status must be completed"
rm -rf "$RTDIR"

# --- Test 2: failing command, blocked status ---
RTDIR=$(mktemp -d)
T2_EXIT=0
python3 Polaris/scripts/polaris_cli.py run "false" --runtime-dir "$RTDIR" >/dev/null 2>&1 || T2_EXIT=$?
assert_eq "$((T2_EXIT != 0 ? 1 : 0))" "1" "A1-T2: false command should exit non-zero"
STATUS=$(python3 -c "import json; print(json.load(open('$RTDIR/execution-state.json'))['status'])")
assert_eq "$STATUS" "blocked" "A1-T2: failed command should result in blocked status"
rm -rf "$RTDIR"

# --- Test 3: standard profile ---
RTDIR=$(mktemp -d)
python3 Polaris/scripts/polaris_cli.py run "echo standard-test" --profile standard --runtime-dir "$RTDIR" >/dev/null 2>&1
PROFILE=$(python3 -c "import json; print(json.load(open('$RTDIR/execution-state.json')).get('execution_profile',''))")
assert_eq "$PROFILE" "standard" "A1-T3: profile must be standard"
rm -rf "$RTDIR"

# --- Test 4: equivalence — CLI vs env-var entry produce consistent state ---
RTDIR_CLI=$(mktemp -d)
RTDIR_ENV=$(mktemp -d)
python3 Polaris/scripts/polaris_cli.py run "echo equiv-test" --runtime-dir "$RTDIR_CLI" --profile micro >/dev/null 2>&1
# Env-var entry via runtime_demo
POLARIS_RUNTIME_DIR="$RTDIR_ENV" \
POLARIS_EXECUTION_PROFILE=micro \
POLARIS_MODE=short \
POLARIS_EXECUTION_KIND=shell_command \
POLARIS_SHELL_COMMAND="echo equiv-test" \
POLARIS_GOAL="echo equiv-test" \
POLARIS_SIMULATE_ERROR="" \
bash Polaris/scripts/polaris_runtime_demo.sh >/dev/null 2>&1
# Compare state (exclude volatile fields)
CLI_STATE=$(python3 -c "
import json
s=json.load(open('$RTDIR_CLI/execution-state.json'))
for k in ['run_id','updated_at']: s.pop(k,None)
rt=s.get('runtime',{})
for k in ['started_at','last_heartbeat_at','completed_at']: rt.pop(k,None)
for k in ['started_at','last_heartbeat_at','completed_at']: s.pop(k,None)
s.get('state_machine',{}).get('history',[]).clear()
s.get('state_machine',{}).get('history_summary',[]).clear()
s.get('attempts',[]).clear()
s.get('checkpoints',[]).clear()
print(json.dumps({k:v for k,v in sorted(s.items()) if k not in ('artifacts','runtime','lessons','success_patterns','references','plan')}, sort_keys=True))
")
ENV_STATE=$(python3 -c "
import json
s=json.load(open('$RTDIR_ENV/execution-state.json'))
for k in ['run_id','updated_at']: s.pop(k,None)
rt=s.get('runtime',{})
for k in ['started_at','last_heartbeat_at','completed_at']: rt.pop(k,None)
for k in ['started_at','last_heartbeat_at','completed_at']: s.pop(k,None)
s.get('state_machine',{}).get('history',[]).clear()
s.get('state_machine',{}).get('history_summary',[]).clear()
s.get('attempts',[]).clear()
s.get('checkpoints',[]).clear()
print(json.dumps({k:v for k,v in sorted(s.items()) if k not in ('artifacts','runtime','lessons','success_patterns','references','plan')}, sort_keys=True))
")
assert_eq "$CLI_STATE" "$ENV_STATE" "A1-T4: CLI and ENV entry must produce equivalent state"
rm -rf "$RTDIR_CLI" "$RTDIR_ENV"

# --- Test 5: no-argument call should print usage and exit non-zero ---
T5_EXIT=0
OUT=$(python3 Polaris/scripts/polaris_cli.py run 2>&1) || T5_EXIT=$?
assert_eq "$((T5_EXIT != 0 ? 1 : 0))" "1" "A1-T5: run without command should fail"
assert_contains "$OUT" "usage" "A1-T5: should print usage hint"

# --- Test 6: runtime-dir auto-creation ---
RTDIR="/tmp/polaris-cli-test-autocreate-$$"
rm -rf "$RTDIR"
python3 Polaris/scripts/polaris_cli.py run "echo auto-create" --runtime-dir "$RTDIR" >/dev/null 2>&1
assert_file_exists "$RTDIR/execution-state.json" "A1-T6: auto-created runtime dir must have state"
rm -rf "$RTDIR"

# --- Test 7: default runtime-dir (hash-based) ---
python3 Polaris/scripts/polaris_cli.py run "echo default-dir-test" >/dev/null 2>&1
HASH=$(python3 -c "import hashlib; print(hashlib.sha256(b'echo default-dir-test').hexdigest()[:12])")
DEFAULT_DIR="/tmp/polaris-$HASH"
assert_file_exists "$DEFAULT_DIR/execution-state.json" "A1-T7: default dir must use hash"
rm -rf "$DEFAULT_DIR"

echo "=== A1 Results: $PASS/$TOTAL passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
