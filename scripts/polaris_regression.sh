#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT_BASE="${POLARIS_REGRESSION_OUT:-/tmp/polaris-regression-runs}"
rm -rf "$OUT_BASE" 2>/dev/null || true
mkdir -p "$OUT_BASE"

run_demo() {
  local name="$1" profile="$2" mode="$3" err="$4" kind="${5:-auto}" goal="${6:-Demonstrate Polaris local orchestration flow}" target="${7:-}"
  POLARIS_RUNTIME_DIR="$OUT_BASE/$name" \
  POLARIS_EXECUTION_PROFILE="$profile" \
  POLARIS_MODE="$mode" \
  POLARIS_SIMULATE_ERROR="$err" \
  POLARIS_EXECUTION_KIND="$kind" \
  POLARIS_GOAL="$goal" \
  POLARIS_ANALYSIS_TARGET="$target" \
  bash "$ROOT/scripts/polaris_runtime_demo.sh" >/tmp/polaris-${name}.out
}

run_demo micro-success micro short ''
run_demo runner-success standard short '' runner 'Demonstrate Polaris runner success flow'
run_demo runner-failure standard short 'ModuleNotFoundError: No module named pywinauto' runner 'Demonstrate Polaris runner failure flow'
run_demo standard-success standard short ''
run_demo deep-success deep long ''
run_demo deep-file-transform-success deep long '' file_transform 'Demonstrate Polaris deep file transform flow'
run_demo file-transform-success standard short '' file_transform 'Demonstrate Polaris file transform flow'
run_demo command-output-success standard short '' command_output 'Demonstrate Polaris command output flow'
run_demo command-output-failure standard short 'forced command output failure' command_output 'Demonstrate Polaris command output failure flow'
run_demo standard-repair standard short 'ModuleNotFoundError: No module named pywinauto'
run_demo deep-command-output-repair deep long 'forced command output failure' command_output 'Demonstrate Polaris deep command output repair flow'
run_demo deep-repair deep long 'ModuleNotFoundError: No module named pywinauto'
run_demo boundary-approval standard short 'approval denied by policy'
run_demo boundary-permission standard short 'Permission denied while writing file'

run_demo real-analysis-success standard short '' file_analysis 'Analyze a real Polaris script file' "$ROOT/scripts/polaris_planner.py"

REAL_REPAIR_DIR="$OUT_BASE/real-analysis-failure-repair"
REAL_REPAIR_TARGET="/tmp/polaris-step0-nonexistent-target-$$-$(date +%s).txt"
mkdir -p "$REAL_REPAIR_DIR"
POLARIS_RUNTIME_DIR="$REAL_REPAIR_DIR" \
POLARIS_EXECUTION_PROFILE=standard \
POLARIS_MODE=short \
POLARIS_SIMULATE_ERROR='' \
POLARIS_EXECUTION_KIND=file_analysis \
POLARIS_GOAL='Analyze a file that does not exist yet' \
POLARIS_ANALYSIS_TARGET="$REAL_REPAIR_TARGET" \
bash "$ROOT/scripts/polaris_runtime_demo.sh" >/tmp/polaris-real-analysis-failure-repair-1.out || true
cp "$REAL_REPAIR_DIR/execution-state.json" "$REAL_REPAIR_DIR/execution-state-run1.json"
echo "Step 0 repair target content created after real failure." > "$REAL_REPAIR_TARGET"
POLARIS_RUNTIME_DIR="$REAL_REPAIR_DIR" \
POLARIS_EXECUTION_PROFILE=standard \
POLARIS_MODE=short \
POLARIS_SIMULATE_ERROR='' \
POLARIS_EXECUTION_KIND=file_analysis \
POLARIS_GOAL='Analyze a file that now exists after repair' \
POLARIS_ANALYSIS_TARGET="$REAL_REPAIR_TARGET" \
bash "$ROOT/scripts/polaris_runtime_demo.sh" >/tmp/polaris-real-analysis-failure-repair-2.out
cp "$REAL_REPAIR_DIR/execution-state.json" "$REAL_REPAIR_DIR/execution-state-run2.json"
rm -f "$REAL_REPAIR_TARGET"

STEP2_SUCCESS_DIR="$OUT_BASE/step2-learning-repeat-success"
mkdir -p "$STEP2_SUCCESS_DIR"
POLARIS_RUNTIME_DIR="$STEP2_SUCCESS_DIR" POLARIS_EXECUTION_PROFILE=standard POLARIS_MODE=short POLARIS_SIMULATE_ERROR='' bash "$ROOT/scripts/polaris_runtime_demo.sh" >/tmp/polaris-step2-learning-repeat-success-1.out
cp "$STEP2_SUCCESS_DIR/execution-state.json" "$STEP2_SUCCESS_DIR/execution-state-run1.json"
cp "$STEP2_SUCCESS_DIR/runtime-execution-result.json" "$STEP2_SUCCESS_DIR/runtime-execution-result-run1.json"
cp "$STEP2_SUCCESS_DIR/runtime-validation-result.json" "$STEP2_SUCCESS_DIR/runtime-validation-result-run1.json"
POLARIS_RUNTIME_DIR="$STEP2_SUCCESS_DIR" POLARIS_EXECUTION_PROFILE=standard POLARIS_MODE=short POLARIS_SIMULATE_ERROR='' bash "$ROOT/scripts/polaris_runtime_demo.sh" >/tmp/polaris-step2-learning-repeat-success-2.out
cp "$STEP2_SUCCESS_DIR/execution-state.json" "$STEP2_SUCCESS_DIR/execution-state-run2.json"
cp "$STEP2_SUCCESS_DIR/runtime-execution-result.json" "$STEP2_SUCCESS_DIR/runtime-execution-result-run2.json"
cp "$STEP2_SUCCESS_DIR/runtime-validation-result.json" "$STEP2_SUCCESS_DIR/runtime-validation-result-run2.json"

STEP2_REPAIR_DIR="$OUT_BASE/step2-learning-repeat-repair"
mkdir -p "$STEP2_REPAIR_DIR"
POLARIS_RUNTIME_DIR="$STEP2_REPAIR_DIR" POLARIS_EXECUTION_PROFILE=standard POLARIS_MODE=short POLARIS_SIMULATE_ERROR='forced step2 repair seed failure' bash "$ROOT/scripts/polaris_runtime_demo.sh" >/tmp/polaris-step2-learning-repeat-repair-1.out || true
cp "$STEP2_REPAIR_DIR/execution-state.json" "$STEP2_REPAIR_DIR/execution-state-run1.json"
cp "$STEP2_REPAIR_DIR/runtime-repair-report.json" "$STEP2_REPAIR_DIR/runtime-repair-report-run1.json"
cp "$STEP2_REPAIR_DIR/runtime-repair-plan.json" "$STEP2_REPAIR_DIR/runtime-repair-plan-run1.json"
POLARIS_RUNTIME_DIR="$STEP2_REPAIR_DIR" POLARIS_EXECUTION_PROFILE=standard POLARIS_MODE=short POLARIS_SIMULATE_ERROR='' bash "$ROOT/scripts/polaris_runtime_demo.sh" >/tmp/polaris-step2-learning-repeat-repair-2.out
cp "$STEP2_REPAIR_DIR/execution-state.json" "$STEP2_REPAIR_DIR/execution-state-run2.json"
cp "$STEP2_REPAIR_DIR/runtime-execution-result.json" "$STEP2_REPAIR_DIR/runtime-execution-result-run2.json"
cp "$STEP2_REPAIR_DIR/runtime-validation-result.json" "$STEP2_REPAIR_DIR/runtime-validation-result-run2.json"

run_demo missing-tool-repair standard short 'command not found: polaris-missing-tool' runner 'Demonstrate Polaris missing tool repair flow'

POLARIS_RUNTIME_DIR="$OUT_BASE/deep-resumed-failure" \
POLARIS_EXECUTION_PROFILE=deep \
POLARIS_MODE=long \
POLARIS_EXECUTION_KIND=runner \
POLARIS_SIMULATE_ERROR='ModuleNotFoundError: No module named pywinauto' \
POLARIS_RESUMED_SIMULATE_ERROR='ModuleNotFoundError: No module named pywinauto' \
POLARIS_GOAL='Demonstrate Polaris resumed failure flow' \
bash "$ROOT/scripts/polaris_runtime_demo.sh" >/tmp/polaris-deep-resumed-failure.out || true

STEP3_TRANSFER_SOURCE="$OUT_BASE/step3-transfer-source"
STEP3_TRANSFER_TARGET="$OUT_BASE/step3-transfer-target"
mkdir -p "$STEP3_TRANSFER_SOURCE" "$STEP3_TRANSFER_TARGET"
POLARIS_RUNTIME_DIR="$STEP3_TRANSFER_SOURCE" \
POLARIS_EXECUTION_PROFILE=standard \
POLARIS_MODE=short \
POLARIS_EXECUTION_KIND=runner \
POLARIS_SIMULATE_ERROR='' \
POLARIS_GOAL='Demonstrate Polaris transfer source flow' \
bash "$ROOT/scripts/polaris_runtime_demo.sh" >/tmp/polaris-step3-transfer-source.out
cp "$STEP3_TRANSFER_SOURCE/adapters.json" "$STEP3_TRANSFER_TARGET/adapters.json"
cp "$STEP3_TRANSFER_SOURCE/rules.json" "$STEP3_TRANSFER_TARGET/rules.json"
cp "$STEP3_TRANSFER_SOURCE/success-patterns.json" "$STEP3_TRANSFER_TARGET/success-patterns.json"
POLARIS_RUNTIME_DIR="$STEP3_TRANSFER_TARGET" \
POLARIS_EXECUTION_PROFILE=standard \
POLARIS_MODE=short \
POLARIS_EXECUTION_KIND=runner \
POLARIS_SIMULATE_ERROR='' \
POLARIS_GOAL='Demonstrate Polaris transfer target flow with a different task prompt' \
bash "$ROOT/scripts/polaris_runtime_demo.sh" >/tmp/polaris-step3-transfer-target.out

# ── Phase 1: Real shell-command experience loop scenarios ──

# real-shell-success: shell_command adapter runs echo hello, captures result, pattern recorded
REAL_SHELL_SUCCESS_DIR="$OUT_BASE/real-shell-success"
POLARIS_RUNTIME_DIR="$REAL_SHELL_SUCCESS_DIR" \
POLARIS_EXECUTION_PROFILE=standard \
POLARIS_MODE=short \
POLARIS_EXECUTION_KIND=shell_command \
POLARIS_SIMULATE_ERROR='' \
POLARIS_GOAL='Run echo hello via real shell adapter' \
POLARIS_SHELL_COMMAND='echo hello' \
bash "$ROOT/scripts/polaris_runtime_demo.sh" >/tmp/polaris-real-shell-success.out

# real-shell-failure-classified: shell_command that fails → repair classifies real stderr → failure record written
REAL_SHELL_FAIL_DIR="$OUT_BASE/real-shell-failure-classified"
POLARIS_RUNTIME_DIR="$REAL_SHELL_FAIL_DIR" \
POLARIS_EXECUTION_PROFILE=standard \
POLARIS_MODE=short \
POLARIS_EXECUTION_KIND=shell_command \
POLARIS_SIMULATE_ERROR='' \
POLARIS_GOAL='Run a command that will fail' \
POLARIS_SHELL_COMMAND='cat /nonexistent/path/that/does/not/exist/polaris-test-file.txt' \
bash "$ROOT/scripts/polaris_runtime_demo.sh" >/tmp/polaris-real-shell-failure-classified.out || true

# real-experience-replay: Run 1 succeeds + pattern captured → Run 2 same task, pattern selected
REAL_REPLAY_DIR="$OUT_BASE/real-experience-replay"
POLARIS_RUNTIME_DIR="$REAL_REPLAY_DIR" \
POLARIS_EXECUTION_PROFILE=standard \
POLARIS_MODE=short \
POLARIS_EXECUTION_KIND=shell_command \
POLARIS_SIMULATE_ERROR='' \
POLARIS_GOAL='Run echo replay-test via real shell adapter' \
POLARIS_SHELL_COMMAND='echo replay-test' \
bash "$ROOT/scripts/polaris_runtime_demo.sh" >/tmp/polaris-real-experience-replay-1.out
cp "$REAL_REPLAY_DIR/execution-state.json" "$REAL_REPLAY_DIR/execution-state-run1.json"

# Run 2: same command, fresh state — should pick up pattern from run 1
rm -f "$REAL_REPLAY_DIR/execution-state.json"
POLARIS_RUNTIME_DIR="$REAL_REPLAY_DIR" \
POLARIS_EXECUTION_PROFILE=standard \
POLARIS_MODE=short \
POLARIS_EXECUTION_KIND=shell_command \
POLARIS_SIMULATE_ERROR='' \
POLARIS_GOAL='Run echo replay-test via real shell adapter' \
POLARIS_SHELL_COMMAND='echo replay-test' \
bash "$ROOT/scripts/polaris_runtime_demo.sh" >/tmp/polaris-real-experience-replay-2.out
cp "$REAL_REPLAY_DIR/execution-state.json" "$REAL_REPLAY_DIR/execution-state-run2.json"

# real-experience-avoids-failure: Run 1 fails → failure recorded → Run 2 avoids failure via hints
# The command checks $POLARIS_TEST_TOKEN. Run 1 has no env var → missing_dependency + "required env".
# The avoidance hint sets POLARIS_TEST_TOKEN=polaris-provided → Run 2 succeeds.
REAL_AVOID_DIR="$OUT_BASE/real-experience-avoids-failure"
POLARIS_RUNTIME_DIR="$REAL_AVOID_DIR" \
POLARIS_EXECUTION_PROFILE=standard \
POLARIS_MODE=short \
POLARIS_EXECUTION_KIND=shell_command \
POLARIS_SIMULATE_ERROR='' \
POLARIS_GOAL='Test experience avoidance with env var' \
POLARIS_SHELL_COMMAND='bash -c '"'"'test -n "$POLARIS_TEST_TOKEN" || (echo "required env POLARIS_TEST_TOKEN not set" >&2; exit 1)'"'"'' \
bash "$ROOT/scripts/polaris_runtime_demo.sh" >/tmp/polaris-real-avoid-1.out || true
cp "$REAL_AVOID_DIR/execution-state.json" "$REAL_AVOID_DIR/execution-state-run1.json"

# Run 2: same command, fresh state — avoidance hint sets POLARIS_TEST_TOKEN=polaris-provided
rm -f "$REAL_AVOID_DIR/execution-state.json"
rm -f "$REAL_AVOID_DIR/runtime-execution-result.json"
POLARIS_RUNTIME_DIR="$REAL_AVOID_DIR" \
POLARIS_EXECUTION_PROFILE=standard \
POLARIS_MODE=short \
POLARIS_EXECUTION_KIND=shell_command \
POLARIS_SIMULATE_ERROR='' \
POLARIS_GOAL='Test experience avoidance with env var' \
POLARIS_SHELL_COMMAND='bash -c '"'"'test -n "$POLARIS_TEST_TOKEN" || (echo "required env POLARIS_TEST_TOKEN not set" >&2; exit 1)'"'"'' \
bash "$ROOT/scripts/polaris_runtime_demo.sh" >/tmp/polaris-real-avoid-2.out || true
cp "$REAL_AVOID_DIR/execution-state.json" "$REAL_AVOID_DIR/execution-state-run2.json"

POLARIS_ROOT="$ROOT" python3 - <<'PY' > "$OUT_BASE/step2-strategy-conflict.json"
import json, os, pathlib, sys
sys.path.insert(0, str(pathlib.Path(os.environ['POLARIS_ROOT']) / 'scripts'))
import polaris_orchestrator as po
rules = [
    {
        'rule_id': 'soft-low-fallback',
        'layer': 'soft',
        'priority': 10,
        'validation_count': 1,
        'last_validated_at': '2026-03-14T09:00:00+00:00',
        'strategy_overrides': {'fallback_choice': 'selected-adapter-only', 'retry_policy': 'bounded-repair'},
    },
    {
        'rule_id': 'soft-high-fallback',
        'layer': 'soft',
        'priority': 90,
        'validation_count': 3,
        'last_validated_at': '2026-03-14T09:10:00+00:00',
        'strategy_overrides': {'fallback_choice': 'sticky-adapter-first', 'retry_policy': 'bounded-repair-with-evidence'},
    },
    {
        'rule_id': 'experimental-order-attempt',
        'layer': 'experimental',
        'priority': 99,
        'validation_count': 9,
        'last_validated_at': '2026-03-14T09:20:00+00:00',
        'strategy_overrides': {'execution_ordering': ['should', 'be', 'ignored'], 'validation_strategy': 'runner-contract-strict'},
    },
]
pattern = {
    'pattern_id': 'pattern-ordering-wins',
    'confidence': 80,
    'last_validated_at': '2026-03-14T09:30:00+00:00',
    'strategy_hints': {'execution_ordering': ['precheck', 'execute', 'validate']},
}
strategy = po.build_execution_strategy(rules, pattern, 'standard', 'runner')
print(json.dumps(strategy, indent=2, sort_keys=True))
PY

