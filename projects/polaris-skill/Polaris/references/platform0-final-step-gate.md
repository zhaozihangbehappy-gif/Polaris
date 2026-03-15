# Platform-0 Final Step: Experience Migration + Cross-Version Evidence + Planner Contracts

_Gate contract — 2026-03-15_
_Author: Claude (to be audited by OpenClaw and Codex)_
_Baseline: Steps 0–2 committed (`22e5758`, `20e4311`, `0dff977`); Steps 3A+3B+4A implemented, regression EXIT=0 from both project root and `/tmp`_

---

## Scope

This is the **single remaining step** before Platform-0 is complete. It bundles three substeps that share a dependency on 4A (bootstrap protocol) being done:

| Substep | Summary |
|---------|---------|
| 4B | Experience asset versioning + migration bridge |
| 5A | Cross-version state evidence (v5 snapshot + rollback + round-trip) |
| 5B | Planner contract metadata (`requires` + `validates_with` on plan steps, capability warning in family resolver) |

**Execution order within this step**: 4B → 5A → 5B (each depends on the prior).

**CWD constraint**: every new regression scenario must pass when invoked from `/tmp`, not just from the project root. All Python subprocess paths must use `POLARIS_ROOT` env var, never relative `Polaris/scripts` paths.

---

## 4B: Experience Asset Versioning + Migration Bridge

### Goal

Tag every experience asset (pattern, rule, learning backlog item) with `asset_version`, and migrate pre-existing assets that lack the field on load. The three agreed experience asset types are: success patterns, rules, learning backlog. All three must be covered.

### Must-do

1. **`polaris_success_patterns.py`**
   - `capture` command: set `"asset_version": 2` on every new/merged pattern
   - `load_store()`: if a pattern has no `asset_version`, set `asset_version: 1` and `"migrated_from": "pre-step4"`
   - Consolidation (`consolidate-marker`): propagate `asset_version` from marker to output

2. **`polaris_rules.py`**
   - `add` command: set `"asset_version": 2` on every new rule
   - `load_store()`: if a rule has no `asset_version`, set `asset_version: 1` and `"migrated_from": "pre-step4"`

3. **`polaris_state.py`**
   - `backlog-add` command: set `"asset_version": 2` on each queued item
   - `load_state()`: iterate `learning_backlog` — items lacking `asset_version` get `asset_version: 1`
   - Resume (3B) must NOT re-tag preserved backlog items — they keep their original `asset_version`

4. **`polaris_bootstrap.json`**
   - Manifest adapter/rule/pattern records do NOT need `asset_version` — the receiving CLI (`polaris_rules.py add`, etc.) adds it at registration time

5. **Bootstrap idempotency update**
   - `polaris_bootstrap.py normalize_*` functions must include `asset_version` in the normalized form so idempotency comparison accounts for it
   - After 4B, a second bootstrap run on an already-registered dir must still produce `"skipped": true`

6. **Regression scenarios**
   - `4b-pattern-migration`: create a patterns file with v1 patterns (no `asset_version`) → load via Python `load_store()` → assert `asset_version: 1` added → capture a new pattern → assert `asset_version: 2`
   - `4b-rule-migration`: same for rules
   - `4b-backlog-migration`: create a state file with v1 backlog items (no `asset_version`) → load via `load_state()` → assert `asset_version: 1` on each item
   - `4b-consolidation-across-versions`: consolidate a v1 marker → verify output has `asset_version` and consolidation succeeds
   - `4b-resume-preserves-version`: blocked run queues backlog items (will have `asset_version: 2`) → resume → assert items still have `asset_version: 2`, not re-tagged
   - All existing scenarios must still pass

### Acceptance criteria (4B)

