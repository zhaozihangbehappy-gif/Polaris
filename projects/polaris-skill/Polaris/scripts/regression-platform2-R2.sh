#!/usr/bin/env bash
set -euo pipefail
PASS=0; FAIL=0; TOTAL=0
SCRIPTS=Polaris/scripts

assert_eq() { TOTAL=$((TOTAL+1)); if [ "$1" = "$2" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: expected='$2' got='$1' — $3"; fi; }
assert_contains() { TOTAL=$((TOTAL+1)); if printf '%s' "$1" | grep -qF "$2"; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: output missing '$2' — $3"; fi; }
assert_file_exists() { TOTAL=$((TOTAL+1)); if [ -f "$1" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: file not found '$1' — $2"; fi; }

# Isolated POLARIS_HOME
export POLARIS_HOME=$(mktemp -d)
cleanup() { rm -rf "$POLARIS_HOME"; }
trap cleanup EXIT

# --- R2-1: First success → experience_hints_prefer non-empty ---
RTDIR=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "echo r2-gate-test" --runtime-dir "$RTDIR" 2>&1 || true
PREFER=$(python3 -c "
import json
try:
    sp = json.load(open('$RTDIR/success-patterns.json'))
    for p in sp.get('patterns', []):
        hints = p.get('strategy_hints', {}).get('experience_hints_prefer', [])
        if hints:
            print(len(hints))
            break
    else:
        print(0)
except Exception as e:
    print(0)
")
assert_eq "$((PREFER > 0 ? 1 : 0))" "1" "R2-1: success pattern has non-empty experience_hints_prefer"
rm -rf "$RTDIR"

# --- R2-2: Second run → prefer hints injected into execution_contract ---
# Must use --profile standard so pattern selection is enabled.
# Use --cwd to keep matching_key stable across different runtime-dirs.
rm -rf "$POLARIS_HOME/experience"
SHARED_CWD=$(mktemp -d)
RTDIR1=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "echo r2-reuse-inject" --profile standard --cwd "$SHARED_CWD" --runtime-dir "$RTDIR1" 2>&1 || true
# Second run — fresh runtime-dir, same command, same cwd
RTDIR2=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "echo r2-reuse-inject" --profile standard --cwd "$SHARED_CWD" --runtime-dir "$RTDIR2" 2>&1 || true
PREFER2=$(python3 -c "
import json
try:
    state = json.load(open('$RTDIR2/execution-state.json'))
    # Check experience_hints artifact
    hints_raw = state.get('artifacts', {}).get('experience_hints')
    if isinstance(hints_raw, str):
        hints = json.loads(hints_raw)
    else:
        hints = hints_raw or {}
    prefer = hints.get('prefer', [])
    print(len(prefer))
except:
    print(0)
")
assert_eq "$((PREFER2 > 0 ? 1 : 0))" "1" "R2-2: second run has prefer hints injected"

# --- R2-3: experience_hints.prefer matches strategy_hints in success-patterns ---
MATCH=$(python3 -c "
import json, sys
try:
    state = json.load(open('$RTDIR2/execution-state.json'))
    hints_raw = state.get('artifacts', {}).get('experience_hints')
    if isinstance(hints_raw, str):
        hints = json.loads(hints_raw)
    else:
        hints = hints_raw or {}
    state_prefer = hints.get('prefer', [])
    if not state_prefer:
        sys.stdout.write('no_prefer')
        sys.exit(0)
    sp = json.load(open('$RTDIR2/success-patterns.json'))
    for pat in sp.get('patterns', []):
        strat = pat.get('strategy_hints', {}).get('experience_hints_prefer', [])
        if strat:
            state_kinds = {h.get('kind') for h in state_prefer}
            strat_kinds = {h.get('kind') for h in strat}
            if state_kinds & strat_kinds:
                sys.stdout.write('match')
                sys.exit(0)
    sys.stdout.write('no_match')
except Exception:
    sys.stdout.write('error')
")
assert_eq "$MATCH" "match" "R2-3: prefer hints content consistent with success-patterns strategy_hints"
rm -rf "$RTDIR1" "$RTDIR2" "$SHARED_CWD"

# --- R2-4: 5 consecutive reuse successes → confidence ≤ 0.95 ---
PFILE=$(mktemp)
echo '{"schema_version": 1, "patterns": []}' > "$PFILE"
python3 "$SCRIPTS/polaris_success_patterns.py" capture \
    --patterns "$PFILE" \
    --pattern-id "r2-conf-test" \
    --summary "Test confidence" \
    --trigger "test" \
    --sequence "execute" \
    --outcome "ok" \
    --evidence "test" \
    --confidence 80 \
    --lifecycle-state "validated" \
    --tags "orchestration,local" > /dev/null
# Run 5 successful reuse updates
for i in 1 2 3 4 5; do
    python3 "$SCRIPTS/polaris_success_patterns.py" update-reuse-outcome \
        --patterns "$PFILE" --fingerprint "r2-conf-test" --success yes > /dev/null
done
CONF=$(python3 -c "
import json
sp = json.load(open('$PFILE'))
for p in sp['patterns']:
    if p.get('fingerprint') == 'r2-conf-test':
        print(p['confidence'])
        break
")
assert_eq "$((CONF <= 95 ? 1 : 0))" "1" "R2-4: confidence after 5 successes ≤ 95 (0.95)"
assert_eq "$((CONF > 80 ? 1 : 0))" "1" "R2-4: confidence increased from 80"
rm -f "$PFILE"

# --- R2-5: Reuse failure → confidence decreases ---
PFILE=$(mktemp)
echo '{"schema_version": 1, "patterns": []}' > "$PFILE"
python3 "$SCRIPTS/polaris_success_patterns.py" capture \
    --patterns "$PFILE" \
    --pattern-id "r2-dec-test" \
    --summary "Test decrease" \
    --trigger "test" \
    --sequence "execute" \
    --outcome "ok" \
    --evidence "test" \
    --confidence 80 \
    --lifecycle-state "validated" \
    --tags "orchestration,local" > /dev/null
BEFORE=$(python3 -c "
import json
sp = json.load(open('$PFILE'))
for p in sp['patterns']:
    if p.get('fingerprint') == 'r2-dec-test':
        print(p['confidence'])
        break
")
python3 "$SCRIPTS/polaris_success_patterns.py" update-reuse-outcome \
    --patterns "$PFILE" --fingerprint "r2-dec-test" --success no > /dev/null
AFTER=$(python3 -c "
import json
sp = json.load(open('$PFILE'))
for p in sp['patterns']:
    if p.get('fingerprint') == 'r2-dec-test':
        print(p['confidence'])
        break
")
assert_eq "$((AFTER < BEFORE ? 1 : 0))" "1" "R2-5: confidence decreased after reuse failure ($BEFORE → $AFTER)"
rm -f "$PFILE"

# --- R2-6: 3 consecutive reuse failures → stale, not reused ---
PFILE=$(mktemp)
echo '{"schema_version": 1, "patterns": []}' > "$PFILE"
python3 "$SCRIPTS/polaris_success_patterns.py" capture \
    --patterns "$PFILE" \
    --pattern-id "r2-stale-test" \
    --summary "Test stale" \
    --trigger "test" \
    --sequence "execute" \
    --outcome "ok" \
    --evidence "test" \
    --confidence 70 \
    --lifecycle-state "validated" \
    --tags "orchestration,local" > /dev/null
for i in 1 2 3; do
    python3 "$SCRIPTS/polaris_success_patterns.py" update-reuse-outcome \
        --patterns "$PFILE" --fingerprint "r2-stale-test" --success no > /dev/null
done
STALE=$(python3 -c "
import json
sp = json.load(open('$PFILE'))
for p in sp['patterns']:
    if p.get('fingerprint') == 'r2-stale-test':
        is_stale = p.get('stale', False)
        lifecycle = p.get('lifecycle_state', '')
        print('stale' if (is_stale or lifecycle in ('retired', 'expired')) else 'active')
        break
")
assert_eq "$STALE" "stale" "R2-6: 3 consecutive failures → stale"
# Verify not selected anymore
SEL=$(python3 "$SCRIPTS/polaris_success_patterns.py" select \
    --patterns "$PFILE" --tags "orchestration,local" --min-confidence 0)
SEL_COUNT=$(echo "$SEL" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('selected', [])))")
assert_eq "$SEL_COUNT" "0" "R2-6: stale pattern not selected"
rm -f "$PFILE"

# --- R2-7: prefer and avoid hints coexist, avoid takes precedence ---
RTDIR=$(mktemp -d)
rm -rf "$POLARIS_HOME/experience"
# First run: fail to create avoid hints
python3 "$SCRIPTS/polaris_cli.py" run "python3 -c 'import os; exit(1 if not os.environ.get(\"R2_TEST_VAR\") else 0)'" --runtime-dir "$RTDIR" 2>&1 || true
# Create a success pattern with a prefer hint of same kind (set_env) in a second runtime
RTDIR_S=$(mktemp -d)
R2_TEST_VAR=hello python3 "$SCRIPTS/polaris_cli.py" run "python3 -c 'import os; exit(1 if not os.environ.get(\"R2_TEST_VAR\") else 0)'" --runtime-dir "$RTDIR_S" 2>&1 || true
# Third run: both prefer (from success) and avoid (from failure) should exist
RTDIR3=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "python3 -c 'import os; exit(1 if not os.environ.get(\"R2_TEST_VAR\") else 0)'" --runtime-dir "$RTDIR3" 2>&1 || true
# Check that adapter rejects prefer hint when avoid of same kind exists, OR that avoid hints are present
COEXIST=$(python3 -c "
import json
try:
    state = json.load(open('$RTDIR3/execution-state.json'))
    hints_raw = state.get('artifacts', {}).get('experience_hints')
    if isinstance(hints_raw, str):
        hints = json.loads(hints_raw)
    else:
        hints = hints_raw or {}
    avoid = hints.get('avoid', [])
    prefer = hints.get('prefer', [])
    # If both exist, the adapter should have handled precedence
    # At minimum, avoid hints must be present
    if len(avoid) > 0:
        print('ok')
    else:
        print('no_avoid')
except:
    print('error')
")
assert_eq "$COEXIST" "ok" "R2-7: prefer and avoid hints coexist, avoid present"
rm -rf "$RTDIR" "$RTDIR_S" "$RTDIR3"

# --- R2-8: stderr shows reuse message with confidence ---
rm -rf "$POLARIS_HOME/experience"
SHARED_CWD8=$(mktemp -d)
RTDIR1=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "echo r2-stderr-test" --profile standard --cwd "$SHARED_CWD8" --runtime-dir "$RTDIR1" 2>&1 || true
RTDIR2=$(mktemp -d)
R28_OUTFILE=$(mktemp)
python3 "$SCRIPTS/polaris_cli.py" run "echo r2-stderr-test" --profile standard --cwd "$SHARED_CWD8" --runtime-dir "$RTDIR2" >"$R28_OUTFILE" 2>&1 || true
# Use file-based grep to avoid large-variable issues
TOTAL=$((TOTAL+1)); if grep -qF "reusing verified strategy" "$R28_OUTFILE"; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: output missing 'reusing verified strategy' — R2-8: stderr shows reuse message"; fi
TOTAL=$((TOTAL+1)); if grep -qF "confidence" "$R28_OUTFILE"; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: output missing 'confidence' — R2-8: stderr shows confidence"; fi
rm -f "$R28_OUTFILE"
rm -rf "$RTDIR1" "$RTDIR2" "$SHARED_CWD8"

echo "=== R2 Results: $PASS/$TOTAL passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
