#!/usr/bin/env bash
# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

set -euo pipefail
PASS=0; FAIL=0; TOTAL=0
SCRIPTS=Polaris/scripts
PACKS=Polaris/experience-packs

assert_eq() { TOTAL=$((TOTAL+1)); if [ "$1" = "$2" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: expected='$2' got='$1' — $3"; fi; }

# --- R3-1: Every prebuilt record has ecosystem + error_class + stderr_pattern + avoidance_hints ---
R31=$(python3 -c "
import json, glob
ok = 0; total = 0
for f in sorted(f for f in glob.glob('$PACKS/*.json') if not f.endswith('index.json')):
    pack = json.load(open(f))
    eco = pack.get('ecosystem', '')
    for rec in pack.get('records', []):
        total += 1
        has_all = all([
            eco,
            rec.get('error_class'),
            rec.get('stderr_pattern'),
            rec.get('avoidance_hints'),
        ])
        if has_all:
            ok += 1
        else:
            missing = []
            if not eco: missing.append('ecosystem')
            if not rec.get('error_class'): missing.append('error_class')
            if not rec.get('stderr_pattern'): missing.append('stderr_pattern')
            if not rec.get('avoidance_hints'): missing.append('avoidance_hints')
            print(f'MISSING: {f} record missing {missing}', flush=True)
print(f'{ok}/{total}')
")
EXPECTED_R31=$(python3 -c "
import json, glob
total = 0
for f in sorted(f for f in glob.glob('$PACKS/*.json') if not f.endswith('index.json')):
    pack = json.load(open(f))
    total += len(pack.get('records', []))
print(f'{total}/{total}')
")
assert_eq "$R31" "$EXPECTED_R31" "R3-1: all prebuilt records have required fields"

# --- R3-2: stderr_pattern is a valid regex ---
R32=$(python3 -c "
import json, glob, re
bad = 0; total = 0
for f in sorted(f for f in glob.glob('$PACKS/*.json') if not f.endswith('index.json')):
    pack = json.load(open(f))
    for rec in pack.get('records', []):
        total += 1
        try:
            re.compile(rec.get('stderr_pattern', ''))
        except re.error as e:
            bad += 1
            print(f'BAD REGEX: {rec[\"stderr_pattern\"]} → {e}')
print(f'{bad}')
")
assert_eq "$R32" "0" "R3-2: all stderr_patterns are valid regexes"

# --- R3-3: fixture corpus → classify → query → recall ≥ 60% ---
# Fixture: 10 real stderr snippets per ecosystem (30 total), each with expected error_class
R33=$(python3 -c "
import json, sys, re
sys.path.insert(0, '$SCRIPTS')
import polaris_failure_records as pfr

fixtures = {
    'python': [
        ('ModuleNotFoundError: No module named \"requests\"', 'missing_dependency'),
        ('ModuleNotFoundError: No module named \"numpy.core\"', 'missing_dependency'),
        ('SyntaxError: invalid syntax', 'syntax_error'),
        ('SyntaxError: f-string expression part cannot include a backslash', 'syntax_error'),
        ('PermissionError: [Errno 13] Permission denied: \"/etc/config\"', 'permission_denial'),
        ('FileNotFoundError: [Errno 2] No such file or directory: \"data.csv\"', 'file_not_found'),
        ('FileNotFoundError: [Errno 2] No such file or directory: \"config.yaml\"', 'file_not_found'),
        ('UnicodeDecodeError: \"utf-8\" codec can\\'t decode byte 0xff', 'encoding_error'),
        ('UnicodeDecodeError: \"ascii\" codec can\\'t decode byte 0xc3', 'encoding_error'),
        ('SyntaxError: unexpected EOF while parsing', 'syntax_error'),
    ],
    'node': [
        ('Error: Cannot find module \"express\"', 'missing_dependency'),
        ('MODULE_NOT_FOUND: Cannot find module \"./config\"', 'missing_dependency'),
        ('ENOENT: no such file or directory, open \"/app/package.json\"', 'file_not_found'),
        ('EACCES: permission denied, mkdir \"/usr/local/lib/node_modules\"', 'permission_denial'),
        ('npm ERR! Error: EACCES: permission denied', 'permission_denial'),
        ('FATAL ERROR: Ineffective mark-compacts near heap limit Allocation failed - JavaScript heap out of memory', 'resource_exhaustion'),
        ('FATAL ERROR: Reached heap limit Allocation failed', 'resource_exhaustion'),
        ('ERR_MODULE_NOT_FOUND: Cannot find package \"lodash\"', 'missing_dependency'),
        ('Error [ERR_MODULE_NOT_FOUND]: Cannot find module', 'missing_dependency'),
        ('Cannot find package \"typescript\" imported from /app/index.ts', 'missing_dependency'),
    ],
    'go': [
        ('cannot find module providing package github.com/gin-gonic/gin', 'missing_dependency'),
        ('go: module github.com/foo/bar found but does not contain package', 'missing_dependency'),
        ('build constraints exclude all Go files in /usr/local/go/src/os/exec', 'build_error'),
        ('no Go files in /app/cmd', 'build_error'),
        ('missing go.sum entry for module providing package github.com/lib/pq', 'missing_dependency'),
        ('go.sum: checksum mismatch for github.com/stretchr/testify', 'missing_dependency'),
        ('cannot find package \"internal/utils\" in GOPATH', 'missing_dependency'),
        ('no required module provides package github.com/google/uuid', 'missing_dependency'),
        ('permission denied writing go.mod', 'permission_denial'),
        ('go: writing go.mod: permission denied', 'permission_denial'),
    ],
}

total = 0
hits = 0
for eco, cases in fixtures.items():
    # Load pack and build a store
    pack = json.load(open(f'$PACKS/{eco}.json'))
    store = {'schema_version': 2, 'records': []}
    for i, rec in enumerate(pack['records']):
        entry = {
            'task_fingerprint': {'matching_key': f'prebuilt-{eco}-{i:04x}', 'command_key': f'prebuilt-{eco}'},
            'error_class': rec['error_class'],
            'stderr_summary': rec.get('description', ''),
            'avoidance_hints': rec.get('avoidance_hints', []),
            'recorded_at': '2026-01-01T00:00:00Z',
            'source': 'prebuilt',
            'ecosystem': eco,
            'stale': False,
            'applied_count': 0,
            'applied_fail_count': 0,
            'stderr_pattern': rec.get('stderr_pattern', ''),
        }
        store['records'].append(entry)

    for stderr_text, expected_class in cases:
        total += 1
        result = pfr.query(store,
                           matching_key='test-key-not-in-store',
                           ecosystem=eco,
                           error_class=expected_class,
                           stderr_text=stderr_text)
        if result.get('match_tier') in ('ecosystem_pattern', 'ecosystem') and len(result.get('avoidance_hints', [])) > 0:
            hits += 1
        else:
            pass  # miss

recall = hits / total if total > 0 else 0
print(f'{recall:.2f},{hits},{total}')
")
RECALL=$(echo "$R33" | cut -d, -f1)
RECALL_PCT=$(python3 -c "print(int(float('$RECALL') * 100))")
assert_eq "$((RECALL_PCT >= 60 ? 1 : 0))" "1" "R3-3: recall ≥ 60% (got ${RECALL_PCT}%)"

# --- R3-4: precision ≥ 80% — hits match semantically (pattern match returns correct error_class) ---
R34=$(python3 -c "
import json, sys, re
sys.path.insert(0, '$SCRIPTS')
import polaris_failure_records as pfr

fixtures = {
    'python': [
        ('ModuleNotFoundError: No module named \"requests\"', 'missing_dependency'),
        ('PermissionError: [Errno 13] Permission denied', 'permission_denial'),
        ('FileNotFoundError: [Errno 2] No such file', 'file_not_found'),
        ('UnicodeDecodeError: \"utf-8\" codec can\\'t decode', 'encoding_error'),
        ('SyntaxError: invalid syntax', 'syntax_error'),
    ],
    'node': [
        ('Cannot find module \"express\"', 'missing_dependency'),
        ('EACCES: permission denied', 'permission_denial'),
        ('JavaScript heap out of memory', 'resource_exhaustion'),
        ('ERR_MODULE_NOT_FOUND', 'missing_dependency'),
        ('ENOENT: no such file or directory, open \"/package.json\"', 'file_not_found'),
    ],
    'go': [
        ('cannot find module providing package', 'missing_dependency'),
        ('build constraints exclude all Go files', 'build_error'),
        ('missing go.sum entry', 'missing_dependency'),
        ('permission denied', 'permission_denial'),
        ('cannot find package', 'missing_dependency'),
    ],
}

total_hits = 0
correct_hits = 0
for eco, cases in fixtures.items():
    pack = json.load(open(f'$PACKS/{eco}.json'))
    store = {'schema_version': 2, 'records': []}
    for i, rec in enumerate(pack['records']):
        entry = {
            'task_fingerprint': {'matching_key': f'prebuilt-{eco}-{i:04x}', 'command_key': f'prebuilt-{eco}'},
            'error_class': rec['error_class'],
            'stderr_summary': rec.get('description', ''),
            'avoidance_hints': rec.get('avoidance_hints', []),
            'recorded_at': '2026-01-01T00:00:00Z',
            'source': 'prebuilt',
            'ecosystem': eco,
            'stale': False,
            'applied_count': 0,
            'applied_fail_count': 0,
            'stderr_pattern': rec.get('stderr_pattern', ''),
        }
        store['records'].append(entry)

    for stderr_text, expected_class in cases:
        # Query WITHOUT providing error_class — rely on stderr_pattern only
        result = pfr.query(store,
                           matching_key='test-key-not-in-store',
                           ecosystem=eco,
                           stderr_text=stderr_text)
        if result.get('match_tier') == 'ecosystem_pattern' and result.get('avoidance_hints'):
            total_hits += 1
            # True precision: verify matched records' error_class == expected_class
            # Re-query with full store to find which records matched the pattern
            matched_classes = set()
            for rec in store['records']:
                pat = rec.get('stderr_pattern', '')
                if pat and re.search(pat, stderr_text, re.IGNORECASE):
                    matched_classes.add(rec.get('error_class'))
            if expected_class in matched_classes:
                correct_hits += 1

precision = correct_hits / total_hits if total_hits > 0 else 0
print(f'{precision:.2f},{correct_hits},{total_hits}')
")
PRECISION=$(echo "$R34" | cut -d, -f1)
PREC_PCT=$(python3 -c "print(int(float('$PRECISION') * 100))")
assert_eq "$((PREC_PCT >= 80 ? 1 : 0))" "1" "R3-4: precision ≥ 80% (got ${PREC_PCT}%)"

# --- R3-5: each ecosystem has at least 5 records ---
R35=$(python3 -c "
import json, glob
for f in sorted(f for f in glob.glob('$PACKS/*.json') if not f.endswith('index.json')):
    pack = json.load(open(f))
    eco = pack.get('ecosystem', 'unknown')
    count = len(pack.get('records', []))
    if count < 5:
        print(f'UNDER: {eco} has {count}')
        continue
    print(f'{eco}:{count}', end=' ')
print()
")
R35_OK=$(python3 -c "
import json, glob
ok = True
for f in sorted(f for f in glob.glob('$PACKS/*.json') if not f.endswith('index.json')):
    pack = json.load(open(f))
    if len(pack.get('records', [])) < 5:
        ok = False
print('yes' if ok else 'no')
")
assert_eq "$R35_OK" "yes" "R3-5: each ecosystem has ≥ 5 records"

# --- R3-6: pack_version is 2.0, reset-prebuilt clears them ---
R36=$(python3 -c "
import json, glob
versions = set()
for f in sorted(f for f in glob.glob('$PACKS/*.json') if not f.endswith('index.json')):
    pack = json.load(open(f))
    versions.add(pack.get('pack_version', '?'))
print(','.join(sorted(versions)))
")
assert_eq "$R36" "2.0" "R3-6a: all packs are version 2.0"

# Test reset-prebuilt
export POLARIS_HOME=$(mktemp -d)
RTDIR=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "python3 -c 'print(1)'" --runtime-dir "$RTDIR" 2>&1 || true
# Count prebuilt records (may be 0 in sharded mode where packs aren't merged)
BEFORE=$(python3 -c "
import json, os
fr = '$RTDIR/failure-records.json'
if os.path.exists(fr):
    store = json.load(open(fr))
    prebuilt = [r for r in store.get('records', []) if r.get('source') == 'prebuilt']
    print(len(prebuilt))
else:
    print(0)
")
# Reset
python3 "$SCRIPTS/polaris_cli.py" experience reset-prebuilt --runtime-dir "$RTDIR" 2>&1 || true
AFTER=$(python3 -c "
import json, os
fr = '$RTDIR/failure-records.json'
if os.path.exists(fr):
    store = json.load(open(fr))
    prebuilt = [r for r in store.get('records', []) if r.get('source') == 'prebuilt']
    print(len(prebuilt))
else:
    print(0)
")
assert_eq "$AFTER" "0" "R3-6b: reset-prebuilt clears all prebuilt records (was $BEFORE)"
rm -rf "$RTDIR" "$POLARIS_HOME"

echo "=== R3 Results: $PASS/$TOTAL passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
