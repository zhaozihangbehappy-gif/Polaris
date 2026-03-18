#!/usr/bin/env bash
# regression-all.sh — Run ALL Platform 2 + Platform 3 gate regressions.
# Reports per-phase results and a final total gate count.
set -euo pipefail
cd "$(dirname "$0")/../.."

TOTAL_PASS=0
TOTAL_FAIL=0
PHASE_FAIL=0

extract_counts() {
    # Parse "N/M passed, F failed" from the last line of phase output
    local output="$1"
    local results_line
    results_line=$(echo "$output" | grep -oP '\d+/\d+ passed, \d+ failed' | tail -1 || true)
    if [ -n "$results_line" ]; then
        local p f
        p=$(echo "$results_line" | grep -oP '^\d+')
        f=$(echo "$results_line" | grep -oP '\d+ failed' | grep -oP '^\d+')
        TOTAL_PASS=$((TOTAL_PASS + p))
        TOTAL_FAIL=$((TOTAL_FAIL + f))
    fi
}

echo "============================================="
echo "  Full Regression: Platform 2 + Platform 3"
echo "============================================="
echo ""

# --- Platform 2 phases ---
echo ">>> Platform 2 <<<"
for phase in A1 A2 A3 B1 B2 C1 C2 D1; do
    script="Polaris/scripts/regression-platform2-${phase}.sh"
    if [ ! -f "$script" ]; then
        echo "  SKIP: $script not found"
        continue
    fi
    echo -n "  P2-$phase: "
    output=$(bash "$script" 2>&1) && status=0 || status=$?
    result_line=$(echo "$output" | grep "Results:" | tail -1 || true)
    if [ $status -eq 0 ]; then
        echo "PASS  $result_line"
    else
        echo "FAIL  $result_line"
        PHASE_FAIL=$((PHASE_FAIL + 1))
    fi
    extract_counts "$output"
done

# --- Platform 2 R-series ---
for phase in R0 R1 R2 R2-contract R2-merge R3 R4a R5; do
    script="Polaris/scripts/regression-platform2-${phase}.sh"
    if [ ! -f "$script" ]; then
        echo "  SKIP: $script not found"
        continue
    fi
    echo -n "  P2-$phase: "
    output=$(bash "$script" 2>&1) && status=0 || status=$?
    result_line=$(echo "$output" | grep -E "Results:|passed" | tail -1 || true)
    if [ $status -eq 0 ]; then
        echo "PASS  $result_line"
    else
        echo "FAIL  $result_line"
        PHASE_FAIL=$((PHASE_FAIL + 1))
    fi
    extract_counts "$output"
done

echo ""

# --- Platform 3 phases ---
echo ">>> Platform 3 <<<"
for phase in 3A 3B 3C 3D 3E; do
    script="Polaris/scripts/regression-platform3-${phase}.sh"
    if [ ! -f "$script" ]; then
        echo "  SKIP: $script not found"
        continue
    fi
    echo -n "  P3-$phase: "
    output=$(bash "$script" 2>&1) && status=0 || status=$?
    result_line=$(echo "$output" | grep "Results:" | tail -1 || true)
    if [ $status -eq 0 ]; then
        echo "PASS  $result_line"
    else
        echo "FAIL  $result_line"
        PHASE_FAIL=$((PHASE_FAIL + 1))
        # Show failure details
        echo "$output" | grep "^FAIL" | head -5 | sed 's/^/    /'
    fi
    extract_counts "$output"
done

echo ""
echo "============================================="
echo "  TOTAL: $TOTAL_PASS passed, $TOTAL_FAIL failed"
echo "  Phases failed: $PHASE_FAIL"
echo "============================================="

if [ "$PHASE_FAIL" -gt 0 ]; then
    exit 1
fi