| # | Criterion | Verification |
|---|-----------|-------------|
| 4B.1 | New patterns have `asset_version: 2` | Any post-4B scenario: check field |
| 4B.2 | Old patterns (no `asset_version`) get `asset_version: 1` after load | `4b-pattern-migration` |
| 4B.3 | Consolidation works across v1 and v2 patterns | `4b-consolidation-across-versions` |
| 4B.4 | Migration does NOT alter behavioral fields (`trigger`, `sequence`, `outcome`) | `4b-pattern-migration`: compare before/after |
| 4B.5 | New rules have `asset_version: 2` | Any post-4B scenario: check field / `4b-rule-migration` |
| 4B.6 | Old rules (no `asset_version`) get `asset_version: 1` after load | `4b-rule-migration` |
| 4B.7 | New backlog items have `asset_version: 2` | Any post-4B scenario with learning |
| 4B.8 | Old backlog items get `asset_version: 1` after `load_state()` | `4b-backlog-migration` |
| 4B.9 | Resume preserves original `asset_version` on backlog items | `4b-resume-preserves-version` |
| 4B.10 | Bootstrap idempotency still works (second run → `"skipped": true`) | `bootstrap-idempotency` scenario still passes |
| 4B.11 | All existing regression scenarios pass | EXIT=0 |

### Veto (一票否决 — 4B)

1. **Any of the three experience asset types (patterns, rules, backlog) lacks `asset_version` tagging** → 4B fails. Covering two out of three is an incomplete bridge.
2. **`load_store()` or `load_state()` does NOT migrate old assets** → 4B fails. Adding a version field without a read-time migration path is decoration, not a bridge.
3. **Old patterns cause consolidation to crash or silently drop** → 4B fails. The bridge must preserve semantic content.
4. **Migration alters behavioral fields** (`trigger`, `sequence`, `outcome` for patterns; `trigger`, `action` for rules) → 4B fails. Migration adds metadata; it must not mutate semantics.
5. **Resume re-tags preserved backlog items with `asset_version: 2`** → 4B fails. Resume preserves assets from their original era.
6. **Bootstrap idempotency breaks** (second run no longer skips) → 4B fails. `normalize_*` functions must account for `asset_version`.

---

## 5A: Cross-Version State Evidence

### Goal

Prove, at the state level, that:
1. A v6 state file can be loaded by frozen v5 code without crash, key fields survive
2. A v5-written state file can run end-to-end through the current `polaris_runtime_demo.sh`
3. A full round-trip v5→v6→v5 preserves key fields
4. Coexistence asymmetry is explicitly documented

**Scope boundary**: this is state-layer evidence, not full old-runtime execution. Full old-orchestrator end-to-end is deferred to P1 (freezing the entire v5 orchestrator + all dependencies is out of scope for Platform-0).

### Must-do

1. **`polaris_v5_snapshot.py`** — frozen v5 code snapshot
   - Source: `git show 22e5758:projects/polaris-skill/Polaris/scripts/polaris_state.py`
   - Extract into a self-contained test fixture file with three functions:
     - `v5_load_state(path)` — the pre-Step-1-2 loader that expected `schema_version == 5`
     - `v5_write_json(path, payload)` — the pre-Step-1-2 writer with v5 minimal-density whitelist
     - `v5_default_state()` — the pre-Step-1-2 default with `schema_version: 5`
   - This file is a test fixture only — never imported by production code, never updated after creation
   - Must be importable from any CWD (no relative path assumptions)

2. **Regression scenarios**
   - `rollback-v6-in-v5-loader`:
     - Take a v6 `execution-state.json` from any completed scenario
     - Feed it to `v5_load_state()` → assert: no crash, `run_id` survives, `goal` survives, `status` survives, `artifacts.selected_adapter` survives, `state_machine.node` survives
     - Write the v5-loaded state via `v5_write_json()` → reload with current `load_state()` → assert: loads as v5 → upgrades to v6, key fields survive the full round trip
   - `coexist-v5-dir-full-run`:
     - Create a runtime dir with v5 state (written by `v5_write_json(v5_default_state())`) + NO `runtime-format.json`
     - Run the full `polaris_runtime_demo.sh`
     - Assert: legacy gate fires, `runtime-format.json` written, state upgraded to v6, run completes
   - `cross-version-round-trip`:
     - Start: `v5_default_state()` → `v5_write_json()` → file on disk
     - Step 1: current `load_state()` loads it (v5→v6 upgrade)
     - Step 2: current `write_json()` writes it (v6 format)
     - Step 3: `v5_load_state()` loads the v6 file
     - Assert: no crash at any step, `run_id`, `goal`, `status` survive all 3 transitions

