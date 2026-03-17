#!/usr/bin/env bash
set -euo pipefail
PASS=0; FAIL=0; TOTAL=0
SCRIPTS=Polaris/scripts

assert_eq() { TOTAL=$((TOTAL+1)); if [ "$1" = "$2" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: expected='$2' got='$1' — $3"; fi; }
assert_contains() { TOTAL=$((TOTAL+1)); if grep -qF "$2" <<< "$1"; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: output missing '$2' — $3"; fi; }
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

# --- R2-7: Platform 3A — avoid hints only in failure path, prefer hints on success path ---
# With 3A, avoid hints are NOT loaded pre-execution (zero overhead success path).
# This test verifies prefer hints work correctly on the success path.
RTDIR=$(mktemp -d)
rm -rf "$POLARIS_HOME/experience"
SHARED_CWD7=$(mktemp -d)
# First run: succeed → capture prefer hints
python3 "$SCRIPTS/polaris_cli.py" run "echo r2-7-test" --profile standard --cwd "$SHARED_CWD7" --runtime-dir "$RTDIR" 2>&1 || true
# Second run: prefer hints injected, avoid empty (3A contract)
RTDIR2=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "echo r2-7-test" --profile standard --cwd "$SHARED_CWD7" --runtime-dir "$RTDIR2" 2>&1 || true
COEXIST=$(python3 -c "
import json
try:
    state = json.load(open('$RTDIR2/execution-state.json'))
    hints_raw = state.get('artifacts', {}).get('experience_hints')
    if isinstance(hints_raw, str):
        hints = json.loads(hints_raw)
    else:
        hints = hints_raw or {}
    avoid = hints.get('avoid', [])
    prefer = hints.get('prefer', [])
    # 3A: prefer hints present, avoid empty on success path
    if len(prefer) > 0 and len(avoid) == 0:
        print('ok')
    else:
        print(f'prefer={len(prefer)},avoid={len(avoid)}')
except Exception as e:
    print(f'error:{e}')
")
assert_eq "$COEXIST" "ok" "R2-7: 3A success path has prefer hints, no avoid hints"
rm -rf "$RTDIR" "$RTDIR2" "$SHARED_CWD7"

# --- R2-8: stderr shows experience hit on reuse ---
rm -rf "$POLARIS_HOME/experience"
SHARED_CWD8=$(mktemp -d)
RTDIR1=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "echo r2-stderr-test" --profile standard --cwd "$SHARED_CWD8" --runtime-dir "$RTDIR1" 2>&1 || true
RTDIR2=$(mktemp -d)
R28_OUTFILE=$(mktemp)
python3 "$SCRIPTS/polaris_cli.py" run "echo r2-stderr-test" --profile standard --cwd "$SHARED_CWD8" --runtime-dir "$RTDIR2" >"$R28_OUTFILE" 2>&1 || true
# When prefer hints are applied, message is "succeeded on first try (experience hit: ...)"
# When prefer hints exist but not applied, message is "reusing verified strategy"
TOTAL=$((TOTAL+1)); if grep -qE "(succeeded on first try|reusing verified strategy)" "$R28_OUTFILE"; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: output missing experience reuse message — R2-8: stderr shows reuse/experience hit"; fi
TOTAL=$((TOTAL+1)); if grep -qE "(experience hit|confidence)" "$R28_OUTFILE"; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: output missing 'experience hit' or 'confidence' — R2-8: stderr shows experience detail"; fi
rm -f "$R28_OUTFILE"
rm -rf "$RTDIR1" "$RTDIR2" "$SHARED_CWD8"

echo "=== R2 Results: $PASS/$TOTAL passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
