# Polaris Skill Snapshot — 2026-03-13

This folder imports the previously temporary `/tmp/polaris-skill` work into the main repository so the project can resume cleanly tomorrow without relying on tmux scrollback or local scratch state.

## Current Status

Polaris today is a **local-first runtime shell** for longer or failure-prone tasks.

What it already does well:
- explicit plan and state transitions
- layered rules and selected-pattern selection plus contract forwarding
- richer adapter selection with sticky reuse
- bounded repair and explicit stop/retry semantics
- deferred learning, convergence, and resumable runtime artifacts
- an executable regression harness for core demo scenarios that currently summarizes outputs rather than asserting expected behavior

What it is **not** yet:
- not yet a mature capability-growth engine
- not yet a fully real execution core
- not yet a production execution runtime with independent validators and rich adapter diversity

The current execution path is only a **partial execution core**:
- adapter selection, execution contracts, adapter invocation, artifact validation, and deep re-execution all exist
- but execution still largely collapses into the current local demo runner and its associated result artifacts
- validation is still same-stack and weakly heterogeneous: the current validator mainly checks for an output file and `status == "ok"` in an artifact produced by the same runner stack
- stop semantics are improved but not perfectly uniform yet: some `nonrepair_stop` classifications are still cleaner in diagnosis/orchestration than in the current repair action layer

### Completed work

#### Baseline Polaris build
- modular scripts for state, planner, report, repair, repair-actions, rules, adapters, runtime, orchestrator, and success patterns
- reference docs and example runtime artifacts
- runtime demo scenarios passing
- adapter-selected execution now flows through an explicit contract and invocation path instead of stopping at selection/reporting only, but still defaults to the current local demo runner in most scenarios

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

#### Phase 3 deferred learning
- lightweight online success markers now queue into state `learning_backlog`
- non-deep runs defer heavier pattern consolidation until end-of-run cold path
- deferred consolidation now clears backlog after processing so foreground flow stays light
- deep runs keep the richer immediate capture path

#### Phase 4 repair-learning decoupling
- repair learning now queues deferred `rule_candidate` and `success_marker` items instead of writing hot-path rule/pattern updates directly
- deferred learning items now carry fingerprints so repeated similar runs converge during consolidation
- bounded non-deep repair paths also consolidate queued repair learning before returning blocked state
- consolidation is now durable: failed deferred items remain in `learning_backlog` for retry instead of being dropped
- non-repair stop classifications are no longer learned as reusable repair guidance
- repair learning payloads are now specialized across the supported failure taxonomy, although the repair action layer does not yet fully consume the structured diagnosis taxonomy directly

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

## Target Definition

Polaris is being developed as OpenClaw’s long-term capability growth system.

Its target is to improve three dimensions together:
1. **runtime stability and recoverability**
2. **capability growth through executable learning**
3. **hot-path efficiency that is preserved or improved over time**

Polaris is only successful when progress in one dimension does not come from meaningful regression in the other two.

### Design law

Every new Polaris mechanism must answer at least one of these clearly:
1. Does it improve future real problem-solving ability?
2. Does it reduce hot-path cost, or at least avoid increasing it?
3. Does it make repeated tasks faster or make new tasks easier through transferable experience?

If a mechanism cannot answer any of the three, it should not be prioritized.
If it improves one dimension by materially harming the other two, it is the wrong design.

### Anti-goals

Polaris must not become:
- a state-heavy system that records more than it improves
- a learning system whose outputs do not change future execution behavior
- a runtime shell that validates its own synthetic success without real task gain
- a structure-heavy layer whose orchestration complexity grows faster than real usefulness
- an execution layer that adds hot-path drag without reducing real task cost

## Phase 5 / Phase 6 Direction

### Phase 5 — execution core first

Phase 5 exists to turn Polaris from a runtime shell into a real execution amplifier.

#### Phase 5A — real adapter execution contracts
- split executor and validator responsibilities cleanly
- introduce real execution contract types beyond the current demo runner path
- require validator diversity so execution is not self-authenticated by the same runner layer
- prove that adapter choice changes real execution behavior, not just wrappers

#### Phase 5B — executable learning
- make rules and patterns materially change future execution behavior
- first allowed policy slots: `fallback choice`, `retry policy`, `validation strategy`, `execution ordering`
- keep conflict resolution explicit: `hard` for stop/route/invariant, `soft` for default execution preference, `experimental` for candidate optimization
- require repeated-run evidence that learned guidance changes behavior and improves outcomes

#### Phase 5C — repair taxonomy coherence
- make `polaris_repair_actions.py` consume structured diagnosis instead of reclassifying from raw text
- keep `repairable` and `nonrepair_stop` semantics consistent across diagnose, action, orchestrator, learning, and operator guidance
- ensure nonrepair-stop paths do not silently continue as if they were ordinary repair flows
- feed repair results back into future execution strategy instead of leaving them as isolated records

### Phase 6 — capability growth and efficiency discipline

Phase 6 exists to make Polaris a long-term capability-growth engine without letting structure turn into process tax.

#### Phase 6A — transferable task-family learning
- move from single-run experience capture to transferable strategy capture
- let successful execution, repair, and validation strategies migrate across related task families
- require that learned abstractions change how future tasks are decomposed and executed

#### Phase 6B — measurable efficiency discipline
- establish explicit hot-path budgets for `micro`, `standard`, and `deep`
- measure step budget, state-write budget, retry budget, and selection cost
- require that new capability mechanisms preserve or improve hot-path efficiency instead of slowing real work

#### Phase 6C — asserting regression harness
- evolve regression from evidence generation into real behavior assertions
- add missing scenarios such as repeated-run convergence, malformed artifacts, resumed-failure paths, and broader repair classes
- include efficiency assertions so structure growth cannot hide execution drag

## Comparison note

A source-level comparison against `self-improving-agent` was completed today.

Current takeaway:
- `self-improving-agent` is strong as a learning/error capture system
- Polaris is aiming toward a stronger execution/evolution runtime shape, but that comparison is still directional rather than fully proven by the current implementation
- the right future direction is to absorb the best low-friction learning capture ideas without collapsing Polaris back into a markdown-log-only system

See:
- `docs/evaluation/polaris-vs-self-improving-agent-source-comparison-2026-03-13.md`

## Resume checklist

When resuming next time:
1. read this file
2. read `Polaris/references/agility.md`
3. inspect `Polaris/scripts/polaris_orchestrator.py`
4. inspect `Polaris/scripts/polaris_success_patterns.py`
5. inspect `Polaris/scripts/polaris_rules.py`
6. rerun `bash Polaris/scripts/polaris_regression.sh`
7. inspect whether the next target is richer adapter contracts, stronger rule-driven execution, or better runtime surfaces
