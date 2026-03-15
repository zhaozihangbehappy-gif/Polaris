# Steps 1–2: Compatibility Spine + Runtime-dir Safe Resume

_Engineering plan — 2026-03-15_
_Author: Claude (to be audited by OpenClaw and Codex)_

---

## Goal

Establish the minimum compatibility and deployment-safety infrastructure so that future Polaris schema changes, runtime-directory format changes, and cross-version upgrades do not depend on one-shot migration luck.

Concretely: after Steps 1–2, Polaris can read state files from the current schema (v5), write in a new canonical schema (v6), detect incompatible runtime directories before overwriting them, and prove all of this through regression — not through documentation claims.

---

## What "compatibility spine" means here

- **Forward-compatible write**: new Polaris writes v6 state that includes all fields a v5 reader needs.
- **Backward-compatible read**: new Polaris reads v5 state files without loss or crash.
- **Runtime format marker**: every runtime directory carries a machine-readable format version file (`runtime-format.json`) that gates whether Polaris may open, resume, or overwrite it.
- **Resume safety gate**: before **any** write to a pre-existing runtime directory — including adapter registration, rules, and success patterns written by wrapper scripts — Polaris checks the format marker and refuses to proceed if the version is incompatible or unknown. The gate runs before the first byte is written, not before orchestrator startup.
- **Migration bridge**: `load_state()` can upgrade a v5 state to v6, preserving all data, and the upgrade is tested by regression.

---

## Step 1: Schema Compatibility Contract

### Must-do

1. **`polaris_compat.py`** — new compatibility module
   - `CURRENT_SCHEMA_VERSION = 6`
   - `READABLE_SCHEMA_VERSIONS = {5, 6}` — versions this Polaris can read
   - `CURRENT_RUNTIME_FORMAT = 1` — first runtime-dir format version
   - `COMPATIBLE_RUNTIME_FORMATS = {1}` — formats this Polaris can open
   - `check_schema_version(state: dict) -> CompatResult` — returns ok / upgradeable / incompatible
   - `check_runtime_format(runtime_dir: Path) -> CompatResult` — reads `runtime-format.json`, returns ok / missing / incompatible
   - `write_runtime_format(runtime_dir: Path)` — writes `runtime-format.json` with current format version, Polaris version, and timestamp
   - `CompatResult` is a simple dict with `{"compatible": bool, "reason": str, "action": "proceed"|"upgrade"|"refuse"}`

2. **Schema v5 → v6 upgrade in `polaris_state.py`**
   - `default_state()` returns `schema_version: 6`
   - `load_state()` adds a new branch: if `schema_version == 5`, upgrade to 6 (preserving all existing fields, adding any new v6-only fields with defaults)
   - The v5 → v6 upgrade must be lossless: every field in a v5 state file must survive the upgrade with its original value
   - New v6 field: `"compat"` dict in state root with `{"upgraded_from": 5|null, "upgraded_at": "iso"|null, "runtime_format": 1}`

3. **Load-write-reload lossless test** — regression proves the full round-trip: load a v5 state file → write as v6 via `write_json()` (including minimal-density filtering) → reload the written file → assert all original v5 key fields survive. This catches field loss in the `write_json()` minimal-density whitelist (`polaris_state.py:234–238`), not just in `load_state()`.

4. **Canonical-write** — `write_json()` always writes `schema_version: 6`. There is no "write in v5 format" path. Forward compatibility is achieved by keeping all v5-expected fields present in the v6 output (superset, not rename). The `compat` field must be included in the minimal-density whitelist so it survives `write_json()` filtering.

### Forbidden pseudo-completion (Step 1)

1. **If `load_state()` silently drops or overwrites v5 fields during upgrade, Step 1 is not complete.**
   Every v5 field must survive the upgrade with its original value.

2. **If the schema version bump is a number change with no structural difference, Step 1 is not complete.**
   v6 must add at least the `compat` tracking field, and the upgrade path must be tested.

3. **If compatibility is checked by documentation claim only (no code, no regression), Step 1 is not complete.**
   `polaris_compat.py` must exist, and regression must exercise the check functions.

4. **If v5 state files cannot be loaded by the new code without error, Step 1 is not complete.**
   The dual-read path is mandatory, not optional.

---

## Step 2: Runtime-dir Compatibility / Safe Resume

### Must-do

1. **Runtime format marker** — `runtime-format.json` written to every runtime directory at initialization
   ```json
   {
     "runtime_format": 1,
     "created_by": "polaris",
     "schema_version": 6,
     "created_at": "2026-03-15T...",
     "min_compatible_schema": 5
   }
   ```

2. **Gate-before-first-write invariant** — the compat gate must run before **any** write to the runtime directory. In the current architecture, `polaris_runtime_demo.sh` writes `adapters.json`, `rules.json`, and `success-patterns.json` (lines 32–146) before calling the orchestrator (line 147). Therefore:
   - The gate **cannot** live only in `polaris_orchestrator.py` — that is too late.
   - `polaris_runtime_demo.sh` must call `polaris_compat.py check-runtime-format` immediately after `mkdir -p "$RUNTIME_DIR"` and before any adapter/rule/pattern writes.
   - If the check returns incompatible, the shell script must `exit 1` before writing anything.
   - Any other wrapper/harness that writes to a runtime dir must follow the same pattern.