# ── Resume regression scenarios (Step 3B) ──
# resume-from-blocked: run 1 blocks (standard profile), run 2 resumes with POLARIS_RESUME=1
RESUME_BLOCKED_DIR="$OUT_BASE/resume-from-blocked"
POLARIS_RUNTIME_DIR="$RESUME_BLOCKED_DIR" \
POLARIS_EXECUTION_PROFILE=standard \
POLARIS_MODE=short \
POLARIS_EXECUTION_KIND=runner \
POLARIS_SIMULATE_ERROR='forced resume seed failure' \
POLARIS_GOAL='Demonstrate Polaris resume from blocked' \
bash "$ROOT/scripts/polaris_runtime_demo.sh" >/tmp/polaris-resume-blocked-1.out || true
POLARIS_RUNTIME_DIR="$RESUME_BLOCKED_DIR" \
POLARIS_EXECUTION_PROFILE=standard \
POLARIS_MODE=short \
POLARIS_EXECUTION_KIND=runner \
POLARIS_SIMULATE_ERROR='' \
POLARIS_GOAL='Demonstrate Polaris resume from blocked' \
POLARIS_RESUME=1 \
bash "$ROOT/scripts/polaris_runtime_demo.sh" >/tmp/polaris-resume-blocked-2.out

# resume-no-overwrite-completed: completed run + resume flag → fresh init, not resume
RESUME_COMPLETED_DIR="$OUT_BASE/resume-no-overwrite-completed"
POLARIS_RUNTIME_DIR="$RESUME_COMPLETED_DIR" \
POLARIS_EXECUTION_PROFILE=standard \
POLARIS_MODE=short \
POLARIS_EXECUTION_KIND=runner \
POLARIS_SIMULATE_ERROR='' \
POLARIS_GOAL='Demonstrate Polaris completed run' \
bash "$ROOT/scripts/polaris_runtime_demo.sh" >/tmp/polaris-resume-completed-1.out
POLARIS_RUNTIME_DIR="$RESUME_COMPLETED_DIR" \
POLARIS_EXECUTION_PROFILE=standard \
POLARIS_MODE=short \
POLARIS_EXECUTION_KIND=runner \
POLARIS_SIMULATE_ERROR='' \
POLARIS_GOAL='Demonstrate Polaris completed run' \
POLARIS_RESUME=1 \
bash "$ROOT/scripts/polaris_runtime_demo.sh" >/tmp/polaris-resume-completed-2.out

# ── P1 e2e: nonrepair_stop=true → resume → hard stop ──
RESUME_NONREPAIR_DIR="$OUT_BASE/resume-nonrepair-hardstop"
POLARIS_RUNTIME_DIR="$RESUME_NONREPAIR_DIR" \
POLARIS_EXECUTION_PROFILE=standard \
POLARIS_MODE=short \
POLARIS_EXECUTION_KIND=runner \
POLARIS_SIMULATE_ERROR='approval denied by sandbox policy' \
POLARIS_GOAL='Demonstrate nonrepair hard stop on resume' \
bash "$ROOT/scripts/polaris_runtime_demo.sh" >/tmp/polaris-resume-nonrepair-1.out || true
RESUME_NONREPAIR_EXIT=0
POLARIS_RUNTIME_DIR="$RESUME_NONREPAIR_DIR" \
POLARIS_EXECUTION_PROFILE=standard \
POLARIS_MODE=short \
POLARIS_EXECUTION_KIND=runner \
POLARIS_SIMULATE_ERROR='' \
POLARIS_GOAL='Demonstrate nonrepair hard stop on resume' \
POLARIS_RESUME=1 \
bash "$ROOT/scripts/polaris_runtime_demo.sh" >/tmp/polaris-resume-nonrepair-2.out || RESUME_NONREPAIR_EXIT=$?

# ── P1 e2e: attempted_adapters → resume → adapter exhaustion hard stop ──
# Run 1 blocks normally, then we inject all adapter names into attempted_adapters before resume
RESUME_EXHAUST_DIR="$OUT_BASE/resume-adapter-exhaust"
POLARIS_RUNTIME_DIR="$RESUME_EXHAUST_DIR" \
POLARIS_EXECUTION_PROFILE=standard \
POLARIS_MODE=short \
POLARIS_EXECUTION_KIND=runner \
POLARIS_SIMULATE_ERROR='forced adapter exhaust seed failure' \
POLARIS_GOAL='Demonstrate adapter exhaustion on resume' \
bash "$ROOT/scripts/polaris_runtime_demo.sh" >/tmp/polaris-resume-exhaust-1.out || true
# Inject all adapter names into attempted_adapters to simulate full exhaustion
python3 -c "
import json
state = json.loads(open('$RESUME_EXHAUST_DIR/execution-state.json').read())
registry = json.loads(open('$RESUME_EXHAUST_DIR/adapters.json').read())
all_names = [a['tool'] for a in registry.get('adapters', [])]
state['fallback_state']['attempted_adapters'] = all_names
state['fallback_state']['fallback_count'] = len(all_names)
state['fallback_state']['max_fallback_attempts'] = len(all_names)
open('$RESUME_EXHAUST_DIR/execution-state.json', 'w').write(json.dumps(state, indent=2))
"
RESUME_EXHAUST_EXIT=0
POLARIS_RUNTIME_DIR="$RESUME_EXHAUST_DIR" \
POLARIS_EXECUTION_PROFILE=standard \
POLARIS_MODE=short \
POLARIS_EXECUTION_KIND=runner \
POLARIS_SIMULATE_ERROR='' \
POLARIS_GOAL='Demonstrate adapter exhaustion on resume' \
POLARIS_RESUME=1 \
bash "$ROOT/scripts/polaris_runtime_demo.sh" >/tmp/polaris-resume-exhaust-2.out || RESUME_EXHAUST_EXIT=$?

# resume-refuse-in-progress: create in_progress state → orchestrator should refuse
RESUME_INPROGRESS_DIR="$OUT_BASE/resume-refuse-in-progress"
mkdir -p "$RESUME_INPROGRESS_DIR"
python3 -c "
import json
state = {'schema_version': 6, 'status': 'in_progress', 'state_machine': {'node': 'executing'}, 'compat': {'upgraded_from': None, 'upgraded_at': None, 'runtime_format': 1, 'resumed_count': 0}}
open('$RESUME_INPROGRESS_DIR/execution-state.json', 'w').write(json.dumps(state, indent=2))
"
python3 "$ROOT/scripts/polaris_compat.py" write-runtime-format --runtime-dir "$RESUME_INPROGRESS_DIR"
RESUME_INPROGRESS_EXIT=0
POLARIS_RUNTIME_DIR="$RESUME_INPROGRESS_DIR" \
POLARIS_EXECUTION_PROFILE=standard \
POLARIS_MODE=short \
POLARIS_EXECUTION_KIND=runner \
POLARIS_SIMULATE_ERROR='' \
POLARIS_GOAL='Should refuse' \
bash "$ROOT/scripts/polaris_runtime_demo.sh" >/tmp/polaris-resume-inprogress.out 2>&1 || RESUME_INPROGRESS_EXIT=$?

# ── Bootstrap regression scenarios (Step 4A) ──
# 4A idempotency: run bootstrap twice on the same dir → second should skip
BOOTSTRAP_IDEM_DIR="$OUT_BASE/bootstrap-idempotency"
mkdir -p "$BOOTSTRAP_IDEM_DIR"
python3 "$ROOT/scripts/polaris_compat.py" write-runtime-format --runtime-dir "$BOOTSTRAP_IDEM_DIR"
python3 "$ROOT/scripts/polaris_bootstrap.py" bootstrap --manifest "$ROOT/scripts/polaris_bootstrap.json" --runtime-dir "$BOOTSTRAP_IDEM_DIR" >/dev/null
python3 "$ROOT/scripts/polaris_bootstrap.py" bootstrap --manifest "$ROOT/scripts/polaris_bootstrap.json" --runtime-dir "$BOOTSTRAP_IDEM_DIR" > "$BOOTSTRAP_IDEM_DIR/bootstrap-run2.json"

# 4A requirement failure: bad interpreter
BOOTSTRAP_FAIL_DIR="$OUT_BASE/bootstrap-req-failure"
mkdir -p "$BOOTSTRAP_FAIL_DIR"
python3 -c "
import json
manifest = json.load(open('$ROOT/scripts/polaris_bootstrap.json'))
manifest['requires']['interpreter'] = 'nonexistent-binary-xyz'
open('$BOOTSTRAP_FAIL_DIR/bad-manifest.json', 'w').write(json.dumps(manifest))
"
BOOTSTRAP_FAIL_EXIT=0
python3 "$ROOT/scripts/polaris_bootstrap.py" bootstrap --manifest "$BOOTSTRAP_FAIL_DIR/bad-manifest.json" --runtime-dir "$BOOTSTRAP_FAIL_DIR" >/dev/null 2>&1 || BOOTSTRAP_FAIL_EXIT=$?

# 4A capability probe failure: unknown capability
BOOTSTRAP_CAP_DIR="$OUT_BASE/bootstrap-cap-failure"
mkdir -p "$BOOTSTRAP_CAP_DIR"
python3 -c "
import json
manifest = json.load(open('$ROOT/scripts/polaris_bootstrap.json'))
manifest['requires']['capabilities'] = ['nonexistent-capability']
open('$BOOTSTRAP_CAP_DIR/bad-cap-manifest.json', 'w').write(json.dumps(manifest))
"
BOOTSTRAP_CAP_EXIT=0
python3 "$ROOT/scripts/polaris_bootstrap.py" bootstrap --manifest "$BOOTSTRAP_CAP_DIR/bad-cap-manifest.json" --runtime-dir "$BOOTSTRAP_CAP_DIR" >/dev/null 2>&1 || BOOTSTRAP_CAP_EXIT=$?

# 4A real probe failure: interpreter exists but local-exec probe fails (false always exits 1)
BOOTSTRAP_PROBE_DIR="$OUT_BASE/bootstrap-probe-failure"
mkdir -p "$BOOTSTRAP_PROBE_DIR"
python3 -c "
import json
manifest = json.load(open('$ROOT/scripts/polaris_bootstrap.json'))
manifest['requires']['interpreter'] = 'false'
manifest['requires']['capabilities'] = ['local-exec']
open('$BOOTSTRAP_PROBE_DIR/probe-fail-manifest.json', 'w').write(json.dumps(manifest))
"
BOOTSTRAP_PROBE_EXIT=0
python3 "$ROOT/scripts/polaris_bootstrap.py" bootstrap --manifest "$BOOTSTRAP_PROBE_DIR/probe-fail-manifest.json" --runtime-dir "$BOOTSTRAP_PROBE_DIR" >/dev/null 2>&1 || BOOTSTRAP_PROBE_EXIT=$?

# ── Step 4B regression scenarios: Experience asset versioning ──
# 4b-pattern-migration: create v1 patterns (no asset_version) → load → assert migrated
PATTERN_MIG_DIR="$OUT_BASE/4b-pattern-migration"
mkdir -p "$PATTERN_MIG_DIR"
python3 -c "
import json
store = {'schema_version': 1, 'patterns': [
    {'pattern_id': 'v1-test', 'summary': 'v1 test pattern', 'trigger': 'test', 'sequence': ['a','b'], 'outcome': 'pass', 'evidence': ['e1'], 'tags': ['test'], 'modes': ['long'], 'confidence': 70, 'lifecycle_state': 'experimental', 'fingerprint': 'v1-test', 'adapter': None, 'promotion_count': 0, 'demotion_count': 0, 'selection_count': 0, 'reusable': True, 'strategy_hints': {}, 'expires_at': None, 'created_at': '2026-01-01T00:00:00+00:00', 'updated_at': '2026-01-01T00:00:00+00:00', 'last_validated_at': '2026-01-01T00:00:00+00:00', 'validation_count': 1, 'evidence_count': 1}
]}
open('$PATTERN_MIG_DIR/success-patterns.json', 'w').write(json.dumps(store, indent=2))
"
# Capture a new pattern into the same store → should have asset_version: 2
python3 "$ROOT/scripts/polaris_success_patterns.py" capture \
  --patterns "$PATTERN_MIG_DIR/success-patterns.json" \
  --pattern-id "v2-test" --summary "v2 test" --trigger "test" \
  --sequence "a,b" --outcome "pass" --evidence "e2" --tags "test" > /dev/null

# 4b-pattern-merge-upgrade: v1 pattern (no asset_version) → capture same-id → merged must be asset_version: 2
PATTERN_MERGE_DIR="$OUT_BASE/4b-pattern-merge-upgrade"
mkdir -p "$PATTERN_MERGE_DIR"
python3 -c "
import json
store = {'schema_version': 1, 'patterns': [
    {'pattern_id': 'merge-target', 'summary': 'old pattern', 'trigger': 'test', 'sequence': ['a','b'], 'outcome': 'pass', 'evidence': ['e1'], 'tags': ['test'], 'modes': ['long'], 'confidence': 70, 'lifecycle_state': 'experimental', 'fingerprint': 'merge-target', 'adapter': None, 'promotion_count': 0, 'demotion_count': 0, 'selection_count': 0, 'reusable': True, 'strategy_hints': {}, 'expires_at': None, 'created_at': '2026-01-01T00:00:00+00:00', 'updated_at': '2026-01-01T00:00:00+00:00', 'last_validated_at': '2026-01-01T00:00:00+00:00', 'validation_count': 1, 'evidence_count': 1}
]}
open('$PATTERN_MERGE_DIR/success-patterns.json', 'w').write(json.dumps(store, indent=2))
"
# Capture same pattern_id → triggers merge_pattern(existing=v1, incoming=v2)
python3 "$ROOT/scripts/polaris_success_patterns.py" capture \
  --patterns "$PATTERN_MERGE_DIR/success-patterns.json" \
  --pattern-id "merge-target" --summary "updated pattern" --trigger "test" \
  --sequence "a,b" --outcome "pass" --evidence "e2" --tags "test" > /dev/null
# Also test consolidate-marker merge path
PATTERN_CONSOL_DIR="$OUT_BASE/4b-pattern-consolidate-merge"
mkdir -p "$PATTERN_CONSOL_DIR"
python3 -c "
import json
store = {'schema_version': 1, 'patterns': [
    {'pattern_id': 'consol-target', 'summary': 'old pattern', 'trigger': 'test', 'sequence': ['a','b'], 'outcome': 'pass', 'evidence': ['e1'], 'tags': ['test'], 'modes': ['long'], 'confidence': 70, 'lifecycle_state': 'experimental', 'fingerprint': 'consol-target', 'adapter': None, 'promotion_count': 0, 'demotion_count': 0, 'selection_count': 0, 'reusable': True, 'strategy_hints': {}, 'expires_at': None, 'created_at': '2026-01-01T00:00:00+00:00', 'updated_at': '2026-01-01T00:00:00+00:00', 'last_validated_at': '2026-01-01T00:00:00+00:00', 'validation_count': 1, 'evidence_count': 1}
]}
open('$PATTERN_CONSOL_DIR/success-patterns.json', 'w').write(json.dumps(store, indent=2))
"
python3 "$ROOT/scripts/polaris_success_patterns.py" consolidate-marker \
  --patterns "$PATTERN_CONSOL_DIR/success-patterns.json" \
  --marker '{"pattern_id":"consol-target","summary":"consolidated","trigger":"test","sequence":["a","b"],"outcome":"pass","evidence":["e2"],"tags":["test"],"modes":["long"],"confidence":72}' > /dev/null

# 4b-rule-migration: create v1 rules (no asset_version) → load → assert migrated
RULE_MIG_DIR="$OUT_BASE/4b-rule-migration"
mkdir -p "$RULE_MIG_DIR"
python3 -c "
import json
store = {'schema_version': 3, 'rules': [
    {'rule_id': 'v1-rule', 'layer': 'soft', 'trigger': 'test', 'action': 'do thing', 'evidence': 'e1', 'scope': 'local', 'fingerprint': 'v1-rule', 'tags': ['test'], 'validation': 'observed', 'priority': 50, 'strategy_overrides': {}, 'evidence_count': 1, 'validation_count': 1, 'last_validated_at': '2026-01-01T00:00:00+00:00', 'created_at': '2026-01-01T00:00:00+00:00'}
]}
open('$RULE_MIG_DIR/rules.json', 'w').write(json.dumps(store, indent=2))
"
# Add a new rule → should have asset_version: 2
python3 "$ROOT/scripts/polaris_rules.py" add \
  --rules "$RULE_MIG_DIR/rules.json" \
  --rule-id "v2-rule" --layer soft --trigger "test2" --action "do other" \
  --evidence "e2" --scope "local" --tags "test" > /dev/null

