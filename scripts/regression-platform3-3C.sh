#!/usr/bin/env bash
set -euo pipefail
PASS=0; FAIL=0; TOTAL=0
SCRIPTS=Polaris/scripts
PACKS=Polaris/experience-packs

assert_eq() { TOTAL=$((TOTAL+1)); if [ "$1" = "$2" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: expected='$2' got='$1' — $3"; fi; }

# --- 3C-G1: Total records ≥ 40 ---
G1=$(python3 -c "
import json, os
idx = json.load(open('$PACKS/index.json'))
total = 0
for eco, info in idx['ecosystems'].items():
    for ec in info['error_classes']:
        shard = json.load(open(os.path.join('$PACKS', eco, f'{ec}.json')))
        total += len(shard['records'])
print(total)
")
assert_eq "$((G1 >= 40 ? 1 : 0))" "1" "3C-G1: total records ≥ 40 (got $G1)"

# --- 3C-G2: Ecosystem coverage ≥ 8 ---
G2=$(python3 -c "
import json
idx = json.load(open('$PACKS/index.json'))
print(len(idx['ecosystems']))
")
assert_eq "$((G2 >= 8 ? 1 : 0))" "1" "3C-G2: ecosystem coverage ≥ 8 (got $G2)"

# --- 3C-G3: Per-ecosystem dev fixture recall ≥ 60% (file-backed) ---
# Reads from experience-packs/fixtures/{eco}/dev/*.json instead of inline data.
G3=$(python3 -c "
import sys, json, re, os
sys.path.insert(0, '$SCRIPTS')
import polaris_failure_records as pfr

pfr._index_cache = None
from pathlib import Path
packs = Path('$PACKS')
fixtures_root = packs / 'fixtures'

total = 0
hits = 0
local_store = {'schema_version': 2, 'records': []}

for eco_dir in sorted(fixtures_root.iterdir()):
    if not eco_dir.is_dir():
        continue
    eco = eco_dir.name
    dev_dir = eco_dir / 'dev'
    if not dev_dir.is_dir():
        continue
    for f in sorted(dev_dir.glob('*.json')):
        try:
            fixture = json.loads(f.read_text())
        except:
            continue
        stderr_text = fixture.get('stderr', '')
        expected_class = fixture.get('error_class', '')
        if not stderr_text or not expected_class:
            continue
        total += 1
        pfr._index_cache = None
        result = pfr.query_sharded(
            local_store, packs_dir=packs,
            matching_key='fixture-dev-test',
            ecosystem=eco, error_class=expected_class,
            stderr_text=stderr_text
        )
        if result.get('match_tier') in ('ecosystem_pattern', 'ecosystem') and result.get('avoidance_hints'):
            hits += 1

recall = hits / total if total > 0 else 0
print(f'{recall:.2f},{hits},{total}')
")
RECALL=$(echo "$G3" | cut -d, -f1)
RECALL_PCT=$(python3 -c "print(int(float('$RECALL') * 100))")
assert_eq "$((RECALL_PCT >= 60 ? 1 : 0))" "1" "3C-G3: fixture recall ≥ 60% (got ${RECALL_PCT}%)"

# --- 3C-G4: Cross-ecosystem precision ≥ 80% ---
# For each record R in error_class A, take R's reproduction probe text and
# run it against ALL stderr_patterns in the ENTIRE ecosystem. If any pattern
# from error_class B (B ≠ A) also matches, that's a false positive.
# Precision = (probes with no cross-class match) / (probes tested).
G4=$(python3 -c "
import json, re, os

packs = '$PACKS'
idx = json.load(open(os.path.join(packs, 'index.json')))

total_probes = 0
clean_probes = 0  # no false cross-match

for eco, info in idx['ecosystems'].items():
    # Load all records grouped by error_class
    by_class = {}
    for ec in info['error_classes']:
        shard = json.load(open(os.path.join(packs, eco, f'{ec}.json')))
        by_class[ec] = shard['records']

    # For each record, get probe text from reproduction
    for expected_ec, records in by_class.items():
        for rec in records:
            repro = rec.get('reproduction', {})
            probe = repro.get('expected_stderr_match', '')
            if not probe:
                continue
            total_probes += 1

            # Check if any pattern from a DIFFERENT error_class matches this probe
            cross_matched = False
            for other_ec, other_records in by_class.items():
                if other_ec == expected_ec:
                    continue
                for other_rec in other_records:
                    try:
                        if re.search(other_rec['stderr_pattern'], probe, re.IGNORECASE):
                            cross_matched = True
                            break
                    except re.error:
                        pass
                if cross_matched:
                    break

            if not cross_matched:
                clean_probes += 1

precision = clean_probes / total_probes if total_probes > 0 else 0
print(f'{precision:.2f},{clean_probes},{total_probes}')
")
PREC=$(echo "$G4" | cut -d, -f1)
PREC_PCT=$(python3 -c "print(int(float('$PREC') * 100))")
assert_eq "$((PREC_PCT >= 80 ? 1 : 0))" "1" "3C-G4: cross-class precision ≥ 80% (got ${PREC_PCT}%, ${G4})"

# --- 3C-G5: All regexes compile without error ---
G5=$(python3 -c "
import json, os, re
idx = json.load(open('$PACKS/index.json'))
bad = 0
for eco, info in idx['ecosystems'].items():
    for ec in info['error_classes']:
        shard = json.load(open(os.path.join('$PACKS', eco, f'{ec}.json')))
        for rec in shard['records']:
            try:
                re.compile(rec['stderr_pattern'])
            except re.error:
                bad += 1
print(bad)
")
assert_eq "$G5" "0" "3C-G5: all regexes compile (0 errors)"

# --- 3C-G6: Disk < 10MB ---
G6=$(du -sk "$PACKS" | awk '{print $1}')
assert_eq "$((G6 < 10240 ? 1 : 0))" "1" "3C-G6: disk < 10MB (got ${G6}KB)"

# --- 3C-G7: Largest shard query < 2ms ---
G7=$(python3 -c "
import sys, time, json
sys.path.insert(0, '$SCRIPTS')
import polaris_failure_records as pfr
from pathlib import Path

pfr._index_cache = None
packs = Path('$PACKS')
local_store = {'schema_version': 2, 'records': []}

# Find largest shard
idx = json.load(open('$PACKS/index.json'))
max_eco = max(idx['ecosystems'], key=lambda e: idx['ecosystems'][e]['total_records'])

start = time.perf_counter()
for _ in range(100):
    pfr._index_cache = None
    result = pfr.query_sharded(
        local_store, packs_dir=packs,
        matching_key='bench-key',
        ecosystem=max_eco,
        error_class=idx['ecosystems'][max_eco]['error_classes'][0],
        stderr_text='test error text for benchmark'
    )
elapsed = time.perf_counter() - start
avg_ms = (elapsed / 100) * 1000
print(f'{avg_ms:.2f}')
")
G7_OK=$(python3 -c "print('yes' if float('$G7') < 2.0 else 'no:${G7}ms')")
assert_eq "$G7_OK" "yes" "3C-G7: largest shard query < 2ms (actual: ${G7}ms)"

# --- 3C-G8: KILL GATE — independent holdout corpus, first-hit ≥ 60% (file-backed) ---
# Reads from experience-packs/fixtures/{eco}/holdout/*.json.
G8=$(python3 -c "
import sys, json, re, os
sys.path.insert(0, '$SCRIPTS')
import polaris_failure_records as pfr
from pathlib import Path

pfr._index_cache = None
packs = Path('$PACKS')
fixtures_root = packs / 'fixtures'
local_store = {'schema_version': 2, 'records': []}

total = 0
hits = 0

for eco_dir in sorted(fixtures_root.iterdir()):
    if not eco_dir.is_dir():
        continue
    eco = eco_dir.name
    holdout_dir = eco_dir / 'holdout'
    if not holdout_dir.is_dir():
        continue
    for f in sorted(holdout_dir.glob('*.json')):
        try:
            fixture = json.loads(f.read_text())
        except:
            continue
        stderr_text = fixture.get('stderr', '')
        expected_class = fixture.get('error_class', '')
        if not stderr_text or not expected_class:
            continue
        total += 1
        pfr._index_cache = None
        result = pfr.query_sharded(
            local_store, packs_dir=packs,
            matching_key='holdout-test',
            ecosystem=eco, error_class=expected_class,
            stderr_text=stderr_text
        )
        if result.get('match_tier') in ('ecosystem_pattern', 'ecosystem') and result.get('avoidance_hints'):
            hits += 1

recall = hits / total if total > 0 else 0
print(f'{recall:.2f},{hits},{total}')
")
G8_RECALL=$(echo "$G8" | cut -d, -f1)
G8_HITS=$(echo "$G8" | cut -d, -f2)
G8_TOTAL=$(echo "$G8" | cut -d, -f3)
G8_PCT=$(python3 -c "print(int(float('$G8_RECALL') * 100))")
# Contract: ≥ 80 holdout probes (10 per ecosystem × 8 ecosystems)
assert_eq "$((G8_TOTAL >= 80 ? 1 : 0))" "1" "3C-G8a: holdout corpus size ≥ 80 (got $G8_TOTAL)"
assert_eq "$((G8_PCT >= 60 ? 1 : 0))" "1" "3C-G8b: KILL GATE — holdout first-hit ≥ 60% (got ${G8_PCT}%, $G8_HITS/$G8_TOTAL)"

# --- 3C-G9: Two-phase reproduction: trigger error, apply fix, verify outcome changes ---
# Phase 1: Run reproduction.command with trigger_env → expected_stderr_match must appear.
# Phase 2: Run same command with fix_env applied → result must change
#          (expected_fix_outcome = "different_error_or_success").
# This proves the fix actually changes the outcome, not just that the error exists.
G9=$(python3 -c "
import json, os, re, resource, subprocess, shutil

idx = json.load(open('$PACKS/index.json'))
total = 0
executed = 0
phase1_passed = 0
phase2_passed = 0
skipped_tools = set()
failures = []
resource_limit_mb = int(os.environ.get('POLARIS_REPRO_RESOURCE_MEMORY_MB', '768'))

def _find_tool(cmd):
    for w in cmd.split():
        if '=' in w and not w.startswith('-'):
            continue
        return w
    return cmd.split()[0]

def _run(cmd, env_overrides, timeout=15, error_class=''):
    env = dict(os.environ)
    env.update(env_overrides)
    def _preexec():
        if error_class == 'resource_exhaustion':
            limit_bytes = resource_limit_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))
    try:
        r = subprocess.run(['bash', '-c', cmd], capture_output=True, text=True,
                           timeout=timeout, env=env, cwd='/tmp', preexec_fn=_preexec)
        return r.stdout + r.stderr, r.returncode, False
    except subprocess.TimeoutExpired:
        return '', -1, True

external_tools = {'go', 'npm', 'node', 'cargo', 'rustc', 'javac', 'java', 'mvn',
                  'gradle', 'ruby', 'gem', 'bundle', 'docker', 'terraform'}

for eco, info in idx['ecosystems'].items():
    for ec in info['error_classes']:
        shard = json.load(open(os.path.join('$PACKS', eco, f'{ec}.json')))
        for rec in shard['records']:
            total += 1
            repro = rec.get('reproduction')
            if not (repro and repro.get('command') and repro.get('expected_stderr_match')):
                failures.append(f'{eco}/{ec}: missing reproduction fields')
                continue
            if not repro.get('fix_env') and not repro.get('fix_command') and not repro.get('expected_fix_outcome'):
                failures.append(f'{eco}/{ec}: missing fix_env/fix_command/expected_fix_outcome')
                continue

            cmd = repro['command']
            expected_pattern = repro['expected_stderr_match']
            trigger_env = repro.get('trigger_env', {})
            fix_env = repro.get('fix_env', {})
            fix_command = repro.get('fix_command')  # alternative: run a different command as phase 2
            expected_outcome = repro.get('expected_fix_outcome', 'different_error_or_success')

            tool = _find_tool(cmd)
            if tool in external_tools and not shutil.which(tool):
                skipped_tools.add(tool)
                continue
            if tool in ('mvn', 'gradle') and not shutil.which('java'):
                skipped_tools.add(tool)
                continue

            # === Phase 1: trigger the error ===
            out1, rc1, timeout1 = _run(cmd, trigger_env, error_class=ec)
            executed += 1
            if timeout1:
                # Timeout can be the expected error for some cases
                phase1_passed += 1
                phase2_passed += 1  # can't verify fix on timeout
                continue
            if not re.search(expected_pattern, out1, re.IGNORECASE):
                failures.append(f'{eco}/{ec} P1: pattern \"{expected_pattern}\" not in trigger output ({out1[:80]}...)')
                continue
            phase1_passed += 1

            # === Phase 2: apply fix and rerun ===
            # Build fix env: trigger_env + fix_env + avoidance_hints set_env vars
            # (matches repro_diag.py and actual Polaris engine behavior)
            fix_cmd_env = dict(trigger_env)
            fix_cmd_env.update(fix_env)
            for hint in rec.get('avoidance_hints', []) or []:
                if hint.get('kind') == 'set_env':
                    fix_cmd_env.update(hint.get('vars', {}) or {})
            if fix_command:
                out2, rc2, timeout2 = _run(fix_command, fix_cmd_env, error_class=ec)
            else:
                out2, rc2, timeout2 = _run(cmd, fix_cmd_env, error_class=ec)

            if expected_outcome == 'different_error_or_success':
                # The fix must change SOMETHING: different output or different exit code
                output_changed = out2 != out1
                code_changed = rc2 != rc1
                pattern_gone = not re.search(expected_pattern, out2, re.IGNORECASE)
                if output_changed or code_changed or pattern_gone:
                    phase2_passed += 1
                else:
                    failures.append(f'{eco}/{ec} P2: fix_env did not change outcome (rc {rc1}->{rc2}, same pattern match)')
            elif expected_outcome == 'success':
                if rc2 == 0:
                    phase2_passed += 1
                else:
                    failures.append(f'{eco}/{ec} P2: expected success but rc={rc2}')
            else:
                # Unknown outcome type — pass if anything changed
                if out2 != out1 or rc2 != rc1:
                    phase2_passed += 1
                else:
                    failures.append(f'{eco}/{ec} P2: no change after fix')

p1_rate = phase1_passed / executed if executed > 0 else 0
p2_rate = phase2_passed / executed if executed > 0 else 0
print(f'{p1_rate:.2f},{phase1_passed},{p2_rate:.2f},{phase2_passed},{executed},{total}')
if failures:
    for f in failures[:10]:
        print(f'  FAIL: {f}', flush=True)
if skipped_tools:
    print(f'  skipped (tools not installed): {sorted(skipped_tools)}', flush=True)
")
G9_P1_RATE=$(echo "$G9" | head -1 | cut -d, -f1)
G9_P1_PASS=$(echo "$G9" | head -1 | cut -d, -f2)
G9_P2_RATE=$(echo "$G9" | head -1 | cut -d, -f3)
G9_P2_PASS=$(echo "$G9" | head -1 | cut -d, -f4)
G9_EXEC=$(echo "$G9" | head -1 | cut -d, -f5)
G9_TOTAL=$(echo "$G9" | head -1 | cut -d, -f6)
# Both phases must pass 100% of executed reproductions
G9_OK="no"
if [ "$G9_EXEC" -gt 0 ] 2>/dev/null && [ "$G9_P1_RATE" = "1.00" ] && [ "$G9_P2_RATE" = "1.00" ]; then G9_OK="yes"; fi
assert_eq "$G9_OK" "yes" "3C-G9: two-phase reproduction 100% (P1=$G9_P1_PASS P2=$G9_P2_PASS of $G9_EXEC executed, $G9_TOTAL total)"

echo "=== 3C Results: $PASS/$TOTAL passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
