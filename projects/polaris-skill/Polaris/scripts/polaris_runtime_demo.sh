#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RUNTIME_DIR="${POLARIS_RUNTIME_DIR:-$ROOT/runtime-demo}"
EXECUTION_PROFILE="${POLARIS_EXECUTION_PROFILE:-deep}"
MODE="${POLARIS_MODE:-long}"
SIMULATE_ERROR="${POLARIS_SIMULATE_ERROR-ModuleNotFoundError: No module named pywinauto}"
RESUMED_SIMULATE_ERROR="${POLARIS_RESUMED_SIMULATE_ERROR:-}"
EXECUTION_KIND="${POLARIS_EXECUTION_KIND:-auto}"
GOAL="${POLARIS_GOAL:-Demonstrate Polaris local orchestration flow}"
ANALYSIS_TARGET="${POLARIS_ANALYSIS_TARGET:-}"
mkdir -p "$RUNTIME_DIR"
# ── Compatibility gate: must pass before ANY file is written to runtime dir ──
python3 "$ROOT/scripts/polaris_compat.py" check-runtime-format --runtime-dir "$RUNTIME_DIR"
python3 "$ROOT/scripts/polaris_compat.py" check-schema --state "$RUNTIME_DIR/execution-state.json"
python3 "$ROOT/scripts/polaris_compat.py" write-runtime-format --runtime-dir "$RUNTIME_DIR"
# ── Gate passed — safe to write adapters, rules, patterns ──
ORCH_ARGS=(
  --state "$RUNTIME_DIR/execution-state.json"
  --goal "$GOAL"
  --adapters "$RUNTIME_DIR/adapters.json"
  --rules "$RUNTIME_DIR/rules.json"
  --patterns "$RUNTIME_DIR/success-patterns.json"
  --mode "$MODE"
  --execution-profile "$EXECUTION_PROFILE"
  --execution-kind "$EXECUTION_KIND"
)
if [[ -n "$SIMULATE_ERROR" ]]; then
  ORCH_ARGS+=(--simulate-error "$SIMULATE_ERROR")
fi
if [[ -n "$RESUMED_SIMULATE_ERROR" ]]; then
  ORCH_ARGS+=(--resumed-simulate-error "$RESUMED_SIMULATE_ERROR")
fi
if [[ -n "$ANALYSIS_TARGET" ]]; then
  ORCH_ARGS+=(--analysis-target "$ANALYSIS_TARGET")
fi
python3 "$ROOT/scripts/polaris_adapters.py" add \
  --registry "$RUNTIME_DIR/adapters.json" \
  --tool "python-runtime-local" \
  --tool-command "python3 <script>.py" \
  --inputs "script_path,args" \
  --capabilities "local-exec,reporting,repair-probes,durable-status,long-run,generic-runner" \
  --modes "long" \
  --prerequisites "python3" \
  --selectors "prefer for long-running local orchestration,prefer when durable status surfaces are required" \
  --failure-notes "Same interpreter constraints as python-local still apply" \
  --fallbacks "python-local,shell-local" \
  --fallback-notes "Fall back to python-local first, then shell-local if runtime surface support is unavailable" \
  --mode-preferences "long:8" \
  --trust-level "workspace" \
  --cost-hint 2 \
  --latency-hint 2 \
  --preferred-failures "missing_dependency,import_path_issue,config_parse_error" \
  --safe-retry yes \
  --notes "Preferred adapter profile for durable long-running local tasks"
python3 "$ROOT/scripts/polaris_adapters.py" add \
  --registry "$RUNTIME_DIR/adapters.json" \
  --tool "python-local" \
  --tool-command "python3 <script>.py" \
  --inputs "script_path,args" \
  --capabilities "local-exec,reporting,repair-probes,generic-runner" \
  --modes "short,long" \
  --prerequisites "python3" \
  --selectors "prefer for local JSON tooling,good default for bounded probes" \
  --failure-notes "No module named usually means the active environment is incomplete" \
  --fallbacks "shell-local" \
  --fallback-notes "Fall back to shell-local when only generic shell inspection is needed" \
  --mode-preferences "long:4,short:2" \
  --trust-level "workspace" \
  --cost-hint 1 \
  --latency-hint 1 \
  --preferred-failures "missing_dependency,import_path_issue" \
  --safe-retry yes \
  --notes "Default local execution adapter"
