---
name: polaris
description: Local-first modular execution skill for long or failure-prone tasks that need explicit planning, layered rules, success-pattern capture, bounded self-repair, richer adapter selection, and resumable state. Use when Codex needs auditable orchestration for multi-step local work, especially when planner/repair/reporter/adapters/rule-store coordination must stay concise, reviewable, and preserve explicit runtime stop/retry semantics.
---

# Polaris

Use Polaris to turn complex local work into a small auditable runtime with explicit state, bounded repair, and reusable patterns.

## Core Loop

1. Initialize run state with `scripts/polaris_state.py init`.
2. Build or refresh the plan with `scripts/polaris_planner.py`.
3. Select active rule layers and candidate adapters before execution.
4. Materialize an execution contract, invoke the selected adapter, and validate the produced runtime artifact.
5. Emit compact progress events with `scripts/polaris_report.py`.
6. On failure, diagnose with `scripts/polaris_repair.py`, then generate only bounded local repair action trees with `scripts/polaris_repair_actions.py`.
7. Capture validated rules with `scripts/polaris_rules.py` and success patterns with `scripts/polaris_success_patterns.py`.
8. Advance the state machine explicitly so another agent can resume from files, not memory.

## Modules

- `planner`: produces short ordered steps with phase, active rule layers, and success signals
- `state-machine`: tracks `intake -> planning -> ready -> executing -> validating -> completed`, with `repairing` and `blocked` branches
- `reporter`: emits JSON events and a current-status snapshot
- `task-runner`: executes the current local contract and writes a concrete runtime result artifact for validation
- `repair-engine`: classifies failures into repairable paths versus explicit stop classifications
- `repair-action-layer`: turns diagnosis into controlled local action trees or explicit stops
- `rule-store`: stores `hard`, `soft`, and `experimental` rules
- `success-pattern-store`: captures reusable sequences with confidence, promotion, demotion, expiry, and adapter linkage
- `adapters`: registers local tools declaratively and ranks them by capability, trust level, mode, cost, and fallback shape

## Rule Layering

- `hard`: deterministic stop/route rules and invariants
- `soft`: validated heuristics that usually improve outcomes
- `experimental`: narrow trial guidance that must remain easy to remove

Apply `hard` first, then `soft`, then `experimental`. Promote guidance only when local evidence justifies it.

## Success Capture

Record two things separately:

- rules: what to do when a trigger recurs
- success patterns: which sequence, adapter choice, and validation path led to a good outcome

Only capture success patterns that are concise, local, and inspectable.

## When To Load References

- `references/architecture.md`: module map and data flow
- `references/state-and-rules.md`: state schema, rule layering, success-pattern schema
- `references/adapters.md`: adapter registration and selection
- `references/orchestrator.md`: orchestration flow and examples
- `references/stop-classifications.md`: runtime stop classifications and operator guidance semantics
- `references/repair-actions.md`: repair-plan scope and execution limits
- `references/usage-patterns.md`: short-task, long-task, and resume patterns
- `references/iterative-excellence.md`: how Polaris should improve without becoming opaque
- `references/agility.md`: how Polaris keeps deep capability while staying fast and light in foreground execution

## Operating Rules

- Keep everything local-first and plain-text or JSON.
- Preserve explicit stop classifications instead of collapsing every failure into repair.
- Do not learn from non-repair stop classifications; keep them as audit facts only.
- Prefer the lightest execution profile that still preserves correctness and clear runtime semantics.
- Keep hot-path execution thin; push heavier learning/consolidation work to phase end or deferred cold paths when possible.
- Make state transitions explicit before pausing or retrying.
- Use adapter selection instead of hard-coding tool-specific logic into the orchestrator.
- Validate execution through concrete output artifacts, not only subprocess return codes.
- Capture lessons only after observed local evidence.
- Keep experimental guidance narrow and easy to delete.

## Minimal Workflow

### Short Task

1. Initialize state in `short` mode.
2. Build a 3-4 step plan.
3. Select a local adapter with the lowest adequate trust/cost.
4. Execute, report once or twice, validate, and optionally record one success pattern.

### Long Task

1. Initialize state in `long` mode with resume artifacts.
2. Move through the state machine explicitly.
3. On failure, branch into `repairing`, collect evidence, and return to `ready` or `executing`.
4. Capture layered rules and success patterns only after validation.
5. Leave `next_action`, active layers, and selected adapter in state before stopping.

## Machine-Readable Outputs

- state snapshot: `run_id`, `mode`, `phase`, `state_machine`, `current_step`, `next_action`
- progress event: `ts`, `run_id`, `phase`, `status`, `state_node`, `active_rule_layers`, `selected_adapter`
- repair report: `failure_type`, `confidence`, `candidate_fixes`, `retry_guidance`, `suggested_rule_layer`
- rule store: `rules[]`
- success-pattern store: `patterns[]`

Use the bundled scripts and schemas unless the task needs a small local extension.
