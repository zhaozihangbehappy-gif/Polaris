# Polaris Skill Snapshot — 2026-03-13

This folder imports the previously temporary `/tmp/polaris-skill` work into the main repository so the project can resume cleanly tomorrow without relying on tmux scrollback or local scratch state.

## What Polaris is

Polaris is a local-first execution and evolution skill for longer or failure-prone tasks.

It is designed to keep:
- explicit plan and state transitions
- layered rules
- richer adapter selection
- bounded local repair
- success-pattern capture
- resumable runtime artifacts
- strong safety boundaries

## Current status

### Completed today

#### Baseline Polaris build
- modular scripts for state, planner, report, repair, repair-actions, rules, adapters, runtime, orchestrator, and success patterns
- reference docs and example runtime artifacts
- runtime demo passing

#### Success-pattern lifecycle stabilization
- repeated successful reruns no longer awkwardly demote then re-promote patterns
- `lifecycle_state` and `best_lifecycle_state` are now distinct
- evidence and confidence merge more cleanly across reruns

#### Phase 1 agility refactor
- execution profiles: `micro`, `standard`, `deep`
- state density: `minimal`, `full`
- event/runtime-surface budgets aligned to profile
- short tasks no longer default to full deep orchestration

#### Phase 2 agility refactor
- sticky adapter reuse via scenario fingerprint + lightweight cache
- repair-depth routing via `shallow -> medium -> deep`
- `micro` and `standard` no longer jump into deep repair on first failure
- deep mode still preserves the richer repair/recovery flow

## Important files

### Core
- `Polaris/SKILL.md`
- `Polaris/scripts/polaris_orchestrator.py`
- `Polaris/scripts/polaris_state.py`
- `Polaris/scripts/polaris_adapters.py`
- `Polaris/scripts/polaris_repair.py`
- `Polaris/scripts/polaris_repair_actions.py`
- `Polaris/scripts/polaris_success_patterns.py`

### Design references
- `Polaris/references/agility.md`
- `Polaris/references/orchestrator.md`
- `Polaris/references/state-and-rules.md`
- `Polaris/references/adapters.md`
- `Polaris/references/repair-actions.md`

### Spec and imported task context
- `specs/POLARIS_TASK.md`

### Useful runtime examples
- `Polaris/assets/examples/execution-state-micro.json`
- `Polaris/assets/examples/execution-state-standard.json`
- `Polaris/assets/examples/execution-state.json`
- `Polaris/assets/examples/runtime-status-micro.json`
- `Polaris/assets/examples/runtime-status-standard.json`
- `Polaris/assets/examples/runtime-status-deep.json`

## Honest current score

Polaris is now at a strong local-first 95+-direction stopping point for:
- explicit orchestration
- safety-bounded repair
- success-pattern stability
- agility-aware dispatch

It is not finished forever. The biggest remaining work is still:

## Next recommended step (tomorrow start here)

### Phase 3 — deferred learning
Implement:
- cheap online success markers
- deferred consolidation using `learning_backlog`
- moving heavier pattern/rule promotion off the hot path for non-deep runs

Goal:
- keep Polaris improving
- without letting foreground execution become slow or ceremonious

## Comparison note

A source-level comparison against `self-improving-agent` was completed today.

Short version:
- `self-improving-agent` is strong as a learning/error capture system
- Polaris is stronger as an execution/evolution runtime
- the right future direction is to absorb the best low-friction learning capture ideas without collapsing Polaris back into a markdown-log-only system

See:
- `docs/evaluation/polaris-vs-self-improving-agent-source-comparison-2026-03-13.md`

## Resume checklist

When resuming tomorrow:
1. read this file
2. read `Polaris/references/agility.md`
3. inspect `Polaris/scripts/polaris_orchestrator.py`
4. inspect `Polaris/scripts/polaris_success_patterns.py`
5. implement Phase 3 deferred learning path
6. rerun `bash Polaris/scripts/polaris_runtime_demo.sh`
7. verify micro / standard / deep still stay light in the foreground