# 4b-backlog-migration: create state with v1 backlog items (no asset_version) → load → assert migrated
BACKLOG_MIG_DIR="$OUT_BASE/4b-backlog-migration"
mkdir -p "$BACKLOG_MIG_DIR"
python3 -c "
import json
state = {
    'schema_version': 6, 'run_id': 'test', 'goal': 'test', 'mode': 'long',
    'execution_profile': 'deep', 'status': 'completed', 'phase': 'completed',
    'learning_backlog': [
        {'queued_at': '2026-01-01T00:00:00+00:00', 'kind': 'success_marker', 'payload': {'pattern_id': 'test'}},
        {'queued_at': '2026-01-01T00:00:00+00:00', 'kind': 'rule_candidate', 'payload': {'rule_id': 'test'}}
    ],
    'compat': {'upgraded_from': None, 'upgraded_at': None, 'runtime_format': 1, 'resumed_count': 0}
}
open('$BACKLOG_MIG_DIR/execution-state.json', 'w').write(json.dumps(state, indent=2))
"
python3 "$ROOT/scripts/polaris_compat.py" write-runtime-format --runtime-dir "$BACKLOG_MIG_DIR"

# ── Step 5A regression scenarios: Cross-version state evidence ──
# coexist-v5-dir-full-run: v5 state + no runtime-format.json → full polaris_runtime_demo.sh
COEXIST_V5_DIR="$OUT_BASE/coexist-v5-dir-full-run"
mkdir -p "$COEXIST_V5_DIR"
POLARIS_ROOT="$ROOT" python3 -c "
import os, sys, pathlib
sys.path.insert(0, str(pathlib.Path(os.environ['POLARIS_ROOT']) / 'scripts'))
import polaris_v5_snapshot as v5
state = v5.v5_default_state()
state['run_id'] = 'v5-coexist-test'
state['goal'] = 'v5 coexistence test'
state['status'] = 'completed'
v5.v5_write_json(pathlib.Path('$COEXIST_V5_DIR/execution-state.json'), state)
"
# No runtime-format.json — legacy gate should fire
POLARIS_RUNTIME_DIR="$COEXIST_V5_DIR" \
POLARIS_EXECUTION_PROFILE=standard \
POLARIS_MODE=short \
POLARIS_EXECUTION_KIND=runner \
POLARIS_SIMULATE_ERROR='' \
POLARIS_GOAL='Run on v5 dir' \
bash "$ROOT/scripts/polaris_runtime_demo.sh" >/tmp/polaris-coexist-v5.out

POLARIS_REGRESSION_OUT_DIR="$OUT_BASE" POLARIS_ROOT="$ROOT" RESUME_INPROGRESS_EXIT="$RESUME_INPROGRESS_EXIT" BOOTSTRAP_FAIL_EXIT="$BOOTSTRAP_FAIL_EXIT" BOOTSTRAP_CAP_EXIT="$BOOTSTRAP_CAP_EXIT" BOOTSTRAP_PROBE_EXIT="$BOOTSTRAP_PROBE_EXIT" python3 - <<'PY'
import json, os, pathlib, sys
base=pathlib.Path(os.environ['POLARIS_REGRESSION_OUT_DIR'])
summary={}
errors=[]

def load_efficiency_metrics(directory):
    state = json.loads((directory/'execution-state.json').read_text())
    artifact_payload = state.get('artifacts', {}).get('efficiency_metrics')
    artifact_file = directory/'runtime-efficiency-metrics.json'
    if not artifact_file.exists():
        errors.append(f"{directory.name}: missing runtime-efficiency-metrics.json")
        return state, None
    file_payload = json.loads(artifact_file.read_text())
    if artifact_payload != file_payload:
        errors.append(f"{directory.name}: inline efficiency_metrics artifact does not match runtime-efficiency-metrics.json")
    return state, file_payload

def assert_efficiency_budget(case_name, state, metrics, contract):
    if metrics is None:
        return
    runtime_metrics = state.get('runtime', {}).get('metrics', {})
    validator = contract.get('validator', {})
    allowed_benefits = {
        'bounded local execution',
        'lower hot-path cost with stricter validation replay',
    }
    for key in ['state_write_count', 'learning_hot_path_ops']:
        if key not in runtime_metrics:
            errors.append(f"{case_name}: runtime.metrics missing {key}")
    if metrics.get('budget_profile') != state.get('execution_profile'):
        errors.append(f"{case_name}: efficiency_metrics budget_profile should match execution_profile")
    if runtime_metrics.get('state_write_count') != metrics.get('state_write_count'):
        errors.append(f"{case_name}: runtime.metrics.state_write_count should match efficiency_metrics.state_write_count")
    if runtime_metrics.get('learning_hot_path_ops') != metrics.get('learning_hot_path_ops'):
        errors.append(f"{case_name}: runtime.metrics.learning_hot_path_ops should match efficiency_metrics.learning_hot_path_ops")
    if metrics.get('state_write_count', 0) > validator.get('max_state_writes', 0):
        errors.append(f"{case_name}: state_write_count exceeded max_state_writes")
    if metrics.get('learning_hot_path_ops', 0) > validator.get('max_learning_hot_path_ops', 0):
        errors.append(f"{case_name}: learning_hot_path_ops exceeded max_learning_hot_path_ops")
    if metrics.get('repair_probe_steps', 0) > validator.get('max_repair_probe_steps', 0):
        errors.append(f"{case_name}: repair_probe_steps exceeded max_repair_probe_steps")
    if metrics.get('selection_inputs', 0) > validator.get('max_selection_inputs', 0):
        errors.append(f"{case_name}: selection_inputs exceeded max_selection_inputs")
    if metrics.get('retry_actions', 0) > validator.get('max_retry_actions', 0):
        errors.append(f"{case_name}: retry_actions exceeded max_retry_actions")
    if metrics.get('stage_count', 0) > validator.get('max_stage_count', 0):
        errors.append(f"{case_name}: stage_count exceeded max_stage_count")
    if metrics.get('cold_path_cost') != len(state.get('learning_backlog', [])):
        errors.append(f"{case_name}: cold_path_cost should match learning_backlog size")
    if metrics.get('expected_benefit') not in allowed_benefits:
        errors.append(f"{case_name}: expected_benefit is not in the allowed accountability set")
    expected_benefit = 'lower hot-path cost with stricter validation replay' if (
        metrics.get('family_transfer_applied') or
        contract.get('strategy', {}).get('validation_strategy') == 'runner-contract-strict'
    ) else 'bounded local execution'
    if metrics.get('expected_benefit') != expected_benefit:
        errors.append(f"{case_name}: expected_benefit does not match contract-derived efficiency semantics")
expected={
    'runner-success': {'status': 'completed', 'execution_kind': 'runner'},
    'runner-failure': {'status': 'blocked', 'execution_kind': 'runner'},
    'standard-success': {'status': 'completed', 'execution_kind': 'runner'},
    'deep-success': {'status': 'completed', 'execution_kind': 'runner'},
    'file-transform-success': {'status': 'completed', 'execution_kind': 'file_transform'},
    'deep-file-transform-success': {'status': 'completed', 'execution_kind': 'file_transform'},
    'command-output-success': {'status': 'completed', 'execution_kind': 'command_output'},
    'command-output-failure': {'status': 'blocked', 'execution_kind': 'command_output'},
    'missing-tool-repair': {'status': 'blocked', 'execution_kind': 'runner'},
    'standard-repair': {'status': 'blocked', 'execution_kind': 'runner'},
    'deep-command-output-repair': {'status': 'completed', 'execution_kind': 'command_output'},
    'deep-repair': {'status': 'completed', 'execution_kind': 'runner'},
    'deep-resumed-failure': {'status': 'blocked', 'execution_kind': 'runner'},
    'boundary-approval': {'status': 'blocked', 'execution_kind': 'runner'},
    'boundary-permission': {'status': 'blocked', 'execution_kind': 'runner'},
    'step2-learning-repeat-success': {'status': 'completed', 'execution_kind': 'runner'},
    'step2-learning-repeat-repair': {'status': 'completed', 'execution_kind': 'runner'},
    'step3-transfer-source': {'status': 'completed', 'execution_kind': 'runner'},
    'step3-transfer-target': {'status': 'completed', 'execution_kind': 'runner'},
    'real-analysis-success': {'status': 'completed', 'execution_kind': 'file_analysis'},
    'real-analysis-failure-repair': {'status': 'completed', 'execution_kind': 'file_analysis'},
    'coexist-v5-dir-full-run': {'status': 'completed', 'execution_kind': 'runner'},
}
for d in sorted(base.iterdir()):
    if not d.is_dir():
        continue
    if not (d/'execution-state.json').exists():
        continue
    state=json.loads((d/'execution-state.json').read_text())
    artifacts=state.get('artifacts', {})
    summary[d.name]={
        'status': state.get('status'),
        'phase': state.get('phase'),
        'execution_kind': artifacts.get('execution_kind'),
        'selected_adapter': artifacts.get('selected_adapter'),
        'next_action': state.get('next_action'),
        'learning_summary': artifacts.get('learning_summary'),
        'applied_rules': [r.get('rule_id') for r in state.get('rule_context', {}).get('applied_rules', [])],
    }
    if d.name in expected:
        exp=expected[d.name]
        if state.get('status') != exp['status']:
            errors.append(f"{d.name}: expected status {exp['status']} got {state.get('status')}")
        if artifacts.get('execution_kind') != exp['execution_kind']:
            errors.append(f"{d.name}: expected execution_kind {exp['execution_kind']} got {artifacts.get('execution_kind')}")
    if d.name == 'command-output-success':
        actual_ptr = artifacts.get('execution_result')
        expected_ptr = str((d/'runtime-command-output.txt').resolve())
        if actual_ptr != expected_ptr:
            errors.append('command-output-success: execution_result does not point to runtime-command-output.txt')
    if d.name == 'command-output-failure':
        vr=json.loads((d/'runtime-validation-result.json').read_text())
        if vr.get('validator_kind') != 'command_output_result':
            errors.append('command-output-failure: wrong validator kind')
    if d.name == 'missing-tool-repair':
        repair_report=json.loads((d/'runtime-repair-report.json').read_text())
        if repair_report.get('failure_type') != 'missing_tool':
            errors.append('missing-tool-repair: repair report should classify failure_type as missing_tool')
    if d.name == 'deep-resumed-failure':
        if artifacts.get('resumed_executor_result') != 'runtime-resumed-executor-result.json':
            errors.append('deep-resumed-failure: missing resumed executor artifact pointer')
        if artifacts.get('resumed_validation_result') != 'runtime-resumed-validation-result.json':
            errors.append('deep-resumed-failure: missing resumed validation artifact pointer')
        efficiency = artifacts.get('efficiency_metrics')
        if not efficiency or efficiency.get('retry_actions') != 1:
            errors.append('deep-resumed-failure: efficiency_metrics should record one retry action after resumed failure')
    if d.name == 'deep-command-output-repair':
        resumed=artifacts.get('resumed_execution_contract', {})
        if resumed.get('kind') != 'command_output':
            errors.append('deep-command-output-repair: resumed contract did not stay on command_output family')
        if artifacts.get('resumed_executor_result') != 'runtime-resumed-executor-result.json':
            errors.append('deep-command-output-repair: missing resumed_executor_result artifact pointer')
        if artifacts.get('resumed_validation_result') != 'runtime-resumed-validation-result.json':
            errors.append('deep-command-output-repair: missing resumed_validation_result artifact pointer')
        vr=json.loads((d/'runtime-resumed-validation-result.json').read_text())
        if vr.get('validator_kind') != 'command_output_result':
            errors.append('deep-command-output-repair: resumed validator kind is not command_output_result')
    if d.name == 'boundary-permission':
        plan=json.loads((d/'runtime-repair-plan.json').read_text())
        if plan.get('safe_to_execute'):
            errors.append('boundary-permission: repair plan should not be safe to execute')
        if plan.get('execution_order'):
            errors.append('boundary-permission: repair plan should have empty execution_order')

success_dir = base/'step2-learning-repeat-success'
run1_state=json.loads((success_dir/'execution-state-run1.json').read_text())
run2_state=json.loads((success_dir/'execution-state-run2.json').read_text())
run1_output=json.loads((success_dir/'runtime-execution-result-run1.json').read_text())
run2_output=json.loads((success_dir/'runtime-execution-result-run2.json').read_text())
run2_validation=json.loads((success_dir/'runtime-validation-result-run2.json').read_text())
run1_contract=run1_state['artifacts']['execution_contract']
run2_contract=run2_state['artifacts']['execution_contract']
run2_validator=run2_contract.get('validator', {})
if run1_state.get('status') != 'completed' or run2_state.get('status') != 'completed':
    errors.append('step2-learning-repeat-success: both runs must complete')
if run1_state['artifacts'].get('selected_pattern'):
    errors.append('step2-learning-repeat-success: first run should not have a selected pattern')
if not run2_state['artifacts'].get('selected_pattern'):
    errors.append('step2-learning-repeat-success: second run should select learned success pattern')
if run1_contract.get('strategy', {}).get('validation_strategy') != 'runner-contract-match':
    errors.append('step2-learning-repeat-success: first run should use runner-contract-match')
if run2_contract.get('strategy', {}).get('validation_strategy') != 'runner-contract-strict':
    errors.append('step2-learning-repeat-success: second run should use runner-contract-strict')
if [item.get('step') for item in run1_output.get('stage_results', [])] != ['select-adapter', 'execute', 'validate']:
    errors.append('step2-learning-repeat-success: first run should execute baseline select-adapter/execute/validate stages')
if [item.get('step') for item in run2_output.get('stage_results', [])] != ['execute', 'validate']:
    errors.append('step2-learning-repeat-success: second run should execute learned direct stage ordering')
if len(run2_output.get('stage_results', [])) >= len(run1_output.get('stage_results', [])):
    errors.append('step2-learning-repeat-success: second run should reduce stage count relative to baseline')
run2_efficiency = json.loads((success_dir/'runtime-efficiency-metrics.json').read_text())
if run2_validator.get('baseline_stage_count') != 3 or run2_validator.get('max_stage_count') != 3 or run2_validator.get('max_stage_growth') != 0:
    errors.append('step2-learning-repeat-success: validator should persist explicit hot-path stage budget fields')
if run2_validator.get('max_retry_actions') != 0 or run2_validator.get('observed_selection_inputs') != 2 or run2_validator.get('max_selection_inputs') != 4 or run2_validator.get('budget_profile') != 'standard':
    errors.append('step2-learning-repeat-success: validator should persist explicit retry/selection/profile budget fields')
if not run2_state['artifacts'].get('execution_contract_diff', {}):
    errors.append('step2-learning-repeat-success: second run should persist non-empty contract diff')
if not run2_state['artifacts'].get('validator_diff', {}):
    errors.append('step2-learning-repeat-success: second run should persist non-empty validator diff')
if run2_validation.get('status') != 'ok':
    errors.append('step2-learning-repeat-success: second run validator should pass')
if run2_state['artifacts'].get('resumed_executor_result') or run2_state['artifacts'].get('resumed_validation_result'):
    errors.append('step2-learning-repeat-success: learned success replay should not add repair re-execution to the hot path')
if run2_efficiency.get('adapter_selection_cost', 999) >= 2:
    errors.append('step2-learning-repeat-success: second run should lower adapter_selection_cost relative to baseline')
if run2_efficiency.get('validator_directness_rank', -1) <= 1:
    errors.append('step2-learning-repeat-success: second run should improve validator_directness_rank relative to baseline')
if run2_efficiency.get('retry_actions', 999) != 0:
    errors.append('step2-learning-repeat-success: second run should keep retry_actions at zero on the hot path')
if run2_efficiency.get('repair_probe_steps', 999) != 0:
    errors.append('step2-learning-repeat-success: second run should keep repair_probe_steps off the hot path')

repair_dir = base/'step2-learning-repeat-repair'
repair_run1_state=json.loads((repair_dir/'execution-state-run1.json').read_text())
repair_run2_state=json.loads((repair_dir/'execution-state-run2.json').read_text())
repair_run1_report=json.loads((repair_dir/'runtime-repair-report-run1.json').read_text())
repair_run2_output=json.loads((repair_dir/'runtime-execution-result-run2.json').read_text())
repair_run2_contract=repair_run2_state['artifacts']['execution_contract']
repair_run2_validator=repair_run2_contract.get('validator', {})
repair_run2_validation=json.loads((repair_dir/'runtime-validation-result-run2.json').read_text())
repair_diff=repair_run2_state['artifacts'].get('execution_contract_diff', {})
if repair_run1_state.get('status') != 'blocked':
    errors.append('step2-learning-repeat-repair: first run should block on seeded failure')
