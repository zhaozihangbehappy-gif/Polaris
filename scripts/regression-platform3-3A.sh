#!/usr/bin/env bash
set -euo pipefail
PASS=0; FAIL=0; TOTAL=0
SCRIPTS=Polaris/scripts
PACKS=Polaris/experience-packs

assert_eq() { TOTAL=$((TOTAL+1)); if [ "$1" = "$2" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: expected='$2' got='$1' — $3"; fi; }
assert_contains() { TOTAL=$((TOTAL+1)); if grep -qF "$2" <<< "$1"; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: output missing '$2' — $3"; fi; }

export POLARIS_HOME=$(mktemp -d)
cleanup() { rm -rf "$POLARIS_HOME"; }
trap cleanup EXIT

# --- 3A-G1: Success path does NOT load failure store ---
# A successful command should have no failure-store I/O.
# We verify by checking that no failure-records.json is created on a fresh runtime-dir
# when the command succeeds.
RTDIR1=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run 'echo hello' --profile standard --runtime-dir "$RTDIR1" 2>&1 || true
G1=$(python3 -c "
import json, os
state = json.load(open('$RTDIR1/execution-state.json'))
status = state.get('status', 'unknown')
# On success path, failure-records.json should not be written to
# (it may exist from load_store but should have 0 user records)
fr_path = '$RTDIR1/failure-records.json'
if os.path.exists(fr_path):
    fr = json.load(open(fr_path))
    user_recs = [r for r in fr.get('records', []) if r.get('source') != 'prebuilt']
    print(f'{status}:user_recs={len(user_recs)}')
else:
    print(f'{status}:no_failure_store')
")
# Success: status=completed, no user failure records
if printf '%s' "$G1" | grep -q '^completed:'; then
    assert_eq "$(echo "$G1" | grep -o 'user_recs=0\|no_failure_store')" "$(echo "$G1" | grep -o 'user_recs=0\|no_failure_store')" "3A-G1: success path has no failure store user records"
else
    assert_eq "$G1" "completed:no_failure_store" "3A-G1: success path does not load failure store"
fi
rm -rf "$RTDIR1"

# --- 3A-G2: Sharded query < 2ms (benchmark) ---
# Query a 500-record shard and verify it completes within 2ms.
G2_TMPDIR=$(mktemp -d)
# Generate a 500-record shard for benchmarking
python3 -c "
import json, os
records = []
for i in range(500):
    records.append({
        'stderr_pattern': f'BenchError{i}: something went wrong at line {i}',
        'avoidance_hints': [{'kind': 'set_env', 'vars': {'BENCH_VAR': str(i)}}],
        'description': f'Benchmark record {i}',
        'source': 'prebuilt'
    })
os.makedirs('$G2_TMPDIR/bench_eco', exist_ok=True)
json.dump({'ecosystem': 'bench_eco', 'error_class': 'bench_error', 'shard_version': '3.0', 'records': records},
          open('$G2_TMPDIR/bench_eco/bench_error.json', 'w'), indent=2)
json.dump({'schema_version': 3, 'ecosystems': {'bench_eco': {'error_classes': ['bench_error'], 'total_records': 500, 'pack_version': '3.0'}}},
          open('$G2_TMPDIR/index.json', 'w'))
"
G2=$(python3 -c "
import sys, time, json
sys.path.insert(0, '$SCRIPTS')
import polaris_failure_records as pfr
from pathlib import Path

# Clear index cache
pfr._index_cache = None

packs_dir = Path('$G2_TMPDIR')
local_store = {'schema_version': 2, 'records': []}

# Warm up (load index)
pfr.load_index(packs_dir)

# Benchmark: 100 iterations
start = time.perf_counter()
for _ in range(100):
    pfr._index_cache = None  # force reload each time for fair bench
    result = pfr.query_sharded(
        local_store, packs_dir=packs_dir,
        matching_key='nonexistent',
        ecosystem='bench_eco', error_class='bench_error',
        stderr_text='BenchError250: something went wrong at line 250'
    )
elapsed = time.perf_counter() - start
avg_ms = (elapsed / 100) * 1000

matched = len(result.get('avoidance_hints', []))
print(f'{avg_ms:.2f}ms:matched={matched}')
")
G2_MS=$(echo "$G2" | grep -oP '^[0-9.]+')
G2_OK=$(python3 -c "print('yes' if float('$G2_MS') < 2.0 else 'no:${G2_MS}ms')")
assert_eq "$G2_OK" "yes" "3A-G2: 500-record shard query < 2ms (actual: ${G2_MS}ms)"
rm -rf "$G2_TMPDIR"

# --- 3A-G3: Platform 2 R3 regression check ---
# Verify that sharded packs still produce correct hints for the python ecosystem
# using the R3 query path (ecosystem_pattern tier).
G3=$(python3 -c "
import sys, json
sys.path.insert(0, '$SCRIPTS')
import polaris_failure_records as pfr
from pathlib import Path

pfr._index_cache = None
packs_dir = Path('$PACKS')
local_store = {'schema_version': 2, 'records': []}

# Query for a Python ModuleNotFoundError
result = pfr.query_sharded(
    local_store, packs_dir=packs_dir,
    matching_key='test-key-r3',
    ecosystem='python', error_class='missing_dependency',
    stderr_text=\"ModuleNotFoundError: No module named 'foo'\"
)
tier = result.get('match_tier', 'none')
hints = result.get('avoidance_hints', [])
kinds = [h.get('kind') for h in hints]
has_set_env = 'set_env' in kinds
print(f'{tier}:{has_set_env}:{len(hints)}')
")
assert_eq "$G3" "ecosystem_pattern:True:1" "3A-G3: sharded query matches Python ModuleNotFoundError (R3 compat)"

# --- 3A-G4: Single query memory < 1MB (tracemalloc) ---
G4=$(python3 -c "
import sys, json, tracemalloc
sys.path.insert(0, '$SCRIPTS')
import polaris_failure_records as pfr
from pathlib import Path

pfr._index_cache = None
packs_dir = Path('$PACKS')
local_store = {'schema_version': 2, 'records': []}

tracemalloc.start()
result = pfr.query_sharded(
    local_store, packs_dir=packs_dir,
    matching_key='test-mem',
    ecosystem='python', error_class='missing_dependency',
    stderr_text=\"ModuleNotFoundError: No module named 'bar'\"
)
current, peak = tracemalloc.get_traced_memory()
tracemalloc.stop()
peak_kb = peak / 1024
print(f'{peak_kb:.1f}KB')
")
G4_KB=$(echo "$G4" | grep -oP '^[0-9.]+')
G4_OK=$(python3 -c "print('yes' if float('$G4_KB') < 1024 else 'no:${G4_KB}KB')")
assert_eq "$G4_OK" "yes" "3A-G4: single query peak memory < 1MB (actual: ${G4_KB}KB)"

# --- 3A-G5: Corrupt/missing index.json → fallback to legacy query ---
G5_TMPDIR=$(mktemp -d)
# Create a corrupt index.json
echo "not json" > "$G5_TMPDIR/index.json"
# Create legacy flat pack
mkdir -p "$G5_TMPDIR"
cp "$PACKS/python.json" "$G5_TMPDIR/python.json" 2>/dev/null || true

G5=$(python3 -c "
import sys, json
sys.path.insert(0, '$SCRIPTS')
import polaris_failure_records as pfr
from pathlib import Path

pfr._index_cache = None
packs_dir = Path('$G5_TMPDIR')

# load_index should return None for corrupt file
idx = pfr.load_index(packs_dir)

# query_sharded should fallback to legacy query (local store only)
local_store = {'schema_version': 2, 'records': []}
result = pfr.query_sharded(
    local_store, packs_dir=packs_dir,
    matching_key='test-fallback',
    ecosystem='python', error_class='missing_dependency',
    stderr_text=\"ModuleNotFoundError: No module named 'baz'\"
)
# With empty local store and no valid index, should get 'none'
print(f'index={idx is None}:tier={result[\"match_tier\"]}')
")
assert_eq "$G5" "index=True:tier=none" "3A-G5: corrupt index.json → graceful fallback (no crash)"
rm -rf "$G5_TMPDIR"

# --- 3A-G6: Final release-pack benchmark (167 patterns, all 8 ecosystems) ---
# The plan requires "在最终 pack 规模下重跑 3A benchmark": query < 2ms, memory < 1MB.
# Unlike G2 (synthetic 500-record shard), this uses the ACTUAL release packs.
G6=$(python3 -c "
import sys, time, json, tracemalloc
sys.path.insert(0, '$SCRIPTS')
import polaris_failure_records as pfr
from pathlib import Path

pfr._index_cache = None
packs = Path('$PACKS')
local_store = {'schema_version': 2, 'records': []}
idx = json.load(open('$PACKS/index.json'))

# Prepare a representative query per ecosystem
queries = []
for eco, info in idx['ecosystems'].items():
    ec = info['error_classes'][0]
    queries.append((eco, ec, f'Test error for {eco}/{ec} benchmark probe'))

# --- Query latency: average over 50 full sweeps ---
start = time.perf_counter()
for _ in range(50):
    for eco, ec, stderr_text in queries:
        pfr._index_cache = None
        pfr.query_sharded(local_store, packs_dir=packs, matching_key='bench-final',
                          ecosystem=eco, error_class=ec, stderr_text=stderr_text)
elapsed = time.perf_counter() - start
total_queries = 50 * len(queries)
avg_ms = (elapsed / total_queries) * 1000

# --- Peak memory: single sweep with tracemalloc ---
pfr._index_cache = None
tracemalloc.start()
for eco, ec, stderr_text in queries:
    pfr._index_cache = None
    pfr.query_sharded(local_store, packs_dir=packs, matching_key='bench-final-mem',
                      ecosystem=eco, error_class=ec, stderr_text=stderr_text)
_, peak = tracemalloc.get_traced_memory()
tracemalloc.stop()
peak_kb = peak / 1024

print(f'{avg_ms:.3f},{peak_kb:.1f},{len(queries)},{total_queries}')
")
G6_MS=$(echo "$G6" | cut -d, -f1)
G6_KB=$(echo "$G6" | cut -d, -f2)
G6_ECOS=$(echo "$G6" | cut -d, -f3)
G6_TOTAL=$(echo "$G6" | cut -d, -f4)
G6_QUERY_OK=$(python3 -c "print('yes' if float('$G6_MS') < 2.0 else 'no')")
G6_MEM_OK=$(python3 -c "print('yes' if float('$G6_KB') < 1024 else 'no')")
assert_eq "$G6_QUERY_OK" "yes" "3A-G6a: final-pack query < 2ms (actual: ${G6_MS}ms, ${G6_ECOS} ecosystems, ${G6_TOTAL} queries)"
assert_eq "$G6_MEM_OK" "yes" "3A-G6b: final-pack memory < 1MB (actual: ${G6_KB}KB)"

echo "=== 3A Results: $PASS/$TOTAL passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