python3 "$ROOT/scripts/polaris_adapters.py" add \
  --registry "$RUNTIME_DIR/adapters.json" \
  --tool "file-transform-local" \
  --tool-command "python3 <script>.py" \
  --inputs "script_path,args" \
  --capabilities "local-exec,reporting,validation,file-transform,durable-status,long-run" \
  --modes "short,long" \
  --prerequisites "python3" \
  --selectors "prefer for local file transform contracts,prefer when validator reads transformed files" \
  --failure-notes "Transform contracts still depend on local filesystem writes" \
  --fallbacks "python-local,shell-local" \
  --fallback-notes "Fall back to python-local or shell-local when transform-specific execution is unavailable" \
  --mode-preferences "long:3,short:5" \
  --trust-level "workspace" \
  --cost-hint 1 \
  --latency-hint 1 \
  --preferred-failures "path_or_missing_file" \
  --safe-retry yes \
  --notes "Preferred adapter for local file transform execution contracts"
python3 "$ROOT/scripts/polaris_adapters.py" add \
  --registry "$RUNTIME_DIR/adapters.json" \
  --tool "shell-local" \
  --tool-command "bash -lc <command>" \
  --inputs "command" \
  --capabilities "local-exec,reporting,validation,repo-inspection,generic-runner,command-output,durable-status,long-run" \
  --modes "short,long" \
  --prerequisites "bash" \
  --selectors "prefer for generic shell inspection,use as broad fallback" \
  --failure-notes "PATH or command resolution issues may still apply" \
  --preferred-failures "missing_tool,path_or_missing_file,test_failure" \
  --trust-level "workspace" \
  --cost-hint 2 \
  --latency-hint 1 \
  --safe-retry yes \
  --notes "Generic shell fallback adapter"
python3 "$ROOT/scripts/polaris_adapters.py" add \
  --registry "$RUNTIME_DIR/adapters.json" \
  --tool "file-analysis-local" \
  --tool-command "python3 <script>.py" \
  --inputs "script_path,args" \
  --capabilities "local-exec,reporting,validation,file-analysis,durable-status,long-run" \
  --modes "short,long" \
  --prerequisites "python3" \
  --selectors "prefer for local file analysis contracts,prefer when validator independently re-reads source files" \
  --failure-notes "Analysis contracts depend on target file accessibility" \
  --fallbacks "python-local,shell-local" \
  --fallback-notes "Fall back to python-local or shell-local when analysis-specific execution is unavailable" \
  --mode-preferences "long:3,short:5" \
  --trust-level "workspace" \
  --cost-hint 1 \
  --latency-hint 1 \
  --preferred-failures "path_or_missing_file" \
  --safe-retry yes \
  --notes "Adapter for real file analysis with independent validation"
python3 "$ROOT/scripts/polaris_rules.py" add \
  --rules "$RUNTIME_DIR/rules.json" \
  --rule-id "stop-on-nonrepair-denial" \
  --layer hard \
  --trigger "an explicit non-repair denial appears" \
  --action "Stop and reduce scope instead of retrying the blocked path" \
  --evidence "explicit runtime stop classification" \
  --scope "all Polaris runs" \
  --tags "stop,runtime,local" \
  --validation "explicit runtime stop classification" \
  --priority 100
python3 "$ROOT/scripts/polaris_success_patterns.py" capture \
  --patterns "$RUNTIME_DIR/success-patterns.json" \
  --pattern-id "bounded-local-repair" \
  --summary "Local repair branches should stay probe-only and feed explicit recovery references" \
  --trigger "repairable local runtime failure" \
  --sequence "detect,branch,probe,recover,record" \
  --outcome "bounded recovery without crossing safeguards" \
  --evidence "$ROOT/references/repair-actions.md" \
  --tags "repair,local,orchestration" \
  --modes "long" \
  --confidence 72 \
  --lifecycle-state validated
python3 "$ROOT/scripts/polaris_orchestrator.py" "${ORCH_ARGS[@]}"