if repair_run1_report.get('failure_type') != 'unknown':
    errors.append('step2-learning-repeat-repair: seeded failure should classify as unknown for generic repair evidence')
if repair_run2_state.get('status') != 'completed':
    errors.append('step2-learning-repeat-repair: second run should complete')
if not str(repair_run2_state['artifacts'].get('selected_pattern', '')).startswith('repair-pattern-'):
    errors.append('step2-learning-repeat-repair: second run should select repair-derived pattern')
if 'applied_rule_ids' not in repair_diff or len(repair_diff['applied_rule_ids']['after']) <= len(repair_diff['applied_rule_ids']['before']):
    errors.append('step2-learning-repeat-repair: repair-derived rule should change applied_rule_ids')
if not repair_run2_contract.get('strategy', {}).get('strategy_trace', {}).get('soft_rules'):
    errors.append('step2-learning-repeat-repair: repair-derived rule should enter strategy trace as a soft rule')
if [item.get('step') for item in repair_run2_output.get('stage_results', [])] != ['diagnose', 'generic-probes', 'record-evidence', 'recover']:
    errors.append('step2-learning-repeat-repair: repair replay should execute repair-derived stage ordering')
if repair_run2_validator.get('baseline_stage_count') != 3 or repair_run2_validator.get('max_stage_count') != 4 or repair_run2_validator.get('max_stage_growth') != 1:
    errors.append('step2-learning-repeat-repair: validator should persist explicit hot-path stage budget fields')
if repair_run2_validator.get('max_retry_actions') != 0 or repair_run2_validator.get('observed_selection_inputs') != 3 or repair_run2_validator.get('max_selection_inputs') != 4 or repair_run2_validator.get('budget_profile') != 'standard':
    errors.append('step2-learning-repeat-repair: validator should persist explicit retry/selection/profile budget fields')
if repair_run2_validation.get('status') != 'ok':
    errors.append('step2-learning-repeat-repair: second run validator should pass')
if repair_run2_state['artifacts'].get('resumed_executor_result') or repair_run2_state['artifacts'].get('resumed_validation_result'):
    errors.append('step2-learning-repeat-repair: repair-derived learning replay should still use a single execute/validate pass on the next run')

for case_name in ['micro-success', 'standard-success', 'deep-success']:
    case_dir = base/case_name
    case_state, case_efficiency = load_efficiency_metrics(case_dir)
    case_contract = case_state['artifacts']['execution_contract']
    assert_efficiency_budget(case_name, case_state, case_efficiency, case_contract)

success_run2_state_full, success_run2_efficiency = load_efficiency_metrics(success_dir)
repair_run2_state_full, repair_run2_efficiency = load_efficiency_metrics(repair_dir)
assert_efficiency_budget('step2-learning-repeat-success', success_run2_state_full, success_run2_efficiency, run2_contract)
assert_efficiency_budget('step2-learning-repeat-repair', repair_run2_state_full, repair_run2_efficiency, repair_run2_contract)

transfer_source_dir = base/'step3-transfer-source'
transfer_target_dir = base/'step3-transfer-target'
transfer_source_state, transfer_source_efficiency = load_efficiency_metrics(transfer_source_dir)
transfer_target_state, transfer_target_efficiency = load_efficiency_metrics(transfer_target_dir)
transfer_source_contract = transfer_source_state['artifacts']['execution_contract']
transfer_target_contract = transfer_target_state['artifacts']['execution_contract']
assert_efficiency_budget('step3-transfer-source', transfer_source_state, transfer_source_efficiency, transfer_source_contract)
assert_efficiency_budget('step3-transfer-target', transfer_target_state, transfer_target_efficiency, transfer_target_contract)
if transfer_source_state.get('goal') == transfer_target_state.get('goal'):
    errors.append('step3-transfer: source and target goals must differ to prove cross-task transfer')
if transfer_target_state['artifacts'].get('family_transfer_applied', False) is not True:
    errors.append('step3-transfer: target should record family_transfer_applied=true')
if not transfer_target_state['artifacts'].get('transfer_source_pattern'):
    errors.append('step3-transfer: target should record transfer_source_pattern')
if not transfer_target_state['artifacts'].get('transfer_reason'):
    errors.append('step3-transfer: target should record transfer_reason')
if not transfer_target_state['artifacts'].get('transfer_contract_diff', {}):
    errors.append('step3-transfer: target should record non-empty transfer_contract_diff')
if transfer_target_state['artifacts'].get('selected_pattern') != transfer_target_state['artifacts'].get('transfer_source_pattern'):
    errors.append('step3-transfer: target selected_pattern should match transfer_source_pattern')
if transfer_target_efficiency and transfer_source_efficiency:
    if transfer_target_efficiency.get('stage_count', 999) >= transfer_source_efficiency.get('stage_count', 999):
        errors.append('step3-transfer: target should reduce stage_count relative to transfer source')
    if transfer_target_efficiency.get('adapter_selection_cost', 999) >= transfer_source_efficiency.get('adapter_selection_cost', 999):
        errors.append('step3-transfer: target should reduce adapter_selection_cost relative to transfer source')
    if transfer_target_efficiency.get('validator_directness_rank', -1) <= transfer_source_efficiency.get('validator_directness_rank', -1):
        errors.append('step3-transfer: target should improve validator directness rank relative to transfer source')

import copy
import hashlib as _hashlib
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(os.environ['POLARIS_ROOT']) / 'scripts'))
import polaris_validator as pv

real_success_dir = base/'real-analysis-success'
real_success_state = json.loads((real_success_dir/'execution-state.json').read_text())
real_success_artifacts = real_success_state.get('artifacts', {})
if real_success_state.get('status') != 'completed':
    errors.append('step0-real-analysis-success: run must complete')
if real_success_artifacts.get('execution_kind') != 'file_analysis':
    errors.append('step0-real-analysis-success: execution_kind must be file_analysis')
real_validation = json.loads((real_success_dir/'runtime-validation-result.json').read_text())
if real_validation.get('validator_kind') != 'independent_file_analysis':
    errors.append('step0-real-analysis-success: validator_kind must be independent_file_analysis')
if real_validation.get('status') != 'ok':
    errors.append('step0-real-analysis-success: independent validation must pass')
verified_fields = real_validation.get('verified_fields', [])
for required_field in ['sha256_bytes', 'line_count', 'word_count', 'char_count', 'size_bytes']:
    if required_field not in verified_fields:
        errors.append(f'step0-real-analysis-success: validator must independently verify {required_field}')
real_analysis_output = json.loads((real_success_dir/'runtime-analysis-result.json').read_text())
if not real_analysis_output.get('sha256_bytes') or len(real_analysis_output['sha256_bytes']) != 64:
    errors.append('step0-real-analysis-success: adapter must compute a real raw-bytes sha256 hash')
if real_analysis_output.get('line_count', -1) < 1:
    errors.append('step0-real-analysis-success: adapter must compute a real line count from a real file')

real_repair_dir = base/'real-analysis-failure-repair'
real_repair_run1 = json.loads((real_repair_dir/'execution-state-run1.json').read_text())
real_repair_run2 = json.loads((real_repair_dir/'execution-state-run2.json').read_text())
if real_repair_run1.get('status') != 'blocked':
    errors.append('step0-real-analysis-failure-repair: run 1 must block on real missing file')
repair_report_path = real_repair_dir/'runtime-repair-report.json'
if repair_report_path.exists():
    real_repair_report = json.loads(repair_report_path.read_text())
    if real_repair_report.get('failure_type') != 'path_or_missing_file':
        errors.append('step0-real-analysis-failure-repair: repair must classify real error as path_or_missing_file')
else:
    errors.append('step0-real-analysis-failure-repair: run 1 must produce a repair report')
if real_repair_run2.get('status') != 'completed':
    errors.append('step0-real-analysis-failure-repair: run 2 must complete after file is created')
if real_repair_run2.get('artifacts', {}).get('execution_kind') != 'file_analysis':
    errors.append('step0-real-analysis-failure-repair: run 2 execution_kind must be file_analysis')

tampered_analysis = copy.deepcopy(real_validation.get('payload', {}))
tampered_analysis['sha256_bytes'] = 'deadbeef' * 8
tampered_output_path = real_success_dir/'runtime-analysis-result-tampered.json'
tampered_output_path.write_text(json.dumps(tampered_analysis, indent=2, sort_keys=True) + '\n')
tampered_contract = {
    'validator': {
        'kind': 'independent_file_analysis',
        'output_file': str(tampered_output_path),
        'target': real_analysis_output.get('target'),
    }
}
tampered_result = pv.validate_independent_file_analysis(tampered_contract, {})
if tampered_result.get('status') != 'failed':
    errors.append('step0-validator-independence: tampering with adapter sha256 must cause validation failure')
if 'independent re-computation does not match' not in tampered_result.get('reason', ''):
    errors.append('step0-validator-independence: tampered validation must report mismatch reason')

conflict_strategy=json.loads((base/'step2-strategy-conflict.json').read_text())
slot_resolution=conflict_strategy.get('strategy_trace', {}).get('slot_resolution', {})
if conflict_strategy.get('fallback_choice') != 'sticky-adapter-first':
    errors.append('step2-strategy-conflict: higher-priority soft rule should win fallback_choice')
if conflict_strategy.get('retry_policy') != 'bounded-repair-with-evidence':
    errors.append('step2-strategy-conflict: higher-priority soft rule should win retry_policy')
if conflict_strategy.get('execution_ordering') != ['precheck', 'execute', 'validate']:
    errors.append('step2-strategy-conflict: pattern hint should control execution_ordering')
ignored_exp = slot_resolution.get('execution_ordering', {}).get('ignored', [])
if not any(item.get('source_id') == 'experimental-order-attempt' for item in ignored_exp):
    errors.append('step2-strategy-conflict: experimental ordering override should be rejected by slot permissions')
if slot_resolution.get('fallback_choice', {}).get('winner', {}).get('source_id') != 'soft-high-fallback':
    errors.append('step2-strategy-conflict: fallback_choice winner should be deterministic')

import copy
import pathlib
import sys
import tempfile
sys.path.insert(0, str(pathlib.Path(os.environ['POLARIS_ROOT']) / 'scripts'))
import polaris_validator as pv
import polaris_orchestrator as po
import polaris_state as ps
success_contract = run2_state['artifacts']['execution_contract']
tampered_profile = copy.deepcopy(success_contract)
tampered_profile['validator']['max_selection_inputs'] = 99
profile_result = pv.validate_runner_result_contract(tampered_profile, {})
if profile_result.get('status') != 'failed' or 'profile-derived selection budget' not in profile_result.get('reason', ''):
    errors.append('step2-budget-tamper: validator should reject contracts whose numeric selection budget conflicts with budget_profile semantics')
tampered_source = copy.deepcopy(success_contract)
tampered_source['validator']['hot_path_budget_source'] = 'baseline'
source_result = pv.validate_runner_result_contract(tampered_source, {})
if source_result.get('status') != 'failed' or 'hot_path_budget_source baseline is inconsistent' not in source_result.get('reason', ''):
    errors.append('step2-budget-tamper: validator should reject contracts whose source-derived hot-path semantics are inconsistent')

malformed_contract = copy.deepcopy(success_contract)
malformed_path = base/'step3-malformed-runner-result.json'
malformed_payload = json.loads((base/'runner-success'/'runtime-execution-result.json').read_text())
malformed_payload.pop('result', None)
malformed_path.write_text(json.dumps(malformed_payload, indent=2, sort_keys=True) + '\n')
malformed_contract['validator']['output_file'] = str(malformed_path)
malformed_result = pv.validate_runner_result_contract(malformed_contract, {})
if malformed_result.get('status') != 'failed' or 'missing required fields' not in malformed_result.get('reason', ''):
    errors.append('step3-malformed-artifact: validator should reject malformed runner artifacts')

consolidation_dir = base/'step3-consolidation-failure'
consolidation_dir.mkdir(exist_ok=True)
import polaris_compat as pc
pc.write_runtime_format(consolidation_dir)
consolidation_state = consolidation_dir/'execution-state.json'
state = ps.default_state()
state['execution_profile'] = 'standard'
state['state_density'] = 'minimal'
state['repair_depth'] = 'shallow'
state['event_budget'] = 'standard'
consolidation_state.write_text(json.dumps(state, indent=2, sort_keys=True) + '\n')
backlog_items = [{
    'queued_at': '2026-03-14T00:00:00+00:00',
    'kind': 'success_marker',
    'payload': {
        'pattern_id': 'step3-consolidation-smoke',
        'fingerprint': 'step3-consolidation-smoke',
        'summary': 'consolidation failure smoke',
        'trigger': 'step3 consolidation failure',
        'sequence': ['execute', 'validate'],
        'outcome': 'retained on consolidation failure',
        'evidence': ['smoke'],
        'adapter': 'shell-local',
        'tags': ['orchestration', 'local', 'standard'],
        'modes': ['short'],
        'confidence': 70,
        'lifecycle_state': 'experimental',
        'reusable': True,
        'strategy_hints': {'execution_ordering': ['execute', 'validate']},
    },
}]
results, retained, consolidation_summary = po.consolidate_backlog(
    pathlib.Path(os.environ['POLARIS_ROOT']) / 'scripts',
    str(consolidation_state),
    str(consolidation_dir/'missing'/'success-patterns.json'),
    str(consolidation_dir/'rules.json'),
    backlog_items,
)
if len(retained) != 1:
    errors.append('step3-consolidation-failure: retained backlog should keep failed consolidation item')
if not results or results[0].get('returncode') == 0:
    errors.append('step3-consolidation-failure: consolidation should produce a failing result for invalid output path')
consolidated_state = json.loads(consolidation_state.read_text())
if len(consolidated_state.get('learning_backlog', [])) != 1:
    errors.append('step3-consolidation-failure: learning_backlog should retain failed consolidation item')
if not consolidated_state.get('artifacts', {}).get('learning_summary'):
    errors.append('step3-consolidation-failure: learning_summary should be recorded even when consolidation fails')

# ═══════════════════════════════════════════════════════════════
# Step 1-2 assertions: Compatibility Spine + Runtime-dir Safety
# ═══════════════════════════════════════════════════════════════

# --- compat-v5-load-write-reload-lossless ---
# Create a representative v5 state, load -> write -> reload, verify lossless round-trip
v5_dir = base / 'compat-v5-lossless-test'
v5_dir.mkdir(exist_ok=True)
pc.write_runtime_format(v5_dir)
v5_state_path = v5_dir / 'execution-state.json'
v5_state = {
    'schema_version': 5,
    'run_id': 'v5-test-run',
    'goal': 'Test v5 compatibility',
    'mode': 'short',
    'execution_profile': 'standard',
    'state_density': 'minimal',
    'repair_depth': 'shallow',
    'event_budget': 'standard',
    'learning_backlog': [],
    'status': 'completed',
    'progress_pct': 100,
    'phase': 'completed',
    'current_step': 'Done',
    'next_action': None,
    'summary_outcome': 'v5 test completed',
    'plan': [{'index': 1, 'step_id': 'p1', 'phase': 'completed', 'step': 'Test', 'status': 'completed'}],
    'checkpoints': [{'value': 'cp1', 'kind': 'milestone', 'ts': '2026-03-15T00:00:00+00:00'}],
    'attempts': [{'ts': '2026-03-15T00:00:00+00:00', 'step': 'test', 'status': 'passed', 'summary': 'ok', 'evidence': [], 'branch_id': 'main'}],
    'artifacts': {
        'selected_adapter': 'shell-local',
        'selected_pattern': 'test-pattern',
        'execution_kind': 'runner',
        'execution_result': 'runtime-execution-result.json',
        'executor_result': 'runtime-executor-result.json',
        'validation_result': 'runtime-validation-result.json',
    },
    'lessons': [],
    'success_patterns': [],
    'references': [{'ts': '2026-03-15T00:00:00+00:00', 'kind': 'rules', 'value': 'rules.json', 'label': 'test'}],
    'runtime': {
        'lifecycle_stage': 'completed',
        'started_at': '2026-03-15T00:00:00+00:00',
        'last_heartbeat_at': '2026-03-15T00:00:00+00:00',
        'completed_at': '2026-03-15T00:01:00+00:00',
        'durable_status_surfaces': {},
        'metrics': {'state_write_count': 5, 'learning_hot_path_ops': 1},
    },
    'state_machine': {
        'node': 'completed',
        'active_branch': None,
        'history': [{'ts': '2026-03-15T00:00:00+00:00', 'from': 'executing', 'to': 'completed', 'summary': 'done', 'branch_id': 'main'}],
        'history_summary': [],
        'branches': [],
        'recovery': [],
        'blocked': {'is_blocked': False, 'reason': None, 'references': []},
    },
    'rule_context': {
        'active_layers': ['hard', 'soft'],
        'applied_rules': [{'rule_id': 'stop-on-nonrepair-denial', 'layer': 'hard'}],
    },
    'updated_at': '2026-03-15T00:01:00+00:00',
}
v5_state_path.write_text(json.dumps(v5_state, indent=2, sort_keys=True) + '\n')

