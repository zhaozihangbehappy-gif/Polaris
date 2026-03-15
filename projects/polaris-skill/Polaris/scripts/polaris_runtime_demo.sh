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
RESUME="${POLARIS_RESUME:-}"
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
if [[ -n "$RESUME" ]]; then
  ORCH_ARGS+=(--resume)
fi
python3 "$ROOT/scripts/polaris_bootstrap.py" bootstrap \
  --manifest "$ROOT/scripts/polaris_bootstrap.json" \
  --runtime-dir "$RUNTIME_DIR"
python3 "$ROOT/scripts/polaris_orchestrator.py" "${ORCH_ARGS[@]}"