3. **Format marker write** — `polaris_runtime_demo.sh` calls `polaris_compat.py write-runtime-format` immediately after the gate passes (for new dirs) or after legacy upgrade (for marker-less dirs), before any adapter/rule/pattern registration.

4. **Resume safety gate** — the gate logic in `polaris_compat.py check-runtime-format`:
   - If `runtime-format.json` exists → check `runtime_format` field against `COMPATIBLE_RUNTIME_FORMATS`
   - If compatible → exit 0 (proceed)
   - If incompatible → print error to stderr, exit 1: `"Runtime directory format {found} is not compatible with this Polaris version (supports: {supported})"`
   - If `runtime-format.json` missing but `execution-state.json` exists → legacy directory → write the marker, upgrade state, exit 0
   - If `runtime-format.json` missing and no state file → fresh directory → write the marker, exit 0

5. **Orchestrator gate (defense in depth)** — `polaris_orchestrator.py` also calls the compatibility check at startup, as a second layer. This catches cases where the orchestrator is called directly without the demo wrapper. But the primary gate is in the wrapper layer.

6. **Legacy directory handling** — a runtime directory created before Steps 1–2 (no `runtime-format.json`, `schema_version: 5` state) must be handled gracefully:
   - Write `runtime-format.json` with `runtime_format: 1`
   - Upgrade state from v5 to v6
   - Proceed normally
   - This is tested in regression

### Forbidden pseudo-completion (Step 2)

1. **If `runtime-format.json` is written but never read or checked, Step 2 is not complete.**
   The gate must be exercised: a test must show that an incompatible format version causes abort.

2. **If the resume safety gate can be bypassed by a flag or env var, Step 2 is not complete.**
   The gate is hard. No `--skip-compat-check`.

3. **If legacy directories (no `runtime-format.json`) cause a crash instead of graceful upgrade, Step 2 is not complete.**
   Legacy handling is a must-do, not a nice-to-have.

4. **If the gate only checks the format marker but not the state schema version, Step 2 is not complete.**
   Both layers must be checked: runtime format + state schema.

5. **If wrapper scripts (demo, harness, regression) can write adapters/rules/patterns to an incompatible runtime directory before the gate runs, Step 2 is not complete.**
   The gate-before-first-write invariant is the core timing contract of Step 2. Putting the gate only in the orchestrator while the wrapper has already mutated the directory is a false gate.

---

## Acceptance Criteria (combined)

### Code

1. `polaris_compat.py` exists with `check_schema_version()`, `check_runtime_format()`, `write_runtime_format()`
2. `polaris_state.py` `default_state()` returns `schema_version: 6` with `compat` field
3. `polaris_state.py` `load_state()` upgrades v5 → v6 losslessly, with `compat.upgraded_from` set
4. `polaris_orchestrator.py` calls compatibility gate at startup
5. `polaris_runtime_demo.sh` writes `runtime-format.json` at directory init
6. `write_json()` always writes `schema_version: 6`

### Regression

7. **`compat-v5-load-write-reload-lossless`**: create a v5 state file (with `state_density: "minimal"` to exercise the whitelist filter) → load with new `load_state()` → write via `write_json()` → reload the written file → assert `schema_version == 6`, `compat.upgraded_from == 5`, and all original v5 key fields (run_id, goal, mode, execution_profile, artifacts, state_machine.node, rule_context) survive the full load → write → reload round-trip
8. **`compat-runtime-format-gate`**: create a runtime dir with `runtime_format: 999` in `runtime-format.json` → run `polaris_runtime_demo.sh` (not just orchestrator) → assert it aborts with incompatibility error (non-zero exit) **and** assert `adapters.json` was NOT written (proving the gate ran before wrapper writes)
9. **`compat-legacy-dir-upgrade`**: create a runtime dir with v5 state and no `runtime-format.json` → run full demo → assert `runtime-format.json` is created, state upgraded to v6, run completes successfully
10. **`compat-format-marker-written`**: run any normal scenario → assert `runtime-format.json` exists in runtime dir with `runtime_format: 1`
11. **`compat-wrapper-no-early-write`**: create a runtime dir with incompatible `runtime-format.json` → run `polaris_runtime_demo.sh` → assert none of `adapters.json`, `rules.json`, `success-patterns.json` were created or modified (gate blocked all writes)

### Compatibility / migration evidence

12. All 26 existing regression scenarios pass with `schema_version: 6` in their output state files
13. The v5 → v6 upgrade preserves every field through the full load → write → reload cycle, including under minimal-density filtering (tested by `compat-v5-load-write-reload-lossless`)
14. Legacy directories are handled without crash (tested by `compat-legacy-dir-upgrade`)
15. Wrapper scripts do not mutate incompatible runtime dirs before gate verdict (tested by `compat-wrapper-no-early-write`)

### Old-scenario zero-breakage evidence