# Step 1: load
loaded = ps.load_state(v5_state_path)
if loaded.get('schema_version') != 6:
    errors.append('compat-v5-lossless: loaded state should have schema_version 6')
if loaded.get('compat', {}).get('upgraded_from') != 5:
    errors.append('compat-v5-lossless: compat.upgraded_from should be 5')
if loaded.get('run_id') != 'v5-test-run':
    errors.append('compat-v5-lossless: run_id lost during load')
if loaded.get('goal') != 'Test v5 compatibility':
    errors.append('compat-v5-lossless: goal lost during load')
if loaded.get('artifacts', {}).get('selected_adapter') != 'shell-local':
    errors.append('compat-v5-lossless: artifacts.selected_adapter lost during load')
if loaded.get('state_machine', {}).get('node') != 'completed':
    errors.append('compat-v5-lossless: state_machine.node lost during load')
if loaded.get('rule_context', {}).get('applied_rules', [{}])[0].get('rule_id') != 'stop-on-nonrepair-denial':
    errors.append('compat-v5-lossless: rule_context.applied_rules lost during load')

# Step 2: write (exercises minimal-density whitelist)
ps.write_json(v5_state_path, loaded)

# Step 3: reload and compare key fields
reloaded = json.loads(v5_state_path.read_text())
if reloaded.get('schema_version') != 6:
    errors.append('compat-v5-lossless: schema_version lost after write-reload')
if reloaded.get('compat', {}).get('upgraded_from') != 5:
    errors.append('compat-v5-lossless: compat field lost after write-reload (minimal-density whitelist gap)')
if reloaded.get('run_id') != 'v5-test-run':
    errors.append('compat-v5-lossless: run_id lost after write-reload')
if reloaded.get('goal') != 'Test v5 compatibility':
    errors.append('compat-v5-lossless: goal lost after write-reload')
if reloaded.get('mode') != 'short':
    errors.append('compat-v5-lossless: mode lost after write-reload')
if reloaded.get('execution_profile') != 'standard':
    errors.append('compat-v5-lossless: execution_profile lost after write-reload')
if reloaded.get('artifacts', {}).get('selected_adapter') != 'shell-local':
    errors.append('compat-v5-lossless: artifacts.selected_adapter lost after write-reload')
if reloaded.get('artifacts', {}).get('execution_kind') != 'runner':
    errors.append('compat-v5-lossless: artifacts.execution_kind lost after write-reload')
if reloaded.get('state_machine', {}).get('node') != 'completed':
    errors.append('compat-v5-lossless: state_machine.node lost after write-reload')
if reloaded.get('rule_context', {}).get('applied_rules', [{}])[0].get('rule_id') != 'stop-on-nonrepair-denial':
    errors.append('compat-v5-lossless: rule_context.applied_rules lost after write-reload')
if reloaded.get('summary_outcome') != 'v5 test completed':
    errors.append('compat-v5-lossless: summary_outcome lost after write-reload')

# --- compat-runtime-format-gate ---
# Incompatible runtime-format.json should block the demo script entirely
import subprocess as sp
gate_dir = base / 'compat-gate-test'
gate_dir.mkdir(exist_ok=True)
(gate_dir / 'runtime-format.json').write_text(json.dumps({'runtime_format': 999, 'created_by': 'future-polaris'}, indent=2) + '\n')
gate_proc = sp.run(
    ['bash', str(pathlib.Path(os.environ['POLARIS_ROOT']) / 'scripts' / 'polaris_runtime_demo.sh')],
    capture_output=True, text=True,
    env={**__import__('os').environ, 'POLARIS_RUNTIME_DIR': str(gate_dir), 'POLARIS_SIMULATE_ERROR': ''},
)
if gate_proc.returncode == 0:
    errors.append('compat-runtime-format-gate: demo should abort on incompatible runtime format')

# --- compat-wrapper-no-early-write ---
# Verify no adapter/rule/pattern files were written before gate blocked
if (gate_dir / 'adapters.json').exists():
    errors.append('compat-wrapper-no-early-write: adapters.json was written before gate blocked')
if (gate_dir / 'rules.json').exists():
    errors.append('compat-wrapper-no-early-write: rules.json was written before gate blocked')
if (gate_dir / 'success-patterns.json').exists():
    errors.append('compat-wrapper-no-early-write: success-patterns.json was written before gate blocked')

# --- compat-schema-gate ---
# Compatible runtime_format (1) but incompatible schema_version (999) should be refused
schema_gate_dir = base / 'compat-schema-gate-test'
schema_gate_dir.mkdir(exist_ok=True)
pc.write_runtime_format(schema_gate_dir)
(schema_gate_dir / 'execution-state.json').write_text(json.dumps({
    'schema_version': 999,
    'run_id': 'future-run',
    'goal': 'from the future',
}, indent=2, sort_keys=True) + '\n')
schema_gate_proc = sp.run(
    ['bash', str(pathlib.Path(os.environ['POLARIS_ROOT']) / 'scripts' / 'polaris_runtime_demo.sh')],
    capture_output=True, text=True,
    env={**__import__('os').environ, 'POLARIS_RUNTIME_DIR': str(schema_gate_dir), 'POLARIS_SIMULATE_ERROR': ''},
)
if schema_gate_proc.returncode == 0:
    errors.append('compat-schema-gate: demo should abort on incompatible schema version 999')
if (schema_gate_dir / 'adapters.json').exists():
    errors.append('compat-schema-gate: adapters.json was written despite incompatible schema')
if (schema_gate_dir / 'rules.json').exists():
    errors.append('compat-schema-gate: rules.json was written despite incompatible schema')

# --- compat-legacy-dir-upgrade ---
# Directory with v5 state and no runtime-format.json should be upgraded gracefully
legacy_dir = base / 'compat-legacy-upgrade-test'
legacy_dir.mkdir(exist_ok=True)
legacy_state_path = legacy_dir / 'execution-state.json'
legacy_v5 = {'schema_version': 5, 'run_id': 'legacy-run', 'goal': 'legacy test', 'mode': 'long', 'status': 'not_started'}
legacy_state_path.write_text(json.dumps(legacy_v5, indent=2, sort_keys=True) + '\n')
# No runtime-format.json — this is a legacy dir
legacy_proc = sp.run(
    ['bash', str(pathlib.Path(os.environ['POLARIS_ROOT']) / 'scripts' / 'polaris_runtime_demo.sh')],
    capture_output=True, text=True,
    env={**__import__('os').environ, 'POLARIS_RUNTIME_DIR': str(legacy_dir), 'POLARIS_SIMULATE_ERROR': ''},
)
if legacy_proc.returncode != 0:
    errors.append(f'compat-legacy-dir-upgrade: demo should complete on legacy dir, got exit {legacy_proc.returncode}: {legacy_proc.stderr[:200]}')
if not (legacy_dir / 'runtime-format.json').exists():
    errors.append('compat-legacy-dir-upgrade: runtime-format.json should be created for legacy dir')
else:
    legacy_marker = json.loads((legacy_dir / 'runtime-format.json').read_text())
    if legacy_marker.get('runtime_format') != 1:
        errors.append('compat-legacy-dir-upgrade: runtime-format.json should have runtime_format=1')
legacy_final_state = json.loads(legacy_state_path.read_text())
if legacy_final_state.get('schema_version') != 6:
    errors.append('compat-legacy-dir-upgrade: state should be upgraded to schema_version 6')

# --- compat-format-marker-written ---
# Verify runtime-format.json exists in every normal regression scenario dir
for scenario_name in summary:
    scenario_dir = base / scenario_name
    marker_path = scenario_dir / 'runtime-format.json'
    if not marker_path.exists():
        errors.append(f'compat-format-marker-written: {scenario_name} missing runtime-format.json')
    else:
        marker_data = json.loads(marker_path.read_text())
        if marker_data.get('runtime_format') != 1:
            errors.append(f'compat-format-marker-written: {scenario_name} has wrong runtime_format')

# Verify all normal scenarios have schema_version 6 and compat field
for scenario_name in summary:
    scenario_dir = base / scenario_name
    state_path = scenario_dir / 'execution-state.json'
    if state_path.exists():
        s = json.loads(state_path.read_text())
        if s.get('schema_version') != 6:
            errors.append(f'compat-schema-v6: {scenario_name} has schema_version {s.get("schema_version")}, expected 6')
        if 'compat' not in s:
            errors.append(f'compat-schema-v6: {scenario_name} missing compat field')

# ═══════════════════════════════════════════════════════════════
# Step 3B assertions: Resume from blocked
# ═══════════════════════════════════════════════════════════════

# --- resume-from-blocked ---
resume_blocked_dir = base / 'resume-from-blocked'
resume_state = json.loads((resume_blocked_dir / 'execution-state.json').read_text())
if resume_state.get('status') != 'completed':
    errors.append('resume-from-blocked: second run (resumed) should complete')
if resume_state.get('run_id') != 'polaris-orchestrated-run':
    errors.append('resume-from-blocked: run_id should be preserved from first run')
if resume_state.get('compat', {}).get('resumed_count') != 1:
    errors.append(f'resume-from-blocked: compat.resumed_count should be 1, got {resume_state.get("compat", {}).get("resumed_count")}')
# learning_backlog key must exist in resumed state (preserved from first run, not cleared by re-init)
if 'learning_backlog' not in resume_state:
    errors.append('resume-from-blocked: learning_backlog key must exist in resumed state')
# State machine history should exist (may be compacted in minimal density, so just check non-empty)
history = resume_state.get('state_machine', {}).get('history', [])
if not history:
    errors.append('resume-from-blocked: state machine history should not be empty after resumed run')

# --- resume-no-overwrite-completed ---
resume_completed_dir = base / 'resume-no-overwrite-completed'
resume_completed_state = json.loads((resume_completed_dir / 'execution-state.json').read_text())
if resume_completed_state.get('status') != 'completed':
    errors.append('resume-no-overwrite-completed: second run should complete')
if resume_completed_state.get('compat', {}).get('resumed_count', -1) != 0:
    errors.append(f'resume-no-overwrite-completed: compat.resumed_count should be 0 (fresh init), got {resume_completed_state.get("compat", {}).get("resumed_count")}')

# --- resume-refuse-in-progress ---
resume_inprogress_exit = int(os.environ.get('RESUME_INPROGRESS_EXIT', '0'))
if resume_inprogress_exit == 0:
    errors.append('resume-refuse-in-progress: orchestrator should refuse (exit non-zero) when state is in_progress')

# Verify resumed_count exists in all scenarios
for scenario_name in summary:
    scenario_dir = base / scenario_name
    state_path = scenario_dir / 'execution-state.json'
    if state_path.exists():
        s = json.loads(state_path.read_text())
        if 'compat' in s and 'resumed_count' not in s.get('compat', {}):
            errors.append(f'compat-resumed-count: {scenario_name} missing resumed_count in compat')

# ═══════════════════════════════════════════════════════════════
# Step 4A assertions: Bootstrap protocol
# ═══════════════════════════════════════════════════════════════

# 4A.1: polaris_bootstrap.json exists with 5 adapters, 1 rule, 1 pattern, requires section
bootstrap_manifest_path = pathlib.Path(os.environ['POLARIS_ROOT']) / 'scripts' / 'polaris_bootstrap.json'
manifest = json.loads(bootstrap_manifest_path.read_text()) if bootstrap_manifest_path.exists() else None
if manifest is None:
    errors.append('4A-manifest: polaris_bootstrap.json does not exist')
else:
    if len(manifest.get('adapters', [])) != 6:
        errors.append(f'4A-manifest: expected 6 adapters, got {len(manifest.get("adapters", []))}')
    if len(manifest.get('rules', [])) != 1:
        errors.append(f'4A-manifest: expected 1 rule, got {len(manifest.get("rules", []))}')
    if len(manifest.get('patterns', [])) != 1:
        errors.append(f'4A-manifest: expected 1 pattern, got {len(manifest.get("patterns", []))}')
    if 'requires' not in manifest:
        errors.append('4A-manifest: missing requires section')

# 4A.2: polaris_runtime_demo.sh has no polaris_adapters.py add calls
demo_path = pathlib.Path(os.environ['POLARIS_ROOT']) / 'scripts' / 'polaris_runtime_demo.sh'
if demo_path.exists():
    demo_content = demo_path.read_text()
    if 'polaris_adapters.py add' in demo_content:
        errors.append('4A-demo: polaris_runtime_demo.sh still has inline polaris_adapters.py add calls')
    if 'polaris_rules.py add' in demo_content:
        errors.append('4A-demo: polaris_runtime_demo.sh still has inline polaris_rules.py add calls')
    if 'polaris_success_patterns.py capture' in demo_content:
        errors.append('4A-demo: polaris_runtime_demo.sh still has inline polaris_success_patterns.py capture calls')

# 4A.5: Bootstrap idempotency — second run should skip
idem_report_path = base / 'bootstrap-idempotency' / 'bootstrap-run2.json'
if idem_report_path.exists():
    idem_report = json.loads(idem_report_path.read_text())
    if not idem_report.get('skipped'):
        errors.append('4A-idempotency: second bootstrap run should report skipped=true')
else:
    errors.append('4A-idempotency: bootstrap-run2.json not found')

# 4A.6: Bootstrap requirement failure
bootstrap_fail_exit = int(os.environ.get('BOOTSTRAP_FAIL_EXIT', '0'))
if bootstrap_fail_exit == 0:
    errors.append('4A-req-failure: bootstrap with bad interpreter should exit non-zero')
# No files should be written to the fail dir
fail_adapters = base / 'bootstrap-req-failure' / 'adapters.json'
if fail_adapters.exists():
    errors.append('4A-req-failure: adapters.json should not be written when requirements fail')

# 4A.7: Bootstrap capability probe — unknown capability should fail
bootstrap_cap_exit = int(os.environ.get('BOOTSTRAP_CAP_EXIT', '0'))
if bootstrap_cap_exit == 0:
    errors.append('4A-cap-failure: bootstrap with unknown capability should exit non-zero')

# 4A.7b: Bootstrap real probe failure — interpreter exists but local-exec probe fails
bootstrap_probe_exit = int(os.environ.get('BOOTSTRAP_PROBE_EXIT', '0'))
if bootstrap_probe_exit == 0:
    errors.append('4A-probe-failure: bootstrap with failing local-exec probe (false interpreter) should exit non-zero')
probe_adapters = base / 'bootstrap-probe-failure' / 'adapters.json'
if probe_adapters.exists():
    errors.append('4A-probe-failure: adapters.json should not be written when probe fails')

# 4A.8: runtime-bootstrap-report.json written for normal scenarios
for scenario_name in ['micro-success', 'runner-success', 'deep-success']:
    report_path = base / scenario_name / 'runtime-bootstrap-report.json'
    if not report_path.exists():
        errors.append(f'4A-report: {scenario_name} missing runtime-bootstrap-report.json')
    else:
        report = json.loads(report_path.read_text())
        if 'requires_check' not in report:
            errors.append(f'4A-report: {scenario_name} bootstrap report missing requires_check')

# ═══════════════════════════════════════════════════════════════
# Step 4B assertions: Experience asset versioning + migration
# ═══════════════════════════════════════════════════════════════

# 4B.1/4B.2: Pattern migration — v1 gets asset_version:1, new gets asset_version:2
pattern_mig_dir = base / '4b-pattern-migration'
pattern_store = json.loads((pattern_mig_dir / 'success-patterns.json').read_text())
for p in pattern_store.get('patterns', []):
    if p.get('pattern_id') == 'v1-test':
        if p.get('asset_version') != 1:
            errors.append(f'4B-pattern-migration: v1 pattern should have asset_version=1, got {p.get("asset_version")}')
        if p.get('migrated_from') != 'pre-step4':
            errors.append('4B-pattern-migration: v1 pattern should have migrated_from=pre-step4')
        # Behavioral fields must be unchanged
        if p.get('trigger') != 'test' or p.get('outcome') != 'pass' or p.get('sequence') != ['a', 'b']:
            errors.append('4B-pattern-migration: migration altered behavioral fields')
    elif p.get('pattern_id') == 'v2-test':
        if p.get('asset_version') != 2:
            errors.append(f'4B-pattern-migration: v2 pattern should have asset_version=2, got {p.get("asset_version")}')

# 4B: Pattern merge upgrade — v1 pattern re-captured must become asset_version:2
merge_dir = base / '4b-pattern-merge-upgrade'
merge_store = json.loads((merge_dir / 'success-patterns.json').read_text())
for p in merge_store.get('patterns', []):
    if p.get('pattern_id') == 'merge-target':
        if p.get('asset_version') != 2:
            errors.append(f'4B-pattern-merge: merged v1 pattern should upgrade to asset_version=2, got {p.get("asset_version")}')
        if p.get('migrated_from') is not None:
            errors.append('4B-pattern-merge: merged pattern should not retain migrated_from')

