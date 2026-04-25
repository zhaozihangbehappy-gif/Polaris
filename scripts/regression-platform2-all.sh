#!/usr/bin/env bash
# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

set -euo pipefail
cd "$(dirname "$0")/../.."

echo "=== Platform 2 Full Regression ==="
echo ""

FAILED=0
for phase in A1 A2 A3 B1 B2 C1 C2 D1; do
    script="Polaris/scripts/regression-platform2-${phase}.sh"
    echo "--- Running $phase ---"
    if bash "$script"; then
        echo ""
    else
        echo "!!! $phase FAILED !!!"
        echo ""
        FAILED=$((FAILED+1))
    fi
done

echo "=== Platform 2 Summary ==="
if [ "$FAILED" -eq 0 ]; then
    echo "ALL PHASES PASSED"
else
    echo "$FAILED PHASE(S) FAILED"
    exit 1
fi
