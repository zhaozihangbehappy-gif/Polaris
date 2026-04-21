# Polaris Architecture Contracts — Platform 1

These are hard constraints. Violating any of them is a regression.

## 1. Cold Path / Hot Path Separation

**Hot path** = everything that happens between the orchestrator receiving a
task and the adapter finishing execution (inclusive of hint injection).

**Cold path** = everything that happens after execution completes — learning
consolidation, pattern promotion, rule extraction, backlog processing.

### Rules

- The hot path MUST NOT iterate over the full pattern store or rule store.
  It receives at most the top-1 selected result.
- Learning backlog writes during execution are append-only counters;
  consolidation happens in the cold path only.

## 2. Hot Path Budget

**Definition**: the total serialized byte count of all decision-bearing JSON
fields passed to the adapter at execution time.

**Measured fields** (exhaustive — if a new field is added to the adapter
call, it MUST be added here):

- `selected_pattern_json`
- `execution_contract_json`
- `applied_rules_json`
- `experience_hints_json`

**Budget limit**: 8192 bytes (warn), 16384 bytes (exceeded). Both thresholds
are **warn-only** — they emit stderr diagnostics and record an artifact but do
not modify the execution contract or adapter inputs.

**Measurement point**: `hot_path_budget_check()` in the orchestrator, called
immediately before adapter invocation.

**Violation detection**: regression must include a scenario where injected
data approaches the limit and verify warn/exceeded diagnostics are emitted.

## 3. Pattern Selection Priority

Resolution order is strict > family fallback > no-hit.

| Level | Condition | Behavior |
|-------|-----------|----------|
| **Strict** | Pattern has `task_fingerprint` and its `matching_key` equals the query fingerprint | Selected with +1000 score bonus |
| **Family fallback** | Pattern matches by tags/trigger/mode/adapter but no fingerprint match, OR pattern is `legacy_family=true` | Selected only if no strict hit exists; marked `match_type=family` |
| **No-hit** | No pattern matches at all | Baseline execution, no pattern guidance |

Legacy Platform 0 patterns are automatically tagged `legacy_family=true`
at `load_store()` time (load-time backfill, not dependent on new writes).

## 4. Blocked Fallback

These constraints are enforced:

- `attempted_adapters` MUST be persisted in the state schema, not held
  in orchestrator memory only.
- On resume from blocked, `attempted_adapters` MUST be restored from
  state and continue to exclude already-tried adapters.
- Hard-stop rules MUST be checked before any fallback attempt. If a
  hard-stop rule matches, no fallback occurs.
- A `max_fallback_attempts` equal to the total adapter count serves as
  the loop breaker. Exceeding it → hard stop.
- Sticky cache for the blocked adapter MUST be invalidated (weight → 0)
  for the duration of the current run.