# 4B: Pattern consolidate-marker merge upgrade — same path via consolidate
consol_dir = base / '4b-pattern-consolidate-merge'
consol_store = json.loads((consol_dir / 'success-patterns.json').read_text())
for p in consol_store.get('patterns', []):
    if p.get('pattern_id') == 'consol-target':
        if p.get('asset_version') != 2:
            errors.append(f'4B-pattern-consol-merge: consolidated v1 pattern should upgrade to asset_version=2, got {p.get("asset_version")}')
        if p.get('migrated_from') is not None:
            errors.append('4B-pattern-consol-merge: consolidated pattern should not retain migrated_from')

# 4B.5/4B.6: Rule migration — v1 gets asset_version:1, new gets asset_version:2
rule_mig_dir = base / '4b-rule-migration'
rule_store = json.loads((rule_mig_dir / 'rules.json').read_text())
for r in rule_store.get('rules', []):
    if r.get('rule_id') == 'v1-rule':
        if r.get('asset_version') != 1:
            errors.append(f'4B-rule-migration: v1 rule should have asset_version=1, got {r.get("asset_version")}')
        if r.get('migrated_from') != 'pre-step4':
            errors.append('4B-rule-migration: v1 rule should have migrated_from=pre-step4')
        # Behavioral fields must be unchanged
        if r.get('trigger') != 'test' or r.get('action') != 'do thing':
            errors.append('4B-rule-migration: migration altered behavioral fields')
    elif r.get('rule_id') == 'v2-rule':
        if r.get('asset_version') != 2:
            errors.append(f'4B-rule-migration: v2 rule should have asset_version=2, got {r.get("asset_version")}')

# 4B.7/4B.8: Backlog migration — v1 items get asset_version:1
backlog_mig_dir = base / '4b-backlog-migration'
sys.path.insert(0, str(pathlib.Path(os.environ['POLARIS_ROOT']) / 'scripts'))
import polaris_state
backlog_state = polaris_state.load_state(backlog_mig_dir / 'execution-state.json')
for item in backlog_state.get('learning_backlog', []):
    if 'asset_version' not in item:
        errors.append('4B-backlog-migration: backlog item missing asset_version after load')
    elif item['asset_version'] != 1:
        errors.append(f'4B-backlog-migration: old backlog item should have asset_version=1, got {item["asset_version"]}')

# 4B.5 (new backlog items): check any scenario with learning backlog for asset_version:2
for scenario_name in ['deep-success', 'deep-repair']:
    scenario_dir = base / scenario_name
    state_path = scenario_dir / 'execution-state.json'
    if state_path.exists():
        s = json.loads(state_path.read_text())
        for item in s.get('learning_backlog', []):
            if 'asset_version' not in item:
                errors.append(f'4B-backlog-new: {scenario_name} backlog item missing asset_version')
            elif item['asset_version'] != 2:
                errors.append(f'4B-backlog-new: {scenario_name} new backlog item should have asset_version=2, got {item["asset_version"]}')

# 4B.1 (new patterns): check that patterns registered by bootstrap have asset_version:2
for scenario_name in ['micro-success', 'runner-success']:
    scenario_dir = base / scenario_name
    pat_path = scenario_dir / 'success-patterns.json'
    if pat_path.exists():
        ps = json.loads(pat_path.read_text())
        for p in ps.get('patterns', []):
            if 'asset_version' not in p:
                errors.append(f'4B-pattern-new: {scenario_name} pattern missing asset_version')
            elif p['asset_version'] != 2:
                errors.append(f'4B-pattern-new: {scenario_name} pattern should have asset_version=2')

# 4B.5 (new rules): check that rules registered by bootstrap have asset_version:2
for scenario_name in ['micro-success', 'runner-success']:
    scenario_dir = base / scenario_name
    rules_path = scenario_dir / 'rules.json'
    if rules_path.exists():
        rs = json.loads(rules_path.read_text())
        for r in rs.get('rules', []):
            if 'asset_version' not in r:
                errors.append(f'4B-rule-new: {scenario_name} rule missing asset_version')
            elif r['asset_version'] != 2:
                errors.append(f'4B-rule-new: {scenario_name} rule should have asset_version=2')

# 4B.9: Resume preserves original asset_version on backlog items
resume_blocked_dir2 = base / 'resume-from-blocked'
resume_state2 = json.loads((resume_blocked_dir2 / 'execution-state.json').read_text())
for item in resume_state2.get('learning_backlog', []):
    if 'asset_version' not in item:
        errors.append('4B-resume-version: resumed backlog item missing asset_version')
    elif item['asset_version'] != 2:
        errors.append(f'4B-resume-version: resumed backlog item should keep asset_version=2, got {item["asset_version"]}')

# ═══════════════════════════════════════════════════════════════
# Step 5A assertions: Cross-version state evidence
# ═══════════════════════════════════════════════════════════════

import polaris_v5_snapshot as v5

# 5A.1: polaris_v5_snapshot.py exists with the three required functions
snapshot_path = pathlib.Path(os.environ['POLARIS_ROOT']) / 'scripts' / 'polaris_v5_snapshot.py'
if not snapshot_path.exists():
    errors.append('5A-snapshot: polaris_v5_snapshot.py does not exist')
for fn_name in ['v5_load_state', 'v5_write_json', 'v5_default_state']:
    if not hasattr(v5, fn_name):
        errors.append(f'5A-snapshot: polaris_v5_snapshot.py missing {fn_name}')

# 5A.2: rollback-v6-in-v5-loader — v6 state loads in v5 loader, key fields survive
# Pick a completed v6 scenario
v6_source = base / 'runner-success' / 'execution-state.json'
if v6_source.exists():
    import tempfile
    v6_state_orig = json.loads(v6_source.read_text())
    # Feed to v5 loader
    with tempfile.TemporaryDirectory() as td:
        td_path = pathlib.Path(td)
        # Copy v6 state to temp
        (td_path / 'execution-state.json').write_text(v6_source.read_text())
        try:
            v5_loaded = v5.v5_load_state(td_path / 'execution-state.json')
            # Key fields survive
            if v5_loaded.get('run_id') != v6_state_orig.get('run_id'):
                errors.append('5A-rollback: run_id did not survive v6->v5 load')
            if v5_loaded.get('goal') != v6_state_orig.get('goal'):
                errors.append('5A-rollback: goal did not survive v6->v5 load')
            if v5_loaded.get('status') != v6_state_orig.get('status'):
                errors.append('5A-rollback: status did not survive v6->v5 load')
            if v5_loaded.get('artifacts', {}).get('selected_adapter') != v6_state_orig.get('artifacts', {}).get('selected_adapter'):
                errors.append('5A-rollback: artifacts.selected_adapter did not survive v6->v5 load')
            if v5_loaded.get('state_machine', {}).get('node') != v6_state_orig.get('state_machine', {}).get('node'):
                errors.append('5A-rollback: state_machine.node did not survive v6->v5 load')
            # schema_version should be 5 (v5 loader forces it)
            if v5_loaded.get('schema_version') != 5:
                errors.append(f'5A-rollback: v5 loader should set schema_version=5, got {v5_loaded.get("schema_version")}')
            # Write with v5 writer, then reload with current loader
            v5.v5_write_json(td_path / 'execution-state.json', v5_loaded)
            v6_reloaded = polaris_state.load_state(td_path / 'execution-state.json')
            if v6_reloaded.get('schema_version') != 6:
                errors.append('5A-rollback-roundtrip: v5-written state should upgrade to v6')
            if v6_reloaded.get('run_id') != v6_state_orig.get('run_id'):
                errors.append('5A-rollback-roundtrip: run_id did not survive full round-trip')
            if v6_reloaded.get('goal') != v6_state_orig.get('goal'):
                errors.append('5A-rollback-roundtrip: goal did not survive full round-trip')
            if v6_reloaded.get('status') != v6_state_orig.get('status'):
                errors.append('5A-rollback-roundtrip: status did not survive full round-trip')
        except Exception as e:
            errors.append(f'5A-rollback: v5 loader crashed on v6 state: {e}')
else:
    errors.append('5A-rollback: runner-success/execution-state.json not found')

# 5A.3: coexist-v5-dir-full-run — v5-written state runs end-to-end
coexist_dir = base / 'coexist-v5-dir-full-run'
coexist_state_path = coexist_dir / 'execution-state.json'
if coexist_state_path.exists():
    coexist_state = json.loads(coexist_state_path.read_text())
    if coexist_state.get('schema_version') != 6:
        errors.append(f'5A-coexist: state should be upgraded to v6, got {coexist_state.get("schema_version")}')
    if coexist_state.get('status') != 'completed':
        errors.append(f'5A-coexist: run should complete, got {coexist_state.get("status")}')
    if not (coexist_dir / 'runtime-format.json').exists():
        errors.append('5A-coexist: runtime-format.json should be written by legacy gate')
else:
    errors.append('5A-coexist: coexist-v5-dir-full-run/execution-state.json not found')

# 5A.4: cross-version-round-trip — v5->v6->v5 preserves key fields
import tempfile
with tempfile.TemporaryDirectory() as td:
    td_path = pathlib.Path(td)
    # Start: v5 default state → v5 write
    v5_state = v5.v5_default_state()
    v5_state['run_id'] = 'cross-version-test'
    v5_state['goal'] = 'round-trip test'
    v5_state['status'] = 'completed'
    v5.v5_write_json(td_path / 'execution-state.json', v5_state)
    # Step 1: current load_state (v5→v6 upgrade)
    try:
        v6_loaded = polaris_state.load_state(td_path / 'execution-state.json')
        if v6_loaded.get('schema_version') != 6:
            errors.append('5A-roundtrip: step1 should upgrade to v6')
        if v6_loaded.get('run_id') != 'cross-version-test':
            errors.append('5A-roundtrip: step1 lost run_id')
        if v6_loaded.get('goal') != 'round-trip test':
            errors.append('5A-roundtrip: step1 lost goal')
        # Step 2: current write_json (v6 format)
        polaris_state.write_json(td_path / 'execution-state.json', v6_loaded)
        # Step 3: v5 load
        v5_reloaded = v5.v5_load_state(td_path / 'execution-state.json')
        if v5_reloaded.get('run_id') != 'cross-version-test':
            errors.append('5A-roundtrip: step3 lost run_id after v5 reload')
        if v5_reloaded.get('goal') != 'round-trip test':
            errors.append('5A-roundtrip: step3 lost goal after v5 reload')
        if v5_reloaded.get('status') != 'completed':
            errors.append('5A-roundtrip: step3 lost status after v5 reload')
    except Exception as e:
        errors.append(f'5A-roundtrip: crashed during round-trip: {e}')

# ═══════════════════════════════════════════════════════════════
# Step 5B assertions: Planner contract metadata
# ═══════════════════════════════════════════════════════════════

# 5B.1/5B.3: Deep-profile plan steps have requires and validates_with
deep_state = json.loads((base / 'deep-success' / 'execution-state.json').read_text())
for step in deep_state.get('plan', []):
    if 'requires' not in step:
        errors.append(f'5B-plan-requires: deep step {step.get("phase")} missing requires')
    if 'validates_with' not in step:
        errors.append(f'5B-plan-requires: deep step {step.get("phase")} missing validates_with')
    phase = step.get('phase')
    if phase == 'executing':
        if 'local-exec' not in step.get('requires', []):
            errors.append('5B-plan-requires: executing step should require local-exec')
        if step.get('validates_with') != 'runner_result_contract':
            errors.append(f'5B-plan-requires: executing step should have validates_with=runner_result_contract, got {step.get("validates_with")}')
    if phase == 'validating':
        if 'local-exec' not in step.get('requires', []) or 'reporting' not in step.get('requires', []):
            errors.append('5B-plan-requires: validating step should require local-exec and reporting')
        if step.get('validates_with') != 'evidence_check':
            errors.append(f'5B-plan-requires: validating step should have validates_with=evidence_check, got {step.get("validates_with")}')

# 5B.2: Micro-profile plan steps have requires and validates_with
micro_state = json.loads((base / 'micro-success' / 'execution-state.json').read_text())
for step in micro_state.get('plan', []):
    if 'requires' not in step:
        errors.append(f'5B-plan-requires-micro: step {step.get("phase")} missing requires')
    if 'validates_with' not in step:
        errors.append(f'5B-plan-requires-micro: step {step.get("phase")} missing validates_with')

# 5B.4: capability_warning on synthetic mismatch
import polaris_contract_planner as cp
limited_adapter = {'tool': 'limited', 'command': 'echo', 'capabilities': ['reporting'], 'inputs': []}
_, warn_trace = cp.choose_family('auto', limited_adapter, [], None, None, plan_requires=['local-exec', 'reporting'])
if 'capability_warning' not in warn_trace:
    errors.append('5B-capability-warning: trace should contain capability_warning when adapter missing local-exec')
elif 'local-exec' not in warn_trace['capability_warning']:
    errors.append(f'5B-capability-warning: warning should mention local-exec, got: {warn_trace["capability_warning"]}')

# Verify no warning when adapter has all required capabilities
full_adapter = {'tool': 'full', 'command': 'echo', 'capabilities': ['local-exec', 'reporting', 'generic-runner'], 'inputs': []}
_, no_warn_trace = cp.choose_family('auto', full_adapter, [], None, None, plan_requires=['local-exec', 'reporting'])
if 'capability_warning' in no_warn_trace:
    errors.append('5B-capability-warning: no warning expected when adapter has all required capabilities')

# ═══════════════════════════════════════════════════════════════
# Phase 1: Real shell-command experience loop assertions
# ═══════════════════════════════════════════════════════════════

# Phase 1A: real-shell-success — adapter ran real command, result is runner-compatible
real_shell_success_state = json.loads((base / 'real-shell-success' / 'execution-state.json').read_text())
if real_shell_success_state.get('status') != 'completed':
    errors.append('phase1-real-shell-success: run should complete')
real_shell_result_path = base / 'real-shell-success' / 'runtime-execution-result.json'
if not real_shell_result_path.exists():
    errors.append('phase1-real-shell-success: execution result file missing')
else:
    real_shell_result = json.loads(real_shell_result_path.read_text())
    if real_shell_result.get('status') != 'ok':
        errors.append(f'phase1-real-shell-success: status should be ok, got {real_shell_result.get("status")}')
    if real_shell_result.get('exit_code') != 0:
        errors.append(f'phase1-real-shell-success: exit_code should be 0, got {real_shell_result.get("exit_code")}')
    if 'hello' not in real_shell_result.get('stdout', ''):
        errors.append('phase1-real-shell-success: stdout should contain hello')
    if 'command' not in real_shell_result:
        errors.append('phase1-real-shell-success: result should contain command field')
    if 'duration_ms' not in real_shell_result:
        errors.append('phase1-real-shell-success: result should contain duration_ms field')

# Phase 1A: real-shell-failure-classified — failure classified and recorded
real_fail_dir = base / 'real-shell-failure-classified'
failure_store_path = real_fail_dir / 'failure-records.json'
if not failure_store_path.exists():
    errors.append('phase1-real-shell-failure-classified: failure-records.json should exist')
else:
    failure_store = json.loads(failure_store_path.read_text())
    if len(failure_store.get('records', [])) == 0:
        errors.append('phase1-real-shell-failure-classified: failure store should have at least one record')
    else:
        rec = failure_store['records'][0]
        if 'task_fingerprint' not in rec:
            errors.append('phase1-real-shell-failure-classified: failure record should have task_fingerprint')
        else:
            fp = rec['task_fingerprint']
            if 'raw_descriptor' not in fp or 'normalized_descriptor' not in fp or 'matching_key' not in fp:
                errors.append('phase1-real-shell-failure-classified: task_fingerprint must have raw_descriptor, normalized_descriptor, matching_key')
        if rec.get('error_class') not in ('path_or_missing_file', 'unknown'):
            errors.append(f'phase1-real-shell-failure-classified: error_class should be path_or_missing_file, got {rec.get("error_class")}')
        if rec.get('asset_version') != 2:
            errors.append('phase1-real-shell-failure-classified: failure record should have asset_version 2')
        if not rec.get('avoidance_hints'):
            errors.append('phase1-real-shell-failure-classified: failure record should have avoidance_hints')
        else:
            for hint in rec['avoidance_hints']:
                if hint.get('kind') not in ('append_flags', 'set_env', 'rewrite_cwd', 'set_timeout'):
                    errors.append(f'phase1-real-shell-failure-classified: avoidance hint kind {hint.get("kind")} not in allowed set')

