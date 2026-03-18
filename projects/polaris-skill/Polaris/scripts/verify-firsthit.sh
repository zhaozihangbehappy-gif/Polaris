#!/usr/bin/env bash
# verify-firsthit.sh — Measure first-hit recall on fixture sets
# Usage: bash verify-firsthit.sh [dev|holdout|both]
# Default: both (prints dev for reference, holdout for release judgment)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
POLARIS_DIR="$(dirname "$SCRIPT_DIR")"
PACKS_DIR="$POLARIS_DIR/experience-packs"
FIXTURES_DIR="$PACKS_DIR/fixtures"
MODE="${1:-both}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# P0 ecosystems (kill gate)
P0_ECOSYSTEMS="python node docker"

total_fixtures=0
total_hits=0
eco_results=""
any_p0_fail=0

run_set() {
    local set_name="$1"  # dev or holdout
    local set_total=0
    local set_hits=0
    local set_eco_results=""
    local set_p0_fail=0

    echo ""
    echo "========================================="
    echo "  First-Hit Verification: $set_name set"
    echo "========================================="
    echo ""

    for eco_dir in "$FIXTURES_DIR"/*/; do
        eco=$(basename "$eco_dir")
        [ "$eco" = "dev" ] || [ "$eco" = "holdout" ] && continue
        set_dir="$eco_dir/$set_name"
        [ -d "$set_dir" ] || continue

        eco_fixtures=0
        eco_hits=0

        for fixture_file in "$set_dir"/*.json; do
            [ -f "$fixture_file" ] || continue
            eco_fixtures=$((eco_fixtures + 1))

            # Extract stderr from fixture
            stderr_text=$(python3 -c "import json,sys; print(json.load(open('$fixture_file'))['stderr'])" 2>/dev/null || echo "")
            expected_class=$(python3 -c "import json,sys; print(json.load(open('$fixture_file'))['error_class'])" 2>/dev/null || echo "")

            if [ -z "$stderr_text" ]; then
                continue
            fi

            # Try to match against pack patterns for this ecosystem
            hit=$(python3 -c "
import json, os, re, sys

stderr = '''$stderr_text'''
eco = '$eco'
packs_dir = '$PACKS_DIR'
eco_dir = os.path.join(packs_dir, eco)

if not os.path.isdir(eco_dir):
    print('miss')
    sys.exit(0)

for fname in os.listdir(eco_dir):
    if not fname.endswith('.json'):
        continue
    fpath = os.path.join(eco_dir, fname)
    try:
        pack = json.load(open(fpath))
    except:
        continue
    for rec in pack.get('records', []):
        pattern = rec.get('stderr_pattern', '')
        try:
            if re.search(pattern, stderr, re.MULTILINE | re.DOTALL):
                # Check hint kind is valid (not rejected by safety)
                hints = rec.get('avoidance_hints', [])
                valid_kinds = {'set_env','rewrite_cwd','set_timeout','append_flags','set_locale','create_dir','retry_with_backoff','install_package'}
                all_valid = all(h.get('kind','') in valid_kinds for h in hints)
                if all_valid and hints:
                    print('hit')
                    sys.exit(0)
        except re.error:
            continue

print('miss')
" 2>/dev/null || echo "miss")

            if [ "$hit" = "hit" ]; then
                eco_hits=$((eco_hits + 1))
            fi
        done

        if [ "$eco_fixtures" -gt 0 ]; then
            recall=$(python3 -c "print(f'{$eco_hits/$eco_fixtures*100:.1f}')")
            is_p0=0
            for p0 in $P0_ECOSYSTEMS; do
                [ "$eco" = "$p0" ] && is_p0=1
            done

            if [ "$eco_hits" -ge 6 ] && [ "$eco_fixtures" -ge 10 ] || \
               ([ "$eco_fixtures" -lt 10 ] && python3 -c "exit(0 if $eco_hits/$eco_fixtures >= 0.6 else 1)"); then
                status="${GREEN}PASS${NC}"
            else
                status="${RED}FAIL${NC}"
                if [ "$is_p0" -eq 1 ] && [ "$set_name" = "holdout" ]; then
                    set_p0_fail=1
                fi
            fi

            printf "  %-12s  %2d / %2d  (%5s%%)  %b" "$eco" "$eco_hits" "$eco_fixtures" "$recall" "$status"
            if [ "$is_p0" -eq 1 ]; then
                printf "  ${YELLOW}[P0 kill gate]${NC}"
            fi
            echo ""

            set_total=$((set_total + eco_fixtures))
            set_hits=$((set_hits + eco_hits))
        fi
    done

    if [ "$set_total" -gt 0 ]; then
        overall=$(python3 -c "print(f'{$set_hits/$set_total*100:.1f}')")
        echo ""
        echo "  Overall: $set_hits / $set_total ($overall%)"
    fi

    if [ "$set_name" = "holdout" ] && [ "$set_p0_fail" -eq 1 ]; then
        echo ""
        echo -e "  ${RED}KILL GATE TRIGGERED: P0 ecosystem holdout recall < 60%. NOT RELEASABLE.${NC}"
        return 1
    fi

    return 0
}

if [ "$MODE" = "dev" ] || [ "$MODE" = "both" ]; then
    run_set "dev" || true
fi

if [ "$MODE" = "holdout" ] || [ "$MODE" = "both" ]; then
    run_set "holdout"
    exit_code=$?
    if [ $exit_code -ne 0 ]; then
        exit 1
    fi
fi

echo ""
echo "Done."