16. The full regression suite (`polaris_regression.sh`) passes with zero failures
17. All Step 0 scenarios (`real-analysis-success`, `real-analysis-failure-repair`) continue to pass
18. No existing scenario's expected output changes except `schema_version` (5 → 6) — and `schema_version` is NOT checked by existing assertions (verified by grep)

---

## Failure Criteria

Steps 1–2 have **failed** if any of the following is true after implementation:

1. Any of the 26 existing regression scenarios fails
2. A v5 state file causes `load_state()` to crash or lose data
3. A v5 state file survives `load_state()` but loses fields after `write_json()` round-trip (the write-then-reload gap)
4. An incompatible `runtime-format.json` does NOT cause abort — whether called via orchestrator or via wrapper script
5. Wrapper scripts (demo/harness) write adapters/rules/patterns to a runtime dir before the compat gate has run
6. A legacy directory (no marker) causes a crash
7. `runtime-format.json` is not written during normal runs
8. The `compat` field is missing from v6 state files
9. The compatibility gate is bypassable via flag or env var
10. Any acceptance criterion above is met by documentation alone without code + regression evidence

---

## Deliverables

### New files

1. `scripts/polaris_compat.py` — compatibility module (CLI + library)
   - Subcommands: `check-schema`, `check-runtime-format`, `write-runtime-format`
   - Library functions: `check_schema_version()`, `check_runtime_format()`, `write_runtime_format()`

### Modified files

2. `scripts/polaris_state.py`
   - `default_state()` → `schema_version: 6`, add `compat` field
   - `load_state()` → add v5 → v6 upgrade branch
   - `write_json()` → always writes v6

3. `scripts/polaris_orchestrator.py`
   - Add compatibility gate call at startup (before state init)
   - Pass runtime dir to gate check

4. `scripts/polaris_runtime_demo.sh`
   - Add compat gate call immediately after `mkdir -p "$RUNTIME_DIR"`, before any adapter/rule/pattern writes
   - Call `polaris_compat.py write-runtime-format` after gate passes, before adapter registration
   - Gate failure → `exit 1` before any file is written

5. `scripts/polaris_regression.sh`
   - Add 5 new scenarios: `compat-v5-load-write-reload-lossless`, `compat-runtime-format-gate`, `compat-legacy-dir-upgrade`, `compat-format-marker-written`, `compat-wrapper-no-early-write`
   - Add Step 1–2 assertions block

---

## Implementation Sequence

1. Write `polaris_compat.py` with version constants + check functions + CLI
2. Update `polaris_state.py`: bump to v6, add `compat` field, add v5 upgrade path, add `compat` to minimal-density whitelist in `write_json()`
3. Update `polaris_runtime_demo.sh`: add compat gate + format marker write **before** any adapter/rule/pattern registration (gate-before-first-write invariant)
4. Update `polaris_orchestrator.py`: add compatibility gate at startup (defense in depth)
5. Add 5 regression scenarios + assertions to `polaris_regression.sh`
6. Run full regression and verify: zero breakage on existing 26 scenarios + all 5 new scenarios pass

---

## Precise scope claims

Steps 1–2 prove the following and no more:

1. **Same-major-version compatibility** — v5 → v6 within the same Polaris codebase. This does not prove cross-repository or cross-deployment compatibility. The compatibility spine is a local contract, not a distributed one.

2. **Format-marker gating, not migration orchestration** — the gate detects incompatibility and refuses to proceed. It does not automatically migrate from format N to format N+1. Migration is manual (upgrade code in `load_state`), and is tested for exactly one transition (v5 → v6).

3. **Runtime-dir safety, not runtime-dir portability** — the format marker prevents accidental overwrites across incompatible versions. It does not make runtime directories portable across machines, filesystems, or OS versions.

4. **Safe-open-and-reinitialize, not true resume** — the legacy directory gate checks compatibility and allows the run to proceed, but `polaris_state.py init` rebuilds state from `default_state()` unconditionally. This means a legacy directory that passes the gate gets a fresh run identity, not a continuation of its prior run state. Evidence: legacy regression output has `compat.upgraded_from: null` because the v5→v6 upgrade in `load_state()` is bypassed by the `init` command's `state = default_state()`. True resume-preserving semantics (detect prior run state, skip init, continue from last checkpoint) is an open edge for a future phase.

## Accepted residual risk (OpenClaw audit, 2026-03-15)

The "safe resume" label in the original plan is stronger than what Steps 1–2 actually deliver. The compatibility gate prevents incompatible overwrites and the v5→v6 load path is lossless, but the orchestrator's `init` path discards pre-existing state. Genuine resume-safe semantics require the orchestrator to detect and continue from prior state rather than reinitializing — that work belongs to a future step, not hidden under the current gate.

## Non-goals

- Cross-deployment compatibility (different machines, different OS)
- Automatic migration orchestration (N → N+1 → N+2 chains)
- Rollback contract (Step 3/4 scope — side-by-side deployment)
- Schema registry or external version catalog
- Breaking change to any existing field name or structure (v6 is a superset of v5)
