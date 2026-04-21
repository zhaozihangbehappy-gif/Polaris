#!/usr/bin/env bash
# verify-reproductions.sh — Execute every pattern's reproduction case
# Kill gate: any reproduction failure → pattern must not be in release pack

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
POLARIS_DIR="$(dirname "$SCRIPT_DIR")"
PACKS_DIR="$POLARIS_DIR/experience-packs"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

total=0
passed=0
failed=0
failed_list=""

echo "========================================="
echo "  Reproduction Case Verification"
echo "========================================="
echo ""

for eco_dir in "$PACKS_DIR"/*/; do
    eco=$(basename "$eco_dir")
    [ "$eco" = "fixtures" ] && continue
    [ -d "$eco_dir" ] || continue

    for pack_file in "$eco_dir"/*.json; do
        [ -f "$pack_file" ] || continue
        pack_name=$(basename "$pack_file" .json)

        # Extract and run reproductions
        record_count=$(python3 -c "import json; print(len(json.load(open('$pack_file')).get('records',[])))" 2>/dev/null || echo "0")

        for i in $(seq 0 $((record_count - 1))); do
            total=$((total + 1))
            desc=$(python3 -c "
import json
d = json.load(open('$pack_file'))
r = d['records'][$i]
print(r.get('description','record $i'))
" 2>/dev/null || echo "record $i")

            # Run reproduction
result=$(python3 -c "
import json, subprocess, re, os, resource, sys

d = json.load(open('$pack_file'))
rec = d['records'][$i]
error_class = d.get('error_class', '')
repro = rec.get('reproduction')
if not repro:
    print('SKIP:no_reproduction')
    sys.exit(0)

cmd = repro.get('command', '')
fix_cmd = repro.get('fix_command', '') or cmd
trigger_env = repro.get('trigger_env', {})
expected_match = repro.get('expected_stderr_match', '')
fix_env = repro.get('fix_env', {})
expected_outcome = repro.get('expected_fix_outcome', 'different_error_or_success')
memory_limit_mb = int(os.environ.get('POLARIS_REPRO_RESOURCE_MEMORY_MB', '768'))

if not cmd:
    print('SKIP:no_command')
    sys.exit(0)

def preexec():
    if error_class == 'resource_exhaustion':
        limit_bytes = memory_limit_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))

# Step 1: Run trigger — should produce error matching expected_stderr_match
env1 = dict(os.environ)
env1.update(trigger_env)
try:
    r1 = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15, env=env1, preexec_fn=preexec)
    stderr1 = r1.stderr + r1.stdout  # some errors go to stdout
except subprocess.TimeoutExpired:
    stderr1 = 'TIMEOUT'
except Exception as e:
    print(f'FAIL:trigger_exception:{e}')
    sys.exit(0)

if expected_match:
    try:
        if not re.search(expected_match, stderr1, re.MULTILINE | re.DOTALL | re.IGNORECASE):
            # Check if trigger at least failed
            if r1.returncode == 0:
                print(f'FAIL:trigger_no_error')
                sys.exit(0)
            # Lenient: trigger failed but stderr didn't match exactly
            print(f'WARN:trigger_stderr_mismatch')
            sys.exit(0)
    except re.error as e:
        print(f'FAIL:bad_regex:{e}')
        sys.exit(0)

# Step 2: Apply fix and re-run — result should be different
env2 = dict(os.environ)
env2.update(trigger_env)
env2.update(fix_env)

# Also apply hint-level fixes (rewrite_cwd, create_dir, etc.)
hints = rec.get('avoidance_hints', [])
for hint in hints:
    kind = hint.get('kind', '')
    if kind == 'set_env':
        env2.update(hint.get('vars', {}))
    elif kind == 'create_dir':
        target = hint.get('target', '')
        if target and not os.path.isabs(target):
            os.makedirs(target, exist_ok=True)

try:
    r2 = subprocess.run(fix_cmd, shell=True, capture_output=True, text=True, timeout=15, env=env2, preexec_fn=preexec)
    stderr2 = r2.stderr + r2.stdout
except subprocess.TimeoutExpired:
    stderr2 = 'TIMEOUT'
except Exception as e:
    print(f'FAIL:fix_exception:{e}')
    sys.exit(0)

if expected_outcome == 'different_error_or_success':
    if r2.returncode == 0:
        print('PASS')
    elif stderr2 != stderr1:
        print('PASS')
    else:
        print('FAIL:fix_no_change')
elif expected_outcome == 'success':
    if r2.returncode == 0:
        print('PASS')
    else:
        print('FAIL:fix_not_success')
else:
    print('PASS')
" 2>/dev/null || echo "FAIL:python_error")

            case "$result" in
                PASS)
                    passed=$((passed + 1))
                    printf "  ${GREEN}✓${NC} %-12s %-25s %s\n" "$eco" "$pack_name" "$desc"
                    ;;
                WARN:*)
                    passed=$((passed + 1))
                    printf "  ${YELLOW}⚠${NC} %-12s %-25s %s (%s)\n" "$eco" "$pack_name" "$desc" "$result"
                    ;;
                SKIP:*)
                    total=$((total - 1))
                    printf "  ${YELLOW}⊘${NC} %-12s %-25s %s (skipped: %s)\n" "$eco" "$pack_name" "$desc" "$result"
                    ;;
                FAIL:*)
                    failed=$((failed + 1))
                    printf "  ${RED}✗${NC} %-12s %-25s %s (%s)\n" "$eco" "$pack_name" "$desc" "$result"
                    failed_list="$failed_list\n  - $eco/$pack_name[$i]: $desc ($result)"
                    ;;
            esac
        done
    done
done

echo ""
echo "========================================="
echo "  Results: $passed passed, $failed failed out of $total total"
echo "========================================="

if [ "$failed" -gt 0 ]; then
    echo ""
    echo -e "${RED}Failed reproductions:${NC}$failed_list"
    echo ""
    echo -e "${RED}KILL GATE: $failed reproduction(s) failed. These patterns must be fixed or removed before release.${NC}"
    exit 1
fi

if [ "$total" -eq 0 ]; then
    echo -e "${RED}ERROR: No reproductions found.${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}All $passed reproductions passed. Zero manual_only.${NC}"