# Verify failure store has NO entries in success pattern store
real_fail_patterns_path = real_fail_dir / 'success-patterns.json'
if real_fail_patterns_path.exists():
    fail_patterns = json.loads(real_fail_patterns_path.read_text())
    for p in fail_patterns.get('patterns', []):
        if 'failure' in p.get('lifecycle_state', '') or 'failure' in p.get('pattern_id', ''):
            errors.append('phase1-real-shell-failure-classified: failure data should NOT be in success pattern store')

# Phase 1D: real-experience-avoids-failure — Run 1 fails, Run 2 succeeds via hints
avoid_dir = base / 'real-experience-avoids-failure'
avoid_state_run1 = avoid_dir / 'execution-state-run1.json'
avoid_state_run2 = avoid_dir / 'execution-state-run2.json'
if not avoid_state_run1.exists():
    errors.append('phase1-real-experience-avoids-failure: run1 state should exist')
else:
    avoid_s1 = json.loads(avoid_state_run1.read_text())
    if avoid_s1.get('status') != 'blocked':
        errors.append(f'phase1-real-experience-avoids-failure: run1 should be blocked, got {avoid_s1.get("status")}')
if not avoid_state_run2.exists():
    errors.append('phase1-real-experience-avoids-failure: run2 state should exist')
else:
    avoid_state2 = json.loads(avoid_state_run2.read_text())
    artifacts2 = avoid_state2.get('artifacts', {})
    # Blocker 1 hard gate: Run 2 must succeed (outcome changed by hints)
    if avoid_state2.get('status') != 'completed':
        errors.append(f'phase1-real-experience-avoids-failure: run2 must complete (outcome must change), got {avoid_state2.get("status")}')
    # Check that experience hints were assembled
    hints_json = artifacts2.get('experience_hints')
    if not hints_json:
        errors.append('phase1-real-experience-avoids-failure: run2 should have experience_hints artifact')
    else:
        hints = json.loads(hints_json) if isinstance(hints_json, str) else hints_json
        if not hints.get('avoid'):
            errors.append('phase1-real-experience-avoids-failure: run2 experience_hints.avoid should not be empty')
        else:
            has_set_env = any(h.get('kind') == 'set_env' for h in hints['avoid'])
            if not has_set_env:
                errors.append('phase1-real-experience-avoids-failure: avoidance hints should include set_env for the missing env var')
    # Check that task_fingerprint was recorded
    if not artifacts2.get('task_fingerprint'):
        errors.append('phase1-real-experience-avoids-failure: run2 should have task_fingerprint artifact')
    # Check execution result shows experience was applied
    avoid_result_path = avoid_dir / 'runtime-execution-result.json'
    if avoid_result_path.exists():
        avoid_result = json.loads(avoid_result_path.read_text())
        applied = avoid_result.get('experience_applied', [])
        if not applied:
            errors.append('phase1-real-experience-avoids-failure: run2 execution result should show experience_applied is not empty')
        # Verify the applied hint actually set the env var
        set_env_applied = [a for a in applied if a.get('kind') == 'set_env']
        if not set_env_applied:
            errors.append('phase1-real-experience-avoids-failure: run2 should have applied a set_env hint')

# Phase 1E: real-experience-replay — task_fingerprint on success side (Blocker 2)
replay_dir = base / 'real-experience-replay'
replay_run1_state = json.loads((replay_dir / 'execution-state-run1.json').read_text())
replay_run2_state = json.loads((replay_dir / 'execution-state-run2.json').read_text())
if replay_run1_state.get('status') != 'completed':
    errors.append('phase1-real-experience-replay: run1 should complete')
if replay_run2_state.get('status') != 'completed':
    errors.append('phase1-real-experience-replay: run2 should complete')
# Both runs must have task_fingerprint
replay_run1_fp = replay_run1_state.get('artifacts', {}).get('task_fingerprint')
replay_run2_fp = replay_run2_state.get('artifacts', {}).get('task_fingerprint')
if not replay_run1_fp:
    errors.append('phase1-real-experience-replay: run1 must have task_fingerprint artifact')
if not replay_run2_fp:
    errors.append('phase1-real-experience-replay: run2 must have task_fingerprint artifact')
# Success patterns store must have entry with task_fingerprint
replay_patterns_path = replay_dir / 'success-patterns.json'
if replay_patterns_path.exists():
    replay_patterns = json.loads(replay_patterns_path.read_text())
    replay_pats = replay_patterns.get('patterns', [])
    has_task_fp_in_pattern = any(p.get('task_fingerprint') for p in replay_pats)
    if not has_task_fp_in_pattern:
        errors.append('phase1-real-experience-replay: success pattern must have task_fingerprint for experience loop closure')
else:
    errors.append('phase1-real-experience-replay: success-patterns.json should exist')

# Add phase1 scenarios to expected dict
summary['real-shell-success'] = {
    'status': real_shell_success_state.get('status'),
    'phase': real_shell_success_state.get('phase'),
    'execution_kind': real_shell_success_state.get('artifacts', {}).get('execution_kind'),
}

# ═══════════════════════════════════════════════════════════════
# Platform 1: Fingerprint safety + two-level pattern selection
# ═══════════════════════════════════════════════════════════════

import polaris_task_fingerprint as ptf

# P1-fingerprint-1: cp a b != cp b a (positional arg order preserved)
fp_ab = ptf.compute('cp a b', '/tmp')
fp_ba = ptf.compute('cp b a', '/tmp')
if fp_ab['matching_key'] == fp_ba['matching_key']:
    errors.append('P1-fingerprint: cp a b and cp b a must produce different fingerprints')

# P1-fingerprint-2: flags sort correctly (--flag-b --flag-a == --flag-a --flag-b)
fp_fb = ptf.compute('cmd --flag-b --flag-a', '/tmp')
fp_fa = ptf.compute('cmd --flag-a --flag-b', '/tmp')
if fp_fb['matching_key'] != fp_fa['matching_key']:
    errors.append('P1-fingerprint: flag ordering should be normalized')

# P1-fingerprint-3: mixed positional+flag (cmd src --flag dst != cmd dst --flag src)
fp_sfd = ptf.compute('cmd src --flag dst', '/tmp')
fp_dfs = ptf.compute('cmd dst --flag src', '/tmp')
if fp_sfd['matching_key'] == fp_dfs['matching_key']:
    errors.append('P1-fingerprint: cmd src --flag dst and cmd dst --flag src must differ')

# P1-fingerprint-4: identical commands match
fp_id1 = ptf.compute('echo hello world', '/tmp')
fp_id2 = ptf.compute('echo hello world', '/tmp')
if fp_id1['matching_key'] != fp_id2['matching_key']:
    errors.append('P1-fingerprint: identical commands must produce same fingerprint')

# P1-legacy-backfill: load_store auto-tags legacy patterns
import polaris_success_patterns as psp
import tempfile
legacy_test_store = {
    'schema_version': 1,
    'patterns': [
        {'pattern_id': 'layered-local-orchestration', 'tags': ['orchestration', 'local', 'success'],
         'trigger': 'long local task', 'confidence': 88, 'lifecycle_state': 'experimental'},
        {'pattern_id': 'specific-task', 'tags': ['orchestration', 'local', 'custom'],
         'trigger': 'deploy mysql', 'confidence': 80, 'lifecycle_state': 'validated',
         'task_fingerprint': {'matching_key': 'test123'}},
    ]
}
with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as ltf:
    json.dump(legacy_test_store, ltf)
    ltf.flush()
    loaded_legacy = psp.load_store(pathlib.Path(ltf.name))
for lp in loaded_legacy['patterns']:
    if lp['pattern_id'] == 'layered-local-orchestration' and not lp.get('legacy_family'):
        errors.append('P1-legacy-backfill: layered-local-orchestration must be tagged legacy_family=true')
    if lp['pattern_id'] == 'specific-task' and lp.get('legacy_family'):
        errors.append('P1-legacy-backfill: specific-task with task_fingerprint must NOT be tagged legacy_family')

# P1-two-level-select: strict > family when fingerprint matches
import subprocess as sp2
two_level_store = {
    'schema_version': 1,
    'patterns': [
        {'pattern_id': 'wide-family', 'tags': ['orchestration', 'local', 'success'],
         'trigger': 'long local task', 'confidence': 88, 'lifecycle_state': 'experimental',
         'modes': ['short', 'long'], 'reusable': True},
        {'pattern_id': 'strict-match', 'tags': ['orchestration', 'local'],
         'trigger': 'shell task', 'confidence': 75, 'lifecycle_state': 'experimental',
         'modes': ['short'], 'reusable': True,
         'task_fingerprint': {'matching_key': 'two_level_test_key'}},
    ]
}
with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tlf:
    json.dump(two_level_store, tlf)
    tl_path = tlf.name
# Strict hit
tl_result = sp2.run([sys.executable, str(pathlib.Path(os.environ['POLARIS_ROOT']) / 'scripts' / 'polaris_success_patterns.py'),
    'select', '--patterns', tl_path, '--tags', 'orchestration,local', '--mode', 'short',
    '--min-confidence', '50', '--task-fingerprint-json', json.dumps({'matching_key': 'two_level_test_key'})],
    capture_output=True, text=True)
tl_parsed = json.loads(tl_result.stdout)
if tl_parsed.get('match_resolution') != 'strict':
    errors.append(f'P1-two-level-select: expected strict resolution, got {tl_parsed.get("match_resolution")}')
if tl_parsed.get('selected', [{}])[0].get('pattern', {}).get('pattern_id') != 'strict-match':
    errors.append('P1-two-level-select: strict hit should select strict-match pattern')

# Family fallback when no fingerprint match
tl_result2 = sp2.run([sys.executable, str(pathlib.Path(os.environ['POLARIS_ROOT']) / 'scripts' / 'polaris_success_patterns.py'),
    'select', '--patterns', tl_path, '--tags', 'orchestration,local', '--mode', 'short',
    '--min-confidence', '50', '--task-fingerprint-json', json.dumps({'matching_key': 'nonexistent'})],
    capture_output=True, text=True)
tl_parsed2 = json.loads(tl_result2.stdout)
if tl_parsed2.get('match_resolution') != 'family_fallback':
    errors.append(f'P1-two-level-select: expected family_fallback, got {tl_parsed2.get("match_resolution")}')

# P1-hot-path-budget: orchestrator records budget check
for scenario_name in ['real-shell-success']:
    scenario_dir = base / scenario_name
    state_path = scenario_dir / 'execution-state.json'
    if state_path.exists():
        s = json.loads(state_path.read_text())
        budget = s.get('artifacts', {}).get('hot_path_budget')
        if not budget:
            errors.append(f'P1-hot-path-budget: {scenario_name} must have hot_path_budget artifact')
        else:
            budget_data = json.loads(budget) if isinstance(budget, str) else budget
            if 'total_bytes' not in budget_data:
                errors.append(f'P1-hot-path-budget: {scenario_name} budget must have total_bytes')
            if 'fields' not in budget_data:
                errors.append(f'P1-hot-path-budget: {scenario_name} budget must have per-field breakdown')
            for required_field in ['selected_pattern_json', 'execution_contract_json', 'applied_rules_json', 'experience_hints_json']:
                if required_field not in budget_data.get('fields', {}):
                    errors.append(f'P1-hot-path-budget: {scenario_name} budget must measure {required_field}')

# P1-family-transfer: step3-transfer uses family_fallback (not unconditional)
transfer_target_dir2 = base / 'step3-transfer-target'
transfer_target_state2 = json.loads((transfer_target_dir2 / 'execution-state.json').read_text())
# After Platform 1, family_transfer_applied should only be true when match_resolution is family_fallback
if transfer_target_state2['artifacts'].get('family_transfer_applied', False):
    tr = transfer_target_state2['artifacts'].get('transfer_reason', '')
    if 'family-fallback' not in tr and 'family_fallback' not in tr.replace('-', '_'):
        errors.append('P1-family-transfer: transfer_reason must indicate family-fallback, not unconditional reuse')

# ── Platform 1 Day 2: Blocked fallback regression ──
import subprocess as sp_test
scripts = pathlib.Path(os.environ['POLARIS_ROOT']) / 'scripts'

# P1-fallback-state-schema: fallback_state exists in state with correct shape
for scenario_name in ['standard-repair']:
    scenario_dir = base / scenario_name
    state_path = scenario_dir / 'execution-state.json'
    if state_path.exists():
        s = json.loads(state_path.read_text())
        fb = s.get('fallback_state')
        if fb is None:
            errors.append(f'P1-fallback-state: {scenario_name} must have fallback_state')
        else:
            for key in ['attempted_adapters', 'fallback_count', 'max_fallback_attempts']:
                if key not in fb:
                    errors.append(f'P1-fallback-state: {scenario_name} fallback_state missing {key}')

# P1-adapter-exclude: polaris_adapters.py select --exclude-adapters filters correctly
import subprocess as sp_test
adapter_exclude_result = sp_test.run([
    sys.executable, str(scripts / 'polaris_adapters.py'), 'select',
    '--registry', str(base / 'standard-success' / 'adapter-registry.json'),
    '--capabilities', 'local-exec,reporting',
    '--mode', 'short',
    '--execution-profile', 'standard',
    '--max-trust', 'workspace',
    '--max-cost', '5',
    '--failure-type', 'moderate_local_task',
    '--require-durable-status', 'no',
    '--verify-prereqs', 'no',
    '--exclude-adapters', 'bash-runner',
], capture_output=True, text=True)
if adapter_exclude_result.returncode == 0:
    exclude_parsed = json.loads(adapter_exclude_result.stdout)
    for sel in exclude_parsed.get('selected', []):
        if sel.get('adapter', {}).get('tool') == 'bash-runner':
            errors.append('P1-adapter-exclude: bash-runner should be excluded but was selected')

# P1-operator-summary: report --output-mode operator_summary must not leak internal state keys
op_summary_result = sp_test.run([
    sys.executable, str(scripts / 'polaris_report.py'),
    '--run-id', 'test-op-summary',
    '--phase', 'complete',
    '--status', 'completed',
    '--summary', 'Test completed',
    '--output-mode', 'operator_summary',
    '--selected-adapter', 'bash-runner',
    '--active-rule-layers', 'hard,soft',
    '--state-node', 'completed',
], capture_output=True, text=True)
if op_summary_result.returncode != 0:
    errors.append(f'P1-operator-summary: report failed: {op_summary_result.stderr}')
else:
    op_event = json.loads(op_summary_result.stdout)
    leaked_keys = {'active_rule_layers', 'selected_adapter', 'state_node', 'active_branch',
                   'selected_pattern', 'references', 'summary_outcome',
                   'lifecycle_stage', 'started_at', 'last_heartbeat_at', 'completed_at',
                   'state_density', 'event_budget'}
    found_leaked = leaked_keys.intersection(set(op_event.keys()))
    if found_leaked:
        errors.append(f'P1-operator-summary: internal keys leaked to operator view: {sorted(found_leaked)}')

# P1-diagnostic-detail: report --output-mode diagnostic_detail preserves all keys
diag_result = sp_test.run([
    sys.executable, str(scripts / 'polaris_report.py'),
    '--run-id', 'test-diag',
    '--phase', 'complete',
    '--status', 'completed',
    '--summary', 'Test completed',
    '--output-mode', 'diagnostic_detail',
    '--selected-adapter', 'bash-runner',
    '--active-rule-layers', 'hard,soft',
], capture_output=True, text=True)
if diag_result.returncode != 0:
    errors.append(f'P1-diagnostic-detail: report failed: {diag_result.stderr}')
else:
    diag_event = json.loads(diag_result.stdout)
    if 'selected_adapter' not in diag_event:
        errors.append('P1-diagnostic-detail: diagnostic mode must include selected_adapter')

# P1-skill-version: SKILL.md must declare platform 1
skill_md = (base / '..' / 'SKILL.md').resolve()
if skill_md.exists():
    skill_text = skill_md.read_text()
    if 'platform: 1' not in skill_text and 'Platform 1' not in skill_text:
        errors.append('P1-skill-version: SKILL.md must declare Platform 1')

# ── Platform 1 Day 2: P0 regression gaps ──

# P1-fallback-record-and-resume: fallback-record writes adapter, resume restores attempted set
import tempfile as _tmpfb
_fb_state_dir = tempfile.mkdtemp(prefix='p1-fb-resume-')
_fb_state_path = os.path.join(_fb_state_dir, 'execution-state.json')
# init
sp_test.run([sys.executable, str(scripts / 'polaris_state.py'), 'init', '--state', _fb_state_path, '--goal', 'test', '--mode', 'short', '--execution-profile', 'standard'], capture_output=True, text=True)
# record first blocked adapter
sp_test.run([sys.executable, str(scripts / 'polaris_state.py'), 'fallback-record', '--state', _fb_state_path, '--adapter', 'adapter-a', '--max-fallback-attempts', '3'], capture_output=True, text=True)
# record second blocked adapter
sp_test.run([sys.executable, str(scripts / 'polaris_state.py'), 'fallback-record', '--state', _fb_state_path, '--adapter', 'adapter-b', '--max-fallback-attempts', '3'], capture_output=True, text=True)
_fb_state = json.loads(pathlib.Path(_fb_state_path).read_text())
_fb = _fb_state.get('fallback_state', {})
if set(_fb.get('attempted_adapters', [])) != {'adapter-a', 'adapter-b'}:
    errors.append(f'P1-fallback-record-resume: attempted_adapters should be {{adapter-a, adapter-b}}, got {_fb.get("attempted_adapters")}')
