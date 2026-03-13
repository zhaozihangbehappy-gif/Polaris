# Polaris Orchestrator

## Purpose

`scripts/polaris_orchestrator.py` turns the modules into a runnable local flow. It remains thin on purpose: the planner plans, the rule store decides guidance, the adapter registry chooses tools, and the state machine records what happened.

## Responsibilities

- initialize state and active rule layers
- route into `micro`, `standard`, or `deep` execution profiles
- apply the matching `state_density`, `repair_depth`, and event budget
- transition through the lifecycle nodes explicitly
- select layered rules relevant to the run
- reuse sticky adapters when a recent matching fingerprint is still valid, otherwise rank adapters by capabilities, mode, trust, cost, and fallback metadata
- select reusable success patterns only when the profile budget allows it
- emit progress events and runtime surfaces according to the profile budget
- route repair through `shallow`, `medium`, or `deep` depth and record recovery references explicitly
- preserve the full repair and learning path in `deep` mode

## Profile Behavior

- `micro`: bounded plan, direct `planning -> executing`, minimal state, start/end reporting only
- `standard`: short planner, `ready` phase retained, minimal state, one event per major phase, shallow repair first
- `deep`: full existing orchestration, repair branch support, rich state, rich reporting surfaces, deep repair on first blocked execution

## Default Flow

1. `init`
2. route execution profile and density
3. `transition -> planning`
4. `plan`
5. `select rules`
6. `rank adapters`
7. optional `select patterns`
8. `transition -> executing` directly for `micro`, or `transition -> ready -> branch execution -> executing` for `standard/deep`
9. optional bounded repair pass in `micro` or `standard`, or `branch repair -> transition -> repairing -> recover -> ready -> executing` in `deep`
10. `transition -> validating -> completed`

## Example

```bash
python3 Polaris/scripts/polaris_orchestrator.py \
  --state Polaris/runtime-demo/execution-state.json \
  --goal "Demonstrate Polaris local orchestration flow" \
  --simulate-error "ModuleNotFoundError: No module named pywinauto" \
  --adapters Polaris/runtime-demo/adapters.json \
  --rules Polaris/runtime-demo/rules.json \
  --patterns Polaris/runtime-demo/success-patterns.json \
  --mode long \
  --execution-profile deep
```

```bash
python3 Polaris/scripts/polaris_orchestrator.py \
  --state Polaris/runtime-demo-micro/execution-state.json \
  --goal "Run a bounded local check" \
  --adapters Polaris/runtime-demo-micro/adapters.json \
  --rules Polaris/runtime-demo-micro/rules.json \
  --patterns Polaris/runtime-demo-micro/success-patterns.json \
  --mode short \
  --execution-profile micro
```

## Why This Matters

- Orchestration is reproducible because decisions are encoded in files.
- Repair is bounded because the orchestrator delegates to explicit repair scripts.
- Improvement is iterative because success patterns and rules are captured separately.