3. **Coexistence asymmetry documentation** — add to `platform0-phase3-5-execution-plan.md`:
   - New code protects old dirs: compat gate refuses incompatible formats
   - Old code may overwrite new dirs: no gate in old code, `runtime-format.json` is ignored
   - Explicit "what degrades" list for v6→v5 rollback:
     - `compat` field lost
     - `schema_version` reverts to 5
     - `runtime-format.json` ignored but not deleted
     - `asset_version` fields on patterns/rules/backlog items pass through (v5 code ignores unknown fields)
   - v5→v6 upgrade: lossless (already proven in Steps 1–2)

### Acceptance criteria (5A)

| # | Criterion | Verification |
|---|-----------|-------------|
| 5A.1 | `polaris_v5_snapshot.py` exists with `v5_load_state`, `v5_write_json`, `v5_default_state` matching pre-`20e4311` git history | File exists, functions extracted from commit `22e5758` |
| 5A.2 | v6 state loads in v5 loader without crash, key fields survive | `rollback-v6-in-v5-loader` |
| 5A.3 | v5-written state runs end-to-end in new code via `polaris_runtime_demo.sh` | `coexist-v5-dir-full-run` |
| 5A.4 | Full round-trip v5→v6→v5 preserves key fields | `cross-version-round-trip` |
| 5A.5 | Coexistence asymmetry documented with "what degrades" list | Plan document updated |
| 5A.6 | All existing regression scenarios pass | EXIT=0 |

### Veto (一票否决 — 5A)

1. **Rollback test uses the current `load_state()`** (which already handles v6) instead of frozen v5 code → 5A fails. The evidence must come from actual v5-era logic.
2. **Tests only check "no crash" without verifying field survival** → 5A fails. Rollback guarantee = "key data survives", not just "doesn't crash".
3. **Coexistence proven only via hand-crafted state files** → 5A fails. At least `coexist-v5-dir-full-run` must use `v5_write_json()` to produce state.
4. **Round-trip is one-directional only** (v5→v6 without v6→v5, or vice versa) → 5A fails.
5. **Coexistence asymmetry not documented** with explicit "what degrades" list → 5A fails.
6. **`polaris_v5_snapshot.py` imports or calls production code** → 5A fails. It must be fully self-contained.

---

## 5B: Planner Contract Metadata

### Goal

Add `requires` (capability list) and `validates_with` (validator kind) to every plan step, and add a capability-check path to the family resolver that produces a warning trace when the selected adapter's capabilities do not satisfy the plan's requirements.

This is the **interface definition** — the first step from heuristic selection toward contract-driven selection. The planner still generates plans heuristically, but each step now declares what it needs. Hard enforcement is a P1 concern.

### Must-do

1. **`polaris_planner.py build_steps()`**
   - Each step dict gets two new fields:
     - `requires`: list of capability strings needed for this phase. Mapping:
       - `planning` → `[]` (no runtime capability needed)
       - `ready` → `["local-exec"]` (adapter selection needs executable adapter)
       - `executing` → `["local-exec"]`
       - `validating` → `["local-exec", "reporting"]`
       - `completed` → `["reporting"]`
     - `validates_with`: validator kind. Mapping:
       - `planning` → `null`
       - `ready` → `null`
       - `executing` → `"runner_result_contract"`
       - `validating` → `"evidence_check"`
       - `completed` → `null`
   - Values derived mechanically from `phase` — no new design

2. **`polaris_contract_planner.py choose_family()`**
   - New parameter: `plan_requires: list[str] | None`
   - After selecting a family, check if the adapter's `capabilities` list covers all entries in `plan_requires`
   - If mismatch: add `"capability_warning": "adapter missing: [X, Y]"` to the returned trace dict
   - This is a **warning only** — no hard failure, no exit 1. The run proceeds but the trace documents the gap.

3. **`polaris_orchestrator.py`**
   - Pass the current plan step's `requires` list to `choose_family()` as `plan_requires`
   - The planner already writes `requires` into the plan; the orchestrator reads it from the plan step and forwards it

