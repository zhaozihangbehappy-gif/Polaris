#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT_BASE="${POLARIS_REGRESSION_OUT:-$ROOT/regression-runs}"
rm -rf "$OUT_BASE"
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

python3 - <<'PY' > "$OUT_BASE/step2-strategy-conflict.json"
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path('Polaris/scripts').resolve()))
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

POLARIS_REGRESSION_OUT_DIR="$OUT_BASE" python3 - <<'PY'
import json, os, pathlib, sys
base=pathlib.Path(os.environ['POLARIS_REGRESSION_OUT_DIR'])
summary={}
errors=[]

def parse_inline_json(value):
    if value in (None, "", "{}"):
        return {} if value == "{}" else None
    return json.loads(value)

def load_efficiency_metrics(directory):
    state = json.loads((directory/'execution-state.json').read_text())
    artifact_payload = parse_inline_json(state.get('artifacts', {}).get('efficiency_metrics'))
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
}
for d in sorted(base.iterdir()):
    if not d.is_dir():
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
        efficiency = parse_inline_json(artifacts.get('efficiency_metrics'))
        if not efficiency or efficiency.get('retry_actions') != 1:
            errors.append('deep-resumed-failure: efficiency_metrics should record one retry action after resumed failure')
    if d.name == 'deep-command-output-repair':
        resumed=json.loads(artifacts.get('resumed_execution_contract', '{}'))
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
run1_contract=json.loads(run1_state['artifacts']['execution_contract'])
run2_contract=json.loads(run2_state['artifacts']['execution_contract'])
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
if not json.loads(run2_state['artifacts'].get('execution_contract_diff', '{}')):
    errors.append('step2-learning-repeat-success: second run should persist non-empty contract diff')
if not json.loads(run2_state['artifacts'].get('validator_diff', '{}')):
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
repair_run2_contract=json.loads(repair_run2_state['artifacts']['execution_contract'])
repair_run2_validator=repair_run2_contract.get('validator', {})
repair_run2_validation=json.loads((repair_dir/'runtime-validation-result-run2.json').read_text())
repair_diff=json.loads(repair_run2_state['artifacts'].get('execution_contract_diff', '{}'))
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
    case_contract = json.loads(case_state['artifacts']['execution_contract'])
    assert_efficiency_budget(case_name, case_state, case_efficiency, case_contract)

success_run2_state_full, success_run2_efficiency = load_efficiency_metrics(success_dir)
repair_run2_state_full, repair_run2_efficiency = load_efficiency_metrics(repair_dir)
assert_efficiency_budget('step2-learning-repeat-success', success_run2_state_full, success_run2_efficiency, run2_contract)
assert_efficiency_budget('step2-learning-repeat-repair', repair_run2_state_full, repair_run2_efficiency, repair_run2_contract)

transfer_source_dir = base/'step3-transfer-source'
transfer_target_dir = base/'step3-transfer-target'
transfer_source_state, transfer_source_efficiency = load_efficiency_metrics(transfer_source_dir)
transfer_target_state, transfer_target_efficiency = load_efficiency_metrics(transfer_target_dir)
transfer_source_contract = json.loads(transfer_source_state['artifacts']['execution_contract'])
transfer_target_contract = json.loads(transfer_target_state['artifacts']['execution_contract'])
assert_efficiency_budget('step3-transfer-source', transfer_source_state, transfer_source_efficiency, transfer_source_contract)
assert_efficiency_budget('step3-transfer-target', transfer_target_state, transfer_target_efficiency, transfer_target_contract)
if transfer_source_state.get('goal') == transfer_target_state.get('goal'):
    errors.append('step3-transfer: source and target goals must differ to prove cross-task transfer')
if json.loads(transfer_target_state['artifacts'].get('family_transfer_applied', 'false')) is not True:
    errors.append('step3-transfer: target should record family_transfer_applied=true')
if not transfer_target_state['artifacts'].get('transfer_source_pattern'):
    errors.append('step3-transfer: target should record transfer_source_pattern')
if not transfer_target_state['artifacts'].get('transfer_reason'):
    errors.append('step3-transfer: target should record transfer_reason')
if not json.loads(transfer_target_state['artifacts'].get('transfer_contract_diff', '{}')):
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
sys.path.insert(0, str(pathlib.Path('Polaris/scripts').resolve()))
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
sys.path.insert(0, str(pathlib.Path('Polaris/scripts').resolve()))
import polaris_validator as pv
import polaris_orchestrator as po
import polaris_state as ps
success_contract = json.loads(run2_state['artifacts']['execution_contract'])
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
    pathlib.Path('Polaris/scripts').resolve(),
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
if not parse_inline_json(consolidated_state.get('artifacts', {}).get('learning_summary')):
    errors.append('step3-consolidation-failure: learning_summary should be recorded even when consolidation fails')
print(json.dumps(summary, indent=2, sort_keys=True))
if errors:
    print('\nASSERTION FAILURES:')
    for err in errors:
        print('-', err)
    sys.exit(1)
PY
