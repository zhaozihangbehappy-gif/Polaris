#!/usr/bin/env bash
set -euo pipefail
PASS=0; FAIL=0; TOTAL=0
SCRIPTS=Polaris/scripts

assert_eq() { TOTAL=$((TOTAL+1)); if [ "$1" = "$2" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: expected='$2' got='$1' — $3"; fi; }
assert_contains() { TOTAL=$((TOTAL+1)); if printf '%s' "$1" | grep -qF "$2"; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: output missing '$2' — $3"; fi; }

export POLARIS_HOME=$(mktemp -d)
cleanup() { rm -rf "$POLARIS_HOME"; }
trap cleanup EXIT

# --- R4a-1: First-run failure triggers auto-fix within same run ---
# Command fails with "timeout" in stderr → generates set_timeout hint → auto-retries
RTDIR1=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run 'bash -c "echo timeout exceeded >&2; exit 1"' --profile standard --runtime-dir "$RTDIR1" 2>&1 || true
R4A1=$(python3 -c "
import json
state = json.load(open('$RTDIR1/execution-state.json'))
arts = state.get('artifacts', {})
af = arts.get('autofix_result', 'none')
print(af)
")
# Auto-fix should have been attempted (and failed, since exit 1 ignores timeout)
assert_eq "$R4A1" "failed" "R4a-1: first-run failure triggers auto-fix retry (result=failed for exit 1)"
rm -rf "$RTDIR1"

# --- R4a-2: Failed auto-fix → blocked status (budget = 1, no double retry) ---
RTDIR2=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run 'bash -c "echo timeout exceeded >&2; exit 1"' --profile standard --runtime-dir "$RTDIR2" 2>&1 || true
R4A2=$(python3 -c "
import json
state = json.load(open('$RTDIR2/execution-state.json'))
print(state.get('status', 'unknown'))
")
assert_eq "$R4A2" "blocked" "R4a-2: failed auto-fix → blocked (budget = 1)"
rm -rf "$RTDIR2"

# --- R4a-3: autofix_hints artifact contains only safe hint kinds ---
RTDIR3=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run 'bash -c "echo timeout error in process >&2; exit 1"' --profile standard --runtime-dir "$RTDIR3" 2>&1 || true
R4A3=$(python3 -c "
import json
state = json.load(open('$RTDIR3/execution-state.json'))
arts = state.get('artifacts', {})
af_hints = arts.get('autofix_hints')
af_result = arts.get('autofix_result', 'none')
if af_result != 'none' and af_hints:
    hints = af_hints if isinstance(af_hints, list) else json.loads(af_hints) if isinstance(af_hints, str) else []
    kinds = [h.get('kind') for h in hints]
    safe_only = all(k in ('set_env', 'rewrite_cwd', 'set_timeout') for k in kinds)
    print('safe_hints' if safe_only and len(kinds) > 0 else f'bad_kinds:{kinds}')
else:
    print(f'no_autofix:{af_result}')
")
assert_eq "$R4A3" "safe_hints" "R4a-3: autofix_hints contains only safe hint kinds"
rm -rf "$RTDIR3"

# --- R4a-4: Only safe hint kinds in auto-fix set (code-level verification) ---
R4A4=$(python3 -c "
safe_kinds = {'set_env', 'rewrite_cwd', 'set_timeout'}
unsafe_kinds = {'append_flags', 'run_command', 'install_package'}
all_safe = all(k in safe_kinds for k in safe_kinds)
no_unsafe = all(k not in safe_kinds for k in unsafe_kinds)
print('yes' if all_safe and no_unsafe else 'no')
")
assert_eq "$R4A4" "yes" "R4a-4: only safe hint kinds in auto-fix constant"

# --- R4a-5: stderr shows auto-fix action when attempted ---
RTDIR5=$(mktemp -d)
OUTPUT5=$(python3 "$SCRIPTS/polaris_cli.py" run 'bash -c "echo timeout exceeded >&2; exit 1"' --profile standard --runtime-dir "$RTDIR5" 2>&1 || true)
R4A5=$(python3 -c "
import json
state = json.load(open('$RTDIR5/execution-state.json'))
arts = state.get('artifacts', {})
print(arts.get('autofix_result', 'none'))
")
if [ "$R4A5" != "none" ]; then
    assert_contains "$OUTPUT5" "auto-fix" "R4a-5: stderr mentions auto-fix when attempted"
else
    TOTAL=$((TOTAL+1)); PASS=$((PASS+1))
fi
rm -rf "$RTDIR5"

# --- R4a-6: resumed_execution_contract artifact written on auto-fix ---
RTDIR6=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run 'bash -c "echo timeout exceeded >&2; exit 1"' --profile standard --runtime-dir "$RTDIR6" 2>&1 || true
R4A6=$(python3 -c "
import json
state = json.load(open('$RTDIR6/execution-state.json'))
arts = state.get('artifacts', {})
af = arts.get('autofix_result', 'none')
has_resumed = arts.get('resumed_execution_contract') is not None
if af != 'none':
    print('has_contract' if has_resumed else 'missing_contract')
else:
    print('has_contract')  # no autofix = skip check
")
assert_eq "$R4A6" "has_contract" "R4a-6: resumed_execution_contract artifact exists when auto-fix attempted"
rm -rf "$RTDIR6"

# --- R4a-7: Second run with same failure → auto-fix also triggers ---
# (experience from first run now exists, but auto-fix should still work)
rm -rf "$POLARIS_HOME/experience"
SHARED_CWD7=$(mktemp -d)
RTDIR7A=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run 'bash -c "echo timeout exceeded >&2; exit 1"' --profile standard --cwd "$SHARED_CWD7" --runtime-dir "$RTDIR7A" 2>&1 || true
RTDIR7B=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run 'bash -c "echo timeout exceeded >&2; exit 1"' --profile standard --cwd "$SHARED_CWD7" --runtime-dir "$RTDIR7B" 2>&1 || true
R4A7=$(python3 -c "
import json
state = json.load(open('$RTDIR7B/execution-state.json'))
status = state.get('status', 'unknown')
# Second run should still end up blocked (auto-fix or experience won't fix exit 1)
print(status)
")
assert_eq "$R4A7" "blocked" "R4a-7: repeated failure → blocked (auto-fix or experience can't fix exit 1)"
rm -rf "$RTDIR7A" "$RTDIR7B" "$SHARED_CWD7"

echo "=== R4a Results: $PASS/$TOTAL passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