if _fb.get('fallback_count') != 2:
    errors.append(f'P1-fallback-record-resume: fallback_count should be 2, got {_fb.get("fallback_count")}')
if _fb.get('max_fallback_attempts') != 3:
    errors.append(f'P1-fallback-record-resume: max_fallback_attempts should be frozen at 3, got {_fb.get("max_fallback_attempts")}')

# P1-nonrepair-stop-persisted: block --nonrepair-stop true persists boolean in state_machine.blocked
_nr_state_dir = tempfile.mkdtemp(prefix='p1-nr-stop-')
_nr_state_path = os.path.join(_nr_state_dir, 'execution-state.json')
sp_test.run([sys.executable, str(scripts / 'polaris_state.py'), 'init', '--state', _nr_state_path, '--goal', 'test', '--mode', 'short', '--execution-profile', 'standard'], capture_output=True, text=True)
sp_test.run([sys.executable, str(scripts / 'polaris_state.py'), 'block', '--state', _nr_state_path, '--reason', 'nonrepair denial test', '--references', '', '--nonrepair-stop', 'true'], capture_output=True, text=True)
_nr_state = json.loads(pathlib.Path(_nr_state_path).read_text())
_nr_blocked = _nr_state.get('state_machine', {}).get('blocked', {})
if _nr_blocked.get('nonrepair_stop') is not True:
    errors.append(f'P1-nonrepair-stop: blocked.nonrepair_stop should be True, got {_nr_blocked.get("nonrepair_stop")}')
# Verify false case
_nr2_state_dir = tempfile.mkdtemp(prefix='p1-nr-stop2-')
_nr2_state_path = os.path.join(_nr2_state_dir, 'execution-state.json')
sp_test.run([sys.executable, str(scripts / 'polaris_state.py'), 'init', '--state', _nr2_state_path, '--goal', 'test', '--mode', 'short', '--execution-profile', 'standard'], capture_output=True, text=True)
sp_test.run([sys.executable, str(scripts / 'polaris_state.py'), 'block', '--state', _nr2_state_path, '--reason', 'normal block test', '--references', '', '--nonrepair-stop', 'false'], capture_output=True, text=True)
_nr2_state = json.loads(pathlib.Path(_nr2_state_path).read_text())
_nr2_blocked = _nr2_state.get('state_machine', {}).get('blocked', {})
if _nr2_blocked.get('nonrepair_stop') is not False:
    errors.append(f'P1-nonrepair-stop: blocked.nonrepair_stop should be False for normal block, got {_nr2_blocked.get("nonrepair_stop")}')

# P1-operator-summary-event-log: event-log must respect --output-mode operator_summary (no internal key leak)
_evlog_dir = tempfile.mkdtemp(prefix='p1-evlog-')
_evlog_path = os.path.join(_evlog_dir, 'test-events.jsonl')
# Create a minimal authoritative state file for the test
_auth_state = {
    'status': 'in_progress', 'phase': 'execute', 'progress_pct': '50',
    'current_step': 'Running', 'next_action': 'Wait',
    'state_machine': {'node': 'executing', 'blocked': {}, 'active_branch': 'b1'},
    'artifacts': {'selected_adapter': 'bash-runner', 'selected_pattern': 'p1'},
    'summary_outcome': 'internal detail', 'references': ['ref1'],
    'rule_context': {'active_layers': ['hard', 'soft']},
    'execution_profile': 'standard', 'state_density': 'normal', 'event_budget': 10,
    'runtime': {'lifecycle_stage': 'running', 'started_at': '2026-01-01', 'last_heartbeat_at': '2026-01-01', 'completed_at': None},
}
_auth_state_path = os.path.join(_evlog_dir, 'auth-state.json')
pathlib.Path(_auth_state_path).write_text(json.dumps(_auth_state))
_evlog_result = sp_test.run([
    sys.executable, str(scripts / 'polaris_report.py'),
    '--run-id', 'test-evlog',
    '--phase', 'execute',
    '--status', 'in_progress',
    '--summary', 'Test',
    '--output-mode', 'operator_summary',
    '--selected-adapter', 'bash-runner',
    '--active-rule-layers', 'hard,soft',
    '--state-node', 'executing',
    '--authoritative-state', _auth_state_path,
    '--event-log', _evlog_path,
], capture_output=True, text=True)
if _evlog_result.returncode != 0:
    errors.append(f'P1-operator-summary-event-log: report failed: {_evlog_result.stderr}')
else:
    _evlog_lines = pathlib.Path(_evlog_path).read_text().strip().split('\n')
    _evlog_event = json.loads(_evlog_lines[-1])
    _evlog_leaked_keys = {'selected_adapter', 'state_node', 'active_branch',
                          'selected_pattern', 'references', 'summary_outcome',
                          'lifecycle_stage', 'started_at', 'last_heartbeat_at', 'completed_at',
                          'state_density', 'event_budget'}
    _evlog_found_leaked = _evlog_leaked_keys.intersection(set(_evlog_event.keys()))
    if _evlog_found_leaked:
        errors.append(f'P1-operator-summary-event-log: event-log leaks internal keys under operator_summary: {sorted(_evlog_found_leaked)}')

# P1-diagnostic-event-log: diagnostic_detail mode still includes all keys in event-log
_diag_evlog_path = os.path.join(_evlog_dir, 'test-diag-events.jsonl')
_diag_evlog_result = sp_test.run([
    sys.executable, str(scripts / 'polaris_report.py'),
    '--run-id', 'test-diag-evlog',
    '--phase', 'execute',
    '--status', 'in_progress',
    '--summary', 'Test',
    '--output-mode', 'diagnostic_detail',
    '--selected-adapter', 'bash-runner',
    '--active-rule-layers', 'hard,soft',
    '--state-node', 'executing',
    '--authoritative-state', _auth_state_path,
    '--event-log', _diag_evlog_path,
], capture_output=True, text=True)
if _diag_evlog_result.returncode != 0:
    errors.append(f'P1-diagnostic-event-log: report failed: {_diag_evlog_result.stderr}')
else:
    _diag_evlog_lines = pathlib.Path(_diag_evlog_path).read_text().strip().split('\n')
    _diag_evlog_event = json.loads(_diag_evlog_lines[-1])
    if 'selected_adapter' not in _diag_evlog_event:
        errors.append('P1-diagnostic-event-log: diagnostic mode event-log must include selected_adapter')
    if 'summary_outcome' not in _diag_evlog_event:
        errors.append('P1-diagnostic-event-log: diagnostic mode event-log must include summary_outcome')

# ── Platform 1 Day 2: additional negative-path regressions ──

# P1-old-state-migration: old state with blocked dict but no nonrepair_stop must backfill False
_old_state_dir = tempfile.mkdtemp(prefix='p1-old-migrate-')
_old_state_path = os.path.join(_old_state_dir, 'execution-state.json')
# Write a synthetic old-format state: blocked exists but lacks nonrepair_stop
_old_state = {
    'schema_version': 6,
    'status': 'blocked', 'phase': 'blocked', 'goal': 'test', 'mode': 'short',
    'execution_profile': 'standard', 'progress_pct': '60',
    'current_step': 'Blocked', 'next_action': 'Manual',
    'state_machine': {
        'node': 'blocked',
        'active_branch': None, 'branches': [], 'history': [], 'history_summary': [],
        'recovery': [],
        'blocked': {'is_blocked': True, 'reason': 'old format test', 'references': []},
        'allowed_transitions': {},
    },
    'rule_context': {'active_layers': ['hard', 'soft'], 'applied_rules': []},
    'fallback_state': {'attempted_adapters': ['old-adapter'], 'fallback_count': 1, 'max_fallback_attempts': 2},
    'summary_outcome': 'old format test',
    'updated_at': '2026-01-01T00:00:00Z',
}
pathlib.Path(_old_state_path).write_text(json.dumps(_old_state))
# Any state read through polaris_state.py should trigger backfill
_old_migrate_result = sp_test.run([
    sys.executable, str(scripts / 'polaris_state.py'), 'heartbeat',
    '--state', _old_state_path,
], capture_output=True, text=True)
if _old_migrate_result.returncode != 0:
    errors.append(f'P1-old-state-migration: heartbeat on old state failed: {_old_migrate_result.stderr}')
else:
    _migrated = json.loads(pathlib.Path(_old_state_path).read_text())
    _migrated_blocked = _migrated.get('state_machine', {}).get('blocked', {})
    if 'nonrepair_stop' not in _migrated_blocked:
        errors.append('P1-old-state-migration: backfill must add nonrepair_stop to existing blocked dict')
    elif _migrated_blocked['nonrepair_stop'] is not False:
        errors.append(f'P1-old-state-migration: backfill nonrepair_stop must be False, got {_migrated_blocked["nonrepair_stop"]}')

# P1-fallback-reset-refreeze: after fallback-reset, next fallback-record must re-freeze max
_rf_state_dir = tempfile.mkdtemp(prefix='p1-refreeze-')
_rf_state_path = os.path.join(_rf_state_dir, 'execution-state.json')
sp_test.run([sys.executable, str(scripts / 'polaris_state.py'), 'init', '--state', _rf_state_path, '--goal', 'test', '--mode', 'short', '--execution-profile', 'standard'], capture_output=True, text=True)
# First record: freeze at 3
sp_test.run([sys.executable, str(scripts / 'polaris_state.py'), 'fallback-record', '--state', _rf_state_path, '--adapter', 'a1', '--max-fallback-attempts', '3'], capture_output=True, text=True)
# Reset
sp_test.run([sys.executable, str(scripts / 'polaris_state.py'), 'fallback-reset', '--state', _rf_state_path], capture_output=True, text=True)
_rf_after_reset = json.loads(pathlib.Path(_rf_state_path).read_text())
if _rf_after_reset.get('fallback_state', {}).get('max_fallback_attempts') != 0:
    errors.append('P1-fallback-reset-refreeze: after reset, max_fallback_attempts must be 0')
# Re-record with different count: should freeze at new value 5
sp_test.run([sys.executable, str(scripts / 'polaris_state.py'), 'fallback-record', '--state', _rf_state_path, '--adapter', 'b1', '--max-fallback-attempts', '5'], capture_output=True, text=True)
_rf_refrozen = json.loads(pathlib.Path(_rf_state_path).read_text())
if _rf_refrozen.get('fallback_state', {}).get('max_fallback_attempts') != 5:
    errors.append(f'P1-fallback-reset-refreeze: after reset+record, max should re-freeze at 5, got {_rf_refrozen.get("fallback_state", {}).get("max_fallback_attempts")}')

# P1-emit-progress-default-mode: emit_progress without explicit output_mode must default to diagnostic_detail
# We test this by calling polaris_report.py without --output-mode and verifying it defaults to diagnostic_detail
_dflt_evlog_dir = tempfile.mkdtemp(prefix='p1-dflt-mode-')
_dflt_evlog_path = os.path.join(_dflt_evlog_dir, 'dflt-events.jsonl')
_dflt_auth_path = os.path.join(_dflt_evlog_dir, 'auth-state.json')
pathlib.Path(_dflt_auth_path).write_text(json.dumps({
    'status': 'in_progress', 'phase': 'execute', 'progress_pct': '50',
    'current_step': 'Running', 'next_action': 'Wait',
    'state_machine': {'node': 'executing', 'blocked': {}, 'active_branch': 'b1'},
    'artifacts': {'selected_adapter': 'bash-runner', 'selected_pattern': 'p1'},
    'summary_outcome': 'internal detail', 'references': ['ref1'],
    'rule_context': {'active_layers': ['hard', 'soft']},
    'execution_profile': 'standard', 'state_density': 'normal', 'event_budget': 10,
    'runtime': {'lifecycle_stage': 'running', 'started_at': '2026-01-01', 'last_heartbeat_at': '2026-01-01', 'completed_at': None},
}))
# No --output-mode flag = default diagnostic_detail
_dflt_result = sp_test.run([
    sys.executable, str(scripts / 'polaris_report.py'),
    '--run-id', 'test-dflt',
    '--phase', 'execute',
    '--status', 'in_progress',
    '--summary', 'Test default',
    '--selected-adapter', 'bash-runner',
    '--active-rule-layers', 'hard,soft',
    '--state-node', 'executing',
    '--authoritative-state', _dflt_auth_path,
    '--event-log', _dflt_evlog_path,
], capture_output=True, text=True)
if _dflt_result.returncode != 0:
    errors.append(f'P1-emit-progress-default-mode: report failed: {_dflt_result.stderr}')
else:
    # Default mode should be diagnostic_detail: event-log must contain full keys
    _dflt_evlog_event = json.loads(pathlib.Path(_dflt_evlog_path).read_text().strip().split('\n')[-1])
    if 'selected_adapter' not in _dflt_evlog_event:
        errors.append('P1-emit-progress-default-mode: default mode event-log must include selected_adapter (diagnostic_detail)')
    if 'summary_outcome' not in _dflt_evlog_event:
        errors.append('P1-emit-progress-default-mode: default mode event-log must include summary_outcome (diagnostic_detail)')
    # stdout should also be diagnostic_detail
    _dflt_stdout_event = json.loads(_dflt_result.stdout)
    if 'selected_adapter' not in _dflt_stdout_event:
        errors.append('P1-emit-progress-default-mode: default mode stdout must include selected_adapter (diagnostic_detail)')

# ── Platform 1 e2e: nonrepair_stop → resume → hard stop ──
# Verify via state file (authoritative) after resume run 2
_nr_e2e_dir = base / 'resume-nonrepair-hardstop'
_nr_e2e_state = _nr_e2e_dir / 'execution-state.json'
if _nr_e2e_state.exists():
    _nr_e2e = json.loads(_nr_e2e_state.read_text())
    _nr_e2e_blocked = _nr_e2e.get('state_machine', {}).get('blocked', {})
    # After resume, state must still be blocked (hard stop prevented fallback)
    if _nr_e2e.get('status') != 'blocked':
        errors.append(f'P1-e2e-nonrepair-hardstop: after resume, status must be blocked, got {_nr_e2e.get("status")}')
    # nonrepair_stop must be persisted from run 1
    if _nr_e2e_blocked.get('nonrepair_stop') is not True:
        errors.append(f'P1-e2e-nonrepair-hardstop: nonrepair_stop must be True, got {_nr_e2e_blocked.get("nonrepair_stop")}')
    # summary_outcome must mention hard-stop / nonrepair denial (written by resume hard stop path)
    _nr_summary = _nr_e2e.get('summary_outcome', '')
    if 'nonrepair' not in _nr_summary.lower() and 'hard-stop' not in _nr_summary.lower() and 'Fallback blocked' not in _nr_summary:
        errors.append(f'P1-e2e-nonrepair-hardstop: summary_outcome must indicate nonrepair hard stop, got: {_nr_summary}')
else:
    errors.append('P1-e2e-nonrepair-hardstop: state file missing after run')

# ── Platform 1 e2e: attempted_adapters → resume → adapter exhaustion ──
# With 1 adapter in registry, after run 1 blocks it, resume must hit exhaustion hard stop
_ex_e2e_dir = base / 'resume-adapter-exhaust'
_ex_e2e_state = _ex_e2e_dir / 'execution-state.json'
if _ex_e2e_state.exists():
    _ex_e2e = json.loads(_ex_e2e_state.read_text())
    _ex_e2e_fb = _ex_e2e.get('fallback_state', {})
    # State must be blocked after adapter exhaustion
    if _ex_e2e.get('status') != 'blocked':
        errors.append(f'P1-e2e-adapter-exhaust: after resume, status must be blocked, got {_ex_e2e.get("status")}')
    # attempted_adapters must contain at least one adapter
    if not _ex_e2e_fb.get('attempted_adapters'):
        errors.append('P1-e2e-adapter-exhaust: attempted_adapters must not be empty')
    # summary must indicate exhaustion or hard stop
    _ex_summary = _ex_e2e.get('summary_outcome', '')
    if 'exhaust' not in _ex_summary.lower() and 'Fallback blocked' not in _ex_summary:
        errors.append(f'P1-e2e-adapter-exhaust: summary_outcome must indicate adapter exhaustion, got: {_ex_summary}')
else:
    errors.append('P1-e2e-adapter-exhaust: state file missing after run')

print(json.dumps(summary, indent=2, sort_keys=True))
if errors:
    print('\nASSERTION FAILURES:')
    for err in errors:
        print('-', err)
    sys.exit(1)
PY