4. **Regression scenarios**
   - `5b-plan-requires-deep`: run a deep-profile scenario → load state → assert every plan step has `requires` (list) and `validates_with` (string or null) fields. `executing` step must have `requires` containing `"local-exec"`.
   - `5b-plan-requires-micro`: same for micro profile
   - `5b-capability-warning`: synthetic test — create an adapter JSON with deliberately limited `capabilities` (e.g., only `["reporting"]`, missing `"local-exec"`) → call `choose_family()` with `plan_requires=["local-exec", "reporting"]` → assert trace dict contains `capability_warning` mentioning `"local-exec"`
   - All existing scenarios must still pass

### Acceptance criteria (5B)

| # | Criterion | Verification |
|---|-----------|-------------|
| 5B.1 | Deep-profile plan steps have non-empty `requires` on executing/validating phases | `5b-plan-requires-deep` |
| 5B.2 | Micro-profile plan steps have non-empty `requires` on executing/validating phases | `5b-plan-requires-micro` |
| 5B.3 | `validates_with` is set for executing and validating phases | `5b-plan-requires-deep` |
| 5B.4 | Family resolver produces `capability_warning` on synthetic mismatch | `5b-capability-warning` |
| 5B.5 | Existing scenarios unaffected (warning is additive, not breaking) | EXIT=0 |

### Veto (一票否决 — 5B)

1. **Plan steps have `requires: []` for ALL phases** → 5B fails. `executing` and `validating` must have meaningful capability names.
2. **`choose_family()` has no capability-check code path** → 5B fails. The check must exist and produce a warning trace.
3. **Contract fields written to plan but never read by any consumer** → 5B fails. The family resolver must read `requires` from the plan and compare against adapter capabilities.
4. **Capability warning hard-fails the run** (exit 1 on mismatch) → 5B fails. This step is warning-only; hard enforcement is P1.
5. **`validates_with` is absent or always null** → 5B fails. `executing` and `validating` phases must have non-null validator kinds.

---

## Cross-cutting Veto (一票否决 — 全局)

These apply to the entire final step, regardless of which substep is being evaluated:

| # | Veto condition | Reason |
|---|---------------|--------|
| G1 | Regression does NOT pass from `/tmp` (CWD ≠ project root) | CWD independence is a hard contract since audit round 2. Any new code using relative `Polaris/scripts` paths is a veto. |
| G2 | Any previously passing regression scenario breaks | No regressions allowed. Every substep must be strictly additive. |
| G3 | New regression scenarios call Python scripts with CWD-relative paths instead of `$POLARIS_ROOT` | Same as G1 — must use `POLARIS_ROOT` env var for all subprocess paths. |
| G4 | State mutations bypass canonical writer (`polaris_state.py` CLI → `write_json()`) | Established in audit round 2. All state writes must go through the canonical path for `state_write_count`, `updated_at`, history compaction. |
| G5 | New files import production modules with relative paths | All imports must work regardless of CWD. Use `POLARIS_ROOT` or `__file__`-relative resolution. |

---

## Platform-0 Completion Definition

After this final step passes (4B + 5A + 5B), Platform-0 is complete when ALL of the following hold:

| Block (from `platformization-phase0.md`) | Covered by | Evidence |
|---|---|---|
| Schema compatibility contract | Steps 1–2 (v5→v6 gate) + Step 3A (clean artifacts) | `compat-*` regression scenarios, zero `parse_inline_json` in codebase |
| Runtime-directory compatibility / migration | Steps 1–2 (format marker + gate) + Step 3B (resume) | `resume-*` scenarios, `runtime-format.json` gate |
| Bootstrap/runtime general capability protocol | Step 4A (manifest + `requires` + idempotency) | `bootstrap-*` scenarios, `polaris_bootstrap.json` manifest |
| Semantic migration for experience assets | Step 4B (pattern/rule/backlog version + bridge) | `4b-*` scenarios, `asset_version` field on all experience assets |
| Side-by-side / rollback / cross-version regression | Step 5A (v5 snapshot + 3 cross-version scenarios) + Steps 1–2 | `rollback-*`, `coexist-*`, `cross-version-*` scenarios |
| Planner contract interface (bridge to P1) | Step 5B (`requires` + `validates_with` + capability warning) | `5b-*` scenarios |

**Final gate**: `polaris_regression.sh` exits 0 from both the project root AND from `/tmp`.

After this gate passes, capability expansion may resume.
