# Platform-0 Phase 3–5: Gate Contracts

_Engineering plan — 2026-03-15_
_Author: Claude (to be audited by OpenClaw and Codex)_
_Baseline: commits `22e5758` (Step 0), `20e4311` (Steps 1–2), `0dff977` (cleanup)_

---

## Baseline: what the current code actually does

All line references are to the codebase as of `0dff977`.

### Artifact double-serialization (the actual debt)

`polaris_orchestrator.py` stores structured data as JSON strings inside JSON state via the `artifact` CLI:

| Line | Key | What is serialized |
|------|-----|--------------------|
| 1259 | `family_transfer_applied` | `json.dumps(bool)` → `"true"` or `"false"` |
| 1332 | `execution_family_trace` | `json.dumps(dict)` |
| 1340 | `baseline_execution_contract` | `json.dumps(dict)` |
| 1341 | `execution_contract_diff` | `json.dumps(dict)` |
| 1342 | `transfer_contract_diff` | `json.dumps(dict)` |
| 1343 | `baseline_validator` | `json.dumps(dict)` |
| 1344 | `validator_diff` | `json.dumps(dict)` |
| 1345 | `execution_contract` | `json.dumps(dict)` |
| 443 | `learning_summary` | `json.dumps(dict)` |
| 873 | `efficiency_metrics` | `json.dumps(dict)` |

The receiving end is `polaris_state.py:534`:
```python
state.setdefault("artifacts", {})[args.key] = args.value  # stores string, not dict
```

Consumers must unwrap:
- `polaris_regression.sh:161–164`: `parse_inline_json()` helper exists solely to unwrap this
- `polaris_regression.sh:400`: `json.loads(state['artifacts'].get('family_transfer_applied', 'false'))`
- `polaris_regression.sh:168,279,570`: `parse_inline_json(artifacts.get('efficiency_metrics'))`, `parse_inline_json(artifacts.get('learning_summary'))`

### Init unconditionally overwrites state (the resume gap)

`polaris_state.py:425–452`: `init` command does `state = default_state()` then `state.update({...})`. Any pre-existing state (prior run's attempts, artifacts, learning_backlog, state_machine history) is destroyed.

`polaris_orchestrator.py:1118–1141`: calls `polaris_state.py init` unconditionally — `fresh_state` at line 1094 is only used for pattern transfer heuristic at line 1249, NOT for skipping init.

### Bootstrap hardcoding (the protocol gap)

`polaris_runtime_demo.sh:32–146`: 5 adapter registrations (115 lines of inline `polaris_adapters.py add` calls), 1 rule registration (`polaris_rules.py add`), 1 pattern registration (`polaris_success_patterns.py capture`). No configuration file. No idempotency check. Re-runs update existing assets through per-type merge logic: `polaris_adapters.py` replaces by tool name (line 365), `polaris_rules.py` merges by `rule_id` (line 139), `polaris_success_patterns.py` merges by fingerprint (line 134). This is more nuanced than unconditional overwrite, but it is still imperative and non-declarative.

### Experience asset versioning (the migration gap)

- `polaris_success_patterns.py:29,33`: patterns store has `schema_version: 1`, individual patterns have NO per-pattern version field
- `polaris_rules.py:17,31`: rules store has `schema_version: 3`, individual rules have NO per-rule version field
- No migration bridge exists for pattern/rule format changes
- No mechanism to detect whether a pattern/rule was created under v5 or v6 state semantics

---

## Step 3: Artifact De-stringification + Resume Fix

### 3A: Artifact de-stringification

#### Goal

Eliminate all double-serialized JSON-string artifacts from the state file. After 3A, every artifact value that is semantically a dict or bool is stored as a dict or bool, never as `json.dumps(x)`.

#### Must-do

1. **Change `polaris_state.py` `artifact` command to parse JSON values**
   - Current (`polaris_state.py:534`): `state["artifacts"][key] = args.value`
   - New: attempt `json.loads(args.value)` → if valid JSON object/array/bool, store the parsed value; if it raises or produces a plain string, store as-is
   - This makes the command backward-compatible: string filenames like `"runtime-executor-result.json"` stay as strings; `'{"status": "ok"}'` gets stored as `{"status": "ok"}`

2. **Remove `json.dumps()` wrapping from all 10 artifact stores in `polaris_orchestrator.py`**
   - Lines 1259, 1332, 1340, 1341, 1342, 1343, 1344, 1345: change `json.dumps(x)` to `json.dumps(x)` passed as the CLI `--value` argument — but now the artifact command will parse it back to dict. (The CLI boundary still requires a string; the change is that the receiver now parses it instead of storing the raw string.)
   - Line 443 (`learning_summary`): same treatment
   - Line 873 (`efficiency_metrics`): same treatment

3. **Update `polaris_regression.sh` consumers**
   - Remove `parse_inline_json()` function (lines 161–164) — no longer needed
   - Line 168, 279: `artifacts.get('efficiency_metrics')` is now a dict directly
   - Line 400: `artifacts.get('family_transfer_applied')` is now a bool directly — remove `json.loads()` wrapper
   - Line 570: `artifacts.get('learning_summary')` is now a dict directly
   - Every assertion that currently calls `parse_inline_json(x)` must change to just `x`

4. **Verify `write_json()` minimal-density whitelist** (`polaris_state.py:257–260`)
   - The whitelist filters artifact keys — dict-valued artifacts will serialize correctly through `json.dumps(persisted, ...)` since the outer `json.dumps` handles nested dicts. No whitelist change needed, but must verify no test breaks.

#### Forbidden pseudo-completion (3A)

1. **If `parse_inline_json()` still exists in `polaris_regression.sh`, 3A is not complete.**
   That function is the canary for double-serialization. Its existence proves the debt remains.

2. **If any artifact value in a final `execution-state.json` is a string that starts with `{` or `[`, 3A is not complete.**
   Exception: filename strings like `"runtime-executor-result.json"` are valid.

3. **If the `artifact` command in `polaris_state.py` still does `state["artifacts"][key] = args.value` without attempting JSON parse, 3A is not complete.**

4. **If `json.loads(state['artifacts'].get('family_transfer_applied', 'false'))` still appears in any consumer, 3A is not complete.** That pattern is the smoking gun of a stringified boolean.

#### Acceptance criteria (3A)

| # | Criterion | How to verify |
|---|-----------|---------------|
| 3A.1 | `parse_inline_json` does not appear in `polaris_regression.sh` | `grep -c parse_inline_json polaris_regression.sh` → 0 |
| 3A.2 | `json.loads(.*family_transfer_applied` does not appear in any file | `grep -r 'json.loads.*family_transfer_applied' scripts/` → 0 |
| 3A.3 | `state["artifacts"]["execution_contract"]` is a dict in `runner-success/execution-state.json` | `python3 -c "import json; s=json.load(open(...)); assert isinstance(s['artifacts']['execution_contract'], dict)"` |
| 3A.4 | `state["artifacts"]["learning_summary"]` is a dict in `step2-learning-repeat-success/execution-state.json` | Same pattern |
| 3A.5 | `state["artifacts"]["efficiency_metrics"]` is a dict in `deep-success/execution-state.json` | Same pattern |
| 3A.6 | `state["artifacts"]["family_transfer_applied"]` is a bool (not string) in `step3-transfer-target/execution-state.json` | `assert isinstance(v, bool)` |
| 3A.7 | All existing regression scenarios pass | Exit 0 |

#### Failure criteria (3A)

1. Any existing scenario fails after the change
2. A consumer crashes because it expected string but got dict
3. `parse_inline_json` still exists in any file
4. Any artifact value that should be a dict is still a string in the persisted state

#### Deliverables (3A)

| File | Change |
|------|--------|
| `polaris_state.py` | `artifact` command: add JSON parse attempt for `--value` |
| `polaris_orchestrator.py` | No code change needed — CLI still passes `json.dumps(x)` as string, but receiver now parses |
| `polaris_regression.sh` | Remove `parse_inline_json`, update all 4 call sites to read dicts directly |

#### Non-goals (3A)

- Changing the CLI interface (the `--value` arg is still a string on the command line)
- Restructuring the artifact dict itself (key names stay the same)
- Touching any artifact that is genuinely a string (filenames, adapter names)

---

### 3B: Resume fix

#### Goal

Make the orchestrator resume-aware: when a runtime directory contains a prior run that ended in `blocked` status, re-running the orchestrator continues from the blocked state instead of destroying it with `default_state()`.

#### Dependency

3B depends on 3A being complete. Reason: resume will preserve prior artifacts, so those artifacts must be clean dicts (not double-serialized strings) or the resumed run will have schema-inconsistent state — old artifacts as strings, new artifacts as dicts.

#### Must-do

1. **Conditional init in `polaris_orchestrator.py`**
   - Before calling `polaris_state.py init` (line 1118), load the existing state file
   - If `state["status"] == "blocked"` and `state["state_machine"]["node"] == "blocked"`:
     - Skip `init` entirely
     - Transition from `blocked` to `planning` (or `executing`, depending on the blocked phase)
     - Preserve: `run_id`, `attempts`, `artifacts`, `state_machine.history`, `learning_backlog`, `compat`
     - Set `compat.resumed_count` = prior value + 1 (new field, tracks resume lineage)
   - If `state["status"] == "completed"`: proceed with normal `init` (completed runs re-initialize)
   - If state file does not exist: proceed with normal `init`
   - If `state["status"] == "in_progress"`: this is a concurrent-run conflict — refuse and exit 1

2. **Resume lineage tracking in `polaris_state.py`**
   - Add `resumed_count` to `compat` dict default: `{"upgraded_from": None, "upgraded_at": None, "runtime_format": 1, "resumed_count": 0}`
   - `write_json()` minimal-density whitelist already includes `compat` — no additional change needed

3. **Resume regression scenarios — all must use `polaris_runtime_demo.sh` as the entrypoint, not direct orchestrator calls**
   The wrapper layer (`polaris_runtime_demo.sh`) currently rewrites `adapters.json`, `rules.json`, and `success-patterns.json` on every run (lines 32–146). A resume test that bypasses the wrapper and calls the orchestrator directly would prove only orchestrator-level resume, not the user-facing resume path. All three scenarios below must invoke the full wrapper.
   - `resume-from-blocked`: run `polaris_runtime_demo.sh` with `SIMULATE_ERROR="some error"` (standard profile → blocks) → save state → re-run `polaris_runtime_demo.sh` with same `RUNTIME_DIR` and `SIMULATE_ERROR=""` → assert:
     - `run_id` is preserved from first run
     - `attempts` array length > first run's attempts (accumulated, not reset)
     - `compat.resumed_count == 1`
     - `learning_backlog` from first run is preserved (not cleared by re-init)
     - status is `completed` (second run succeeds)
   - `resume-no-overwrite-completed`: run a scenario that completes via `polaris_runtime_demo.sh` → re-run with same `RUNTIME_DIR` → assert:
     - `run_id` is different (fresh init, not resume)
     - `compat.resumed_count == 0`
   - `resume-refuse-in-progress`: create a state file with `status: "in_progress"` and a valid `runtime-format.json` → run `polaris_runtime_demo.sh` → assert exit 1 (orchestrator refuses, wrapper propagates)

#### Forbidden pseudo-completion (3B)

1. **If `polaris_state.py init` still does `state = default_state()` unconditionally in all code paths, 3B is not complete.**
   The orchestrator must skip init when resuming.

2. **If a resumed run shows `compat.upgraded_from: null` and a fresh `run_id`, 3B is not complete.**
   That means init overwrote the prior state — the resume is fake.

3. **If the resume path does not preserve `attempts` from the prior run, 3B is not complete.**
   Attempts are the audit trail. Losing them means the resume is really a restart.

4. **If the resume path does not preserve `learning_backlog` from the prior run, 3B is not complete.**
   `learning_backlog` is an experience asset queued during the blocked run. Clearing it on resume discards learning evidence.

5. **If `status: "in_progress"` in a pre-existing state does not cause the orchestrator to refuse, 3B is not complete.**
   Running two orchestrators on the same dir concurrently is a corruption risk that must be gated.

6. **If the resume regression uses direct orchestrator calls instead of `polaris_runtime_demo.sh`, 3B is not complete.**
   The wrapper rewrites `adapters.json`/`rules.json`/`success-patterns.json` before calling the orchestrator. A resume test that bypasses the wrapper proves only half the path.

#### Acceptance criteria (3B)

| # | Criterion | How to verify |
|---|-----------|---------------|
| 3B.1 | Blocked run resumes: `run_id` preserved, `attempts` accumulated, `compat.resumed_count == 1` | Regression: `resume-from-blocked` |
| 3B.2 | Completed run re-initializes: fresh `run_id`, `compat.resumed_count == 0` | Regression: `resume-no-overwrite-completed` |
| 3B.3 | In-progress state causes orchestrator to refuse | Regression: `resume-refuse-in-progress` exit 1 |
| 3B.4 | `compat` field includes `resumed_count` in all states | All regression scenarios |
| 3B.5 | All existing regression scenarios pass | Exit 0 |

#### Failure criteria (3B)

1. Any existing scenario fails
2. `resume-from-blocked` shows a different `run_id` after second run
3. `resume-from-blocked` shows `attempts` length ≤ first run's attempts
4. `resume-refuse-in-progress` exits 0

#### Deliverables (3B)

| File | Change |
|------|--------|
| `polaris_orchestrator.py` | Conditional init: load state, check status, skip init if blocked |
| `polaris_state.py` | Add `resumed_count` to `compat` default |
| `polaris_regression.sh` | 3 new scenarios: `resume-from-blocked`, `resume-no-overwrite-completed`, `resume-refuse-in-progress` |

#### Non-goals (3B)

- Resuming from arbitrary intermediate states (only `blocked` is resumable)
- Automatic re-execution strategy on resume (resume puts you back in the flow, does not auto-fix the blocking reason)
- Multi-run lineage chain (only `resumed_count` integer, not a full history)

---

## Step 4: Bootstrap Protocol + Experience Migration

### Dependency

Step 4 depends on Step 3 (both 3A and 3B) being complete.

**Why Step 4 cannot come before Step 3:**
- Bootstrap refactors how adapters/rules/patterns are registered into the runtime dir
- If artifacts are still double-serialized (3A not done), the bootstrap manifest would encode stringified values, then 3A would require changing the manifest again — double refactor
- If resume is not fixed (3B not done), bootstrap idempotency logic cannot distinguish "fresh dir" from "dir that should be resumed" — bootstrap would overwrite patterns/rules that the resume path needs to preserve

### 4A: Bootstrap protocol

#### Goal

Replace the 115 lines of hardcoded adapter/rule/pattern registration in `polaris_runtime_demo.sh:32–146` with a bootstrap protocol that has three properties the current code lacks:

1. **Declarative** — what assets to register is specified in a manifest file, not inline shell commands
2. **Capability-checked** — at bootstrap time, the manifest declares what capabilities the environment must provide (`requires`), and the bootstrap script probes the actual host environment to verify those capabilities are present (interpreter exists and executes, runtime dir is writable, etc.) before proceeding
3. **Idempotent** — re-running bootstrap on a dir that already has semantically equivalent assets produces no writes

This is not yet a full cross-environment negotiation protocol (that is a non-goal), but it is the first real protocol seam: the manifest declares requirements, the bootstrap script probes the host to verify them. The check is an environment probe, not manifest self-consistency — "does the host provide what the manifest needs" rather than "does the manifest describe itself coherently."

#### Must-do

1. **`polaris_bootstrap.json`** — declarative manifest with capability contract
   - Extracted mechanically from the current shell commands, plus a new `requires` section
   - Structure:
     ```json
     {
       "bootstrap_version": 1,
       "requires": {
         "interpreter": "python3",
         "capabilities": ["local-exec", "reporting"],
         "min_schema_version": 5
       },
       "adapters": [
         {
           "tool": "python-runtime-local",
           "command": "python3 <script>.py",
           "inputs": ["script_path", "args"],
           "capabilities": ["local-exec", "reporting", ...],
           ...
         }
       ],
       "rules": [...],
       "patterns": [...]
     }
     ```
   - Adapter/rule/pattern fields are a 1:1 extraction of what `polaris_runtime_demo.sh` currently passes as CLI args
   - The `requires` section is new: it declares what the environment must provide for this manifest to work. The bootstrap script checks these before registration.

2. **`polaris_bootstrap.py`** — reads manifest, validates requirements, registers assets
   - `bootstrap --manifest FILE --runtime-dir DIR`
   - **Requirement check**: before any registration, validate `requires` against the actual runtime environment (not just the manifest's own internal consistency):
     - `interpreter`: check `shutil.which(interpreter)` is not None — proves the host has the required interpreter binary
     - `capabilities`: the runtime dir must provide evidence that each required capability is satisfiable. The bootstrap script probes the environment:
       - `"local-exec"`: check that the interpreter binary can execute a trivial script (e.g., `python3 -c "print('ok')"` returns exit 0)
       - `"reporting"`: check that the runtime dir is writable (bootstrap can create files in it)
       - Unknown capabilities: fail with an explicit "unsupported capability" error
       - This is a host-environment probe, not a manifest self-consistency check. The manifest declares what it needs; the bootstrap script checks whether the host can deliver.
     - `min_schema_version`: if `execution-state.json` exists, check its `schema_version >= requires.min_schema_version`
     - If any requirement fails: exit 1 with clear error, zero files written
   - **Manifest validation**: reject unknown top-level fields, missing required fields in adapters/rules/patterns
   - For each adapter: call `polaris_adapters.py add` with the manifest values
   - For each rule: call `polaris_rules.py add`
   - For each pattern: call `polaris_success_patterns.py capture`
   - **Idempotency**: compare manifest content against existing registered assets by normalized full content, not just tool names.
     - Current behavior is already more nuanced than "unconditional overwrite": `polaris_adapters.py` replaces by tool name (line 365), `polaris_rules.py` merges by `rule_id` (line 139), `polaris_success_patterns.py` merges by fingerprint (line 134). The bootstrap idempotency check must account for this.
     - Load existing `adapters.json` → normalize each adapter to the same field set as the manifest → compare. If all adapters match: skip adapter registration. Same for rules and patterns.
     - "Match" means: same tool/rule_id/pattern_id AND same capabilities/trigger/action/sequence. Changed selectors, fallbacks, or mode preferences count as a difference.
   - **Bootstrap report artifact**: write `runtime-bootstrap-report.json` to runtime dir with: `{"bootstrap_version": 1, "manifest": "path", "adapters_registered": N, "rules_registered": N, "patterns_registered": N, "skipped": bool, "requires_check": {...}}`

3. **`polaris_runtime_demo.sh` simplification**
   - Replace lines 32–146 with:
     ```bash
     python3 "$ROOT/scripts/polaris_bootstrap.py" bootstrap \
       --manifest "$ROOT/scripts/polaris_bootstrap.json" \
       --runtime-dir "$RUNTIME_DIR"
     ```
   - The compat gate (lines 13–15) stays before bootstrap
   - The orchestrator call (line 147) stays after bootstrap

4. **Equivalence proof**
   - Regression: run the new bootstrap → dump `adapters.json`, `rules.json`, `success-patterns.json` → compare field-by-field against the output of the old hardcoded registration
   - This is a mechanical diff, not a semantic judgment

5. **Requirement failure proof**
   - Regression: create a manifest with `"requires": {"interpreter": "nonexistent-binary-xyz"}` → run bootstrap → assert exit 1, no files written

6. **Capability probe proof**
   - Regression: create a manifest with `"requires": {"capabilities": ["local-exec", "reporting"]}` and a valid interpreter → run bootstrap in a writable runtime dir → assert: `requires_check` in the bootstrap report shows each capability checked against the environment with pass/fail status
   - Regression: create a manifest with `"requires": {"capabilities": ["nonexistent-capability"]}` → run bootstrap → assert exit 1 with "unsupported capability" error, no files written
   - This proves the bootstrap probes the host environment, not just the manifest's own adapter capability lists

#### Forbidden pseudo-completion (4A)

1. **If `polaris_runtime_demo.sh` still contains any `polaris_adapters.py add` call, 4A is not complete.**
   The demo script should call only `polaris_bootstrap.py`, not individual registration commands.

2. **If the manifest has no `requires` section, 4A is not complete.**
   A manifest without declared requirements is config extraction, not a protocol. The `requires` section is what makes the manifest a negotiable contract rather than a static file.

3. **If the bootstrap script does not validate `requires` before registration, 4A is not complete.**
   Having `requires` in the manifest but not checking it is a documentation-only protocol.

4. **If bootstrap idempotency compares only tool names / rule_ids without checking semantic fields (capabilities, trigger, action), 4A is not complete.**
   Name-only comparison misses changed capabilities, selectors, and fallbacks. The idempotency check must compare normalized full content.

5. **If the manifest contains fields or values that differ from what the current shell commands register (in the adapter/rule/pattern sections), 4A is not complete.**
   The manifest must be a mechanical extraction for the asset sections; only `requires` is new.

6. **If the `capabilities` check only verifies that each capability appears in the manifest's own adapter capability lists, 4A is not complete.**
   That is manifest self-consistency, not an environment probe. The bootstrap must check whether the host can actually deliver the required capabilities (interpreter executes, dir is writable, etc.).

#### Acceptance criteria (4A)

| # | Criterion | How to verify |
|---|-----------|---------------|
| 4A.1 | `polaris_bootstrap.json` exists with 5 adapters, 1 rule, 1 pattern, and a `requires` section | `python3 -c "import json; m=json.load(open(...)); assert len(m['adapters'])==5; assert 'requires' in m"` |
| 4A.2 | `polaris_runtime_demo.sh` has no `polaris_adapters.py add` calls | `grep -c 'polaris_adapters.py add' polaris_runtime_demo.sh` → 0 |
| 4A.3 | `polaris_runtime_demo.sh` adapter/rule/pattern section is ≤5 lines | Line count between compat gate and orchestrator call |
| 4A.4 | Bootstrap output matches old registration output field-by-field | Regression: mechanical diff |
| 4A.5 | Bootstrap skip on re-run with identical manifest (full-content idempotency) | Regression: run bootstrap twice, second run produces `"skipped": true` in report, no file changes |
| 4A.6 | Bootstrap requirement failure blocks registration | Regression: bad `requires.interpreter` → exit 1, no files written |
| 4A.7 | Bootstrap capability probe checks host environment, not manifest self-consistency | Regression: valid manifest in writable dir → `requires_check` shows per-capability probe results; manifest with unknown capability → exit 1 |
| 4A.8 | `runtime-bootstrap-report.json` written on every bootstrap | Regression: check file exists with expected fields |
| 4A.9 | All existing scenarios pass | Exit 0 |

#### Failure criteria (4A)

1. Any existing scenario fails
2. The manifest produces different adapters/rules/patterns than the old hardcoded commands
3. `polaris_runtime_demo.sh` still has inline registration commands
4. Re-running bootstrap with identical manifest overwrites existing configs
5. A manifest with unsatisfiable `requires` does not cause exit 1
6. No `requires` section in manifest

#### Deliverables (4A)

| File | Change |
|------|--------|
| `scripts/polaris_bootstrap.json` | New: declarative manifest with `requires` |
| `scripts/polaris_bootstrap.py` | New: manifest reader + registrar |
| `scripts/polaris_runtime_demo.sh` | Replace lines 32–146 with single bootstrap call |
| `scripts/polaris_regression.sh` | Add bootstrap equivalence + idempotency assertions |

### 4B: Experience migration bridge

#### Goal

Add per-asset version tagging to all three experience asset types (patterns, rules, and learning backlog items), and a migration bridge that upgrades pre-Step-4 assets to the new version without losing semantic content.

The agreed experience asset set is: success patterns, rules, and learning backlog. All three must be covered — omitting any one leaves a gap in the migration bridge.

#### Dependency

4B depends on 4A. Reason: the bootstrap manifest sets the initial version tags; if bootstrap isn't config-driven yet, there's no single place to enforce version tagging.

#### Must-do

1. **Per-pattern `asset_version` field**
   - `polaris_success_patterns.py capture`: add `"asset_version": 2` to every new pattern
   - `polaris_success_patterns.py consolidate-marker`: propagate `asset_version` from marker to pattern
   - Patterns without `asset_version` are treated as version 1 (pre-Step-4 era)

2. **Per-rule `asset_version` field**
   - `polaris_rules.py add`: add `"asset_version": 2` to every new rule
   - Rules without `asset_version` are treated as version 1

3. **Per-backlog-item `asset_version` field**
   - `polaris_state.py backlog-add`: add `"asset_version": 2` to each queued item's metadata
   - `polaris_orchestrator.py queue_learning_item()` (the function that calls `backlog-add`): ensure the payload includes `asset_version`
   - Backlog items without `asset_version` are treated as version 1 (pre-Step-4 era)
   - On resume (3B), preserved backlog items retain their original `asset_version` — they are not re-tagged

4. **Migration bridge in loaders**
   - `polaris_success_patterns.py load_store()` (line 27): if a pattern has no `asset_version`, set `asset_version: 1` and add `"migrated_from": "pre-step4"`
   - `polaris_rules.py load_store()` (line 22): same treatment
   - `polaris_state.py load_state()`: iterate `learning_backlog` items — if any item lacks `asset_version`, set `asset_version: 1`
   - This is a read-time migration, not a write-time one — old files are upgraded when loaded

5. **Semantic preservation proof**
   - Regression: create a patterns file with v1 patterns (no `asset_version`) → load via `load_store()` → assert `asset_version: 1` added → run consolidation → assert consolidation succeeds and produces `asset_version: 2` output
   - Same for rules
   - Create a state file with v1 backlog items (no `asset_version`) → load via `load_state()` → assert `asset_version: 1` added to each item → verify consolidation still processes them

#### Forbidden pseudo-completion (4B)

1. **If patterns have an `asset_version` field but `load_store()` does not migrate old patterns, 4B is not complete.**
   Adding a version field without a migration path is just adding a number, not a bridge.

2. **If old patterns (without `asset_version`) cause consolidation to crash or silently drop, 4B is not complete.**
   The bridge must preserve semantic content, not just avoid errors.

3. **If the migration bridge changes pattern semantics (different `trigger`, `sequence`, `outcome`), 4B is not complete.**
   Migration adds metadata fields; it must not alter behavioral fields.

4. **If `learning_backlog` items are not versioned and migrated alongside patterns and rules, 4B is not complete.**
   `learning_backlog` is one of the three agreed experience asset types. Versioning two out of three is an incomplete bridge.

5. **If a resumed run (3B) re-tags pre-existing backlog items with a new `asset_version`, 4B is not complete.**
   Resume preserves assets; migration tags them with their original era, not the current one.

#### Acceptance criteria (4B)

| # | Criterion | How to verify |
|---|-----------|---------------|
| 4B.1 | New patterns have `asset_version: 2` | Regression: check field in any new pattern |
| 4B.2 | Old patterns get `asset_version: 1` after load | Regression: load v1 pattern file, assert field added |
| 4B.3 | Consolidation works across v1 and v2 patterns | Regression: consolidate a v1 marker, verify output |
| 4B.4 | Migration does not alter behavioral fields (`trigger`, `sequence`, `outcome`) | Regression: compare before/after |
| 4B.5 | New backlog items have `asset_version: 2` | Regression: check field in queued items |
| 4B.6 | Old backlog items get `asset_version: 1` after `load_state()` | Regression: load state with v1 backlog, assert field added |
| 4B.7 | Consolidation processes v1 backlog items without error | Regression: consolidate v1 backlog item |
| 4B.8 | All existing scenarios pass | Exit 0 |

#### Deliverables (4B)

| File | Change |
|------|--------|
| `polaris_success_patterns.py` | Add `asset_version: 2` to capture, migration in `load_store()` |
| `polaris_rules.py` | Add `asset_version: 2` to add, migration in `load_store()` |
| `polaris_state.py` | Add `asset_version: 2` to `backlog-add`, migration in `load_state()` for backlog items |
| `polaris_orchestrator.py` | Ensure `queue_learning_item()` includes `asset_version` in payload |
| `polaris_regression.sh` | Add v1→v2 migration assertions for patterns, rules, AND backlog items |

#### Non-goals (4B)

- Multi-hop asset migration (v0→v1→v2 chains)
- Cross-file asset deduplication
- Asset schema registry

---

## Step 5: Rollback Test + Planner Contract Metadata

### Dependency

Step 5 depends on Step 4 being complete.

**Why Step 5 cannot come before Step 4:**
- Rollback test requires stable schemas — if Step 4 changes pattern/rule schemas, the rollback baseline is invalidated
- Planner contract metadata adds `requires` fields to plan steps — these fields interact with the family resolver, which Step 4's bootstrap may affect through capability lists
- Both 5A and 5B are integration-layer concerns that assume the storage and bootstrap layers are settled

### 5A: Side-by-side / Rollback / Cross-version regression

#### Goal

Prove three things at the **state-level** (not full old-runtime execution):
1. **Old/new runtime coexistence**: a runtime dir created by new Polaris (v6, with `runtime-format.json`) can be opened by old Polaris code without crash, and a runtime dir created by old Polaris (v5, no `runtime-format.json`) can be opened by new Polaris code (already proven in Steps 1–2 legacy gate).
2. **Rollback contract**: if an operator needs to roll back from new Polaris to old Polaris, the old code can read the new state file and extract useful data — with explicit documentation of what degrades.
3. **Cross-version state round-trip**: state written by frozen v5 code can be loaded, upgraded, and re-written by v6, and vice versa, with key fields surviving. A v5-written state dir can be used as input to the current full `polaris_runtime_demo.sh` pipeline.

**Scope clarification**: the frozen v5 snapshot contains state I/O functions (`v5_load_state`, `v5_write_json`, `v5_default_state`), not the full v5 orchestrator or planner. This provides state-level cross-version evidence — proof that version transitions don't cause data loss or crashes in the state layer. It does NOT prove that the old orchestrator can execute end-to-end on new state, because freezing the full old orchestrator as a runnable artifact is out of scope for Platform-0 (it would require freezing all v5 dependencies, adapters, and regression infrastructure). The original `platformization-phase0.md:84` requirement is partially satisfied: state-layer compatibility is proven, full old-runtime execution is deferred to P1.

#### Must-do

1. **Frozen v5 code snapshot** — `scripts/polaris_v5_snapshot.py`
   - A self-contained Python file containing frozen copies of these functions from before commit `20e4311`:
     - `v5_load_state(path)` — the old `load_state()` that expected `schema_version == 5`
     - `v5_write_json(path, payload)` — the old `write_json()` with the v5 minimal-density whitelist
     - `v5_default_state()` — the old `default_state()` with `schema_version: 5`
   - This is a test fixture file, never imported by production code, never updated after creation
   - The snapshot is taken from git history: `git show 22e5758:projects/polaris-skill/Polaris/scripts/polaris_state.py`

2. **Rollback scenario: v6 state into v5 loader**
   - `rollback-v6-in-v5-loader`: take a v6 `execution-state.json` from any completed scenario → feed it to `v5_load_state()` → assert:
     - No crash (loads without exception)
     - Key fields survive: `run_id`, `goal`, `status`, `artifacts.selected_adapter`, `state_machine.node`
     - `compat` field is ignored (v5 loader doesn't know about it — it passes through via `upgraded.update(state)`)
     - `schema_version` is overwritten to 5 by the v5 upgrade path (expected and documented)
   - Then: write the v5-loaded state via `v5_write_json()` → reload with current `load_state()` → assert:
     - Loads as v5 → upgrades to v6
     - Key fields still survive the full round trip

3. **Coexistence scenario: v5 state + new code end-to-end**
   - `coexist-v5-dir-full-run`: create a runtime dir with a v5 state (written by `v5_write_json()`), no `runtime-format.json` → run the full `polaris_runtime_demo.sh` → assert:
     - Legacy gate fires, writes `runtime-format.json`
     - State upgraded to v6
     - Run completes successfully
     - (This is similar to `compat-legacy-dir-upgrade` from Steps 1–2, but with the v5 state written by actual v5 code, not hand-crafted)

4. **Cross-version round-trip: v5 write → v6 load → v6 write → v5 load**
   - `cross-version-round-trip`:
     - Start: `v5_default_state()` → `v5_write_json()` → file on disk
     - Step 1: current `load_state()` loads it (v5→v6 upgrade)
     - Step 2: current `write_json()` writes it (v6 format)
     - Step 3: `v5_load_state()` loads the v6 file
     - Assert: no crash at any step, key fields survive all 3 transitions

5. **Coexistence asymmetry documentation**
   - New code protects old dirs: compat gate refuses incompatible formats (Steps 1–2)
   - Old code may overwrite new dirs: no gate in old code, `runtime-format.json` is ignored
   - This asymmetry is **accepted and documented**, not fixed. Fixing it would require patching old deployed code, which is out of scope.
   - Write the asymmetry into the plan document with explicit "what degrades" list:
     - v6 → v5 rollback: `compat` field lost, `schema_version` reverts to 5, `runtime-format.json` ignored but not deleted
     - v5 → v6 upgrade: lossless (already proven)

#### Forbidden pseudo-completion (5A)

1. **If the rollback test uses the current `load_state()` (which already handles v6), 5A is not complete.**
   The test must use a frozen snapshot of the pre-Step-1-2 v5 code, in a separate file, not the current production code.

2. **If the test only checks "no crash" without verifying field survival across the full round-trip, 5A is not complete.**
   The rollback guarantee is not just "doesn't crash" — it's "key data survives."

3. **If coexistence is only proven via hand-crafted state files, 5A is not complete.**
   At least one scenario must use `v5_write_json()` to produce the state, proving the actual v5 code path produces loadable output.

4. **If the cross-version round-trip does not include both directions (v5→v6 AND v6→v5), 5A is not complete.**
   One-directional testing leaves the other direction as an untested claim.

5. **If the coexistence asymmetry is not explicitly documented with a "what degrades" list, 5A is not complete.**
   Undocumented asymmetry becomes a surprise during actual rollback.

#### Acceptance criteria (5A)

| # | Criterion | How to verify |
|---|-----------|---------------|
| 5A.1 | `polaris_v5_snapshot.py` exists with frozen `v5_load_state`, `v5_write_json`, `v5_default_state` | Code: file exists, functions match pre-`20e4311` git history |
| 5A.2 | v6 state loads in v5 loader without crash, key fields survive | Regression: `rollback-v6-in-v5-loader` |
| 5A.3 | v5-written state runs end-to-end in new code | Regression: `coexist-v5-dir-full-run` |
| 5A.4 | Full round-trip v5→v6→v5 preserves key fields | Regression: `cross-version-round-trip` |
| 5A.5 | Coexistence asymmetry documented with "what degrades" list | Plan document |
| 5A.6 | All existing scenarios pass | Exit 0 |

#### Deliverables (5A)

| File | Change |
|------|--------|
| `scripts/polaris_v5_snapshot.py` | New: frozen v5 code snapshot (test fixture only) |
| `scripts/polaris_regression.sh` | Add 3 scenarios: `rollback-v6-in-v5-loader`, `coexist-v5-dir-full-run`, `cross-version-round-trip` |
| `references/platform0-phase3-5-execution-plan.md` | Coexistence asymmetry + "what degrades" documentation |

#### Non-goals (5A)

- Hot-swap rollback mechanism (this is evidence, not automation)
- Patching old deployed code to add compat gates
- Rollback of experience assets (patterns/rules) — only state file rollback is tested

### 5B: Planner contract metadata

#### Goal

Add contract requirement metadata to plan steps, and add a capability-check path to the family resolver, as the first step from heuristic selection toward contract-driven selection.

This is the **interface definition** — the planner still generates plans heuristically, but each plan step now declares what it needs. The family resolver checks whether the selected family satisfies those needs and logs a warning if not.

#### Must-do

1. **Add `requires` and `validates_with` to plan steps**
   - `polaris_planner.py build_steps()`: each step dict gets two new fields:
     - `requires`: list of capability strings needed for this phase (e.g., `["local-exec"]` for executing, `["reporting"]` for validating)
     - `validates_with`: validator kind expected (e.g., `"runner_result_contract"` for executing, `null` for planning)
   - Values are derived from the existing `phase` and `execution_profile` — this is a mechanical mapping, not a new design

2. **Family resolver capability check**
   - `polaris_contract_planner.py choose_family()`: after selecting a family, check if the adapter's capabilities satisfy the plan's `requires` list
   - If mismatch: add `"capability_warning": "adapter missing: [X, Y]"` to the trace dict
   - This is a warning, not a hard failure — it logs the gap without blocking execution
   - Hard enforcement is a future step

3. **Planner contract regression**
   - Verify all plan steps in a deep-profile scenario have `requires` and `validates_with` fields
   - Verify micro-profile plan steps have the fields
   - Create a synthetic test: adapter with limited capabilities + plan step requiring more → verify warning appears in family trace

#### Forbidden pseudo-completion (5B)

1. **If plan steps have `requires: []` (empty list) for all phases, 5B is not complete.**
   The requires list must have meaningful capability names, not placeholder empties.

2. **If the family resolver has no capability-check code path, 5B is not complete.**
   The check must exist and produce a warning trace, even if it never blocks.

3. **If the planner contract fields are only in the plan dict but never read by any consumer, 5B is not complete.**
   The family resolver must read `requires` from the plan and compare against adapter capabilities.

#### Acceptance criteria (5B)

| # | Criterion | How to verify |
|---|-----------|---------------|
| 5B.1 | Deep-profile plan steps have non-empty `requires` | Regression: check field in each step |
| 5B.2 | Micro-profile plan steps have non-empty `requires` | Regression: check field |
| 5B.3 | Family resolver produces `capability_warning` on synthetic mismatch | Regression: synthetic test |
| 5B.4 | `validates_with` is set for executing/validating phases | Regression: check field |
| 5B.5 | All existing scenarios pass | Exit 0 |

#### Deliverables (5B)

| File | Change |
|------|--------|
| `polaris_planner.py` | Add `requires` and `validates_with` to `build_steps()` |
| `polaris_contract_planner.py` | Add capability check + warning in `choose_family()` |
| `polaris_regression.sh` | Add plan metadata assertions + synthetic mismatch test |

#### Non-goals (5B)

- Hard enforcement of capability requirements (warning only)
- Per-phase family selection (family is still global per run)
- Contract negotiation between planner and executor
- Full task-contract semantics (this is the first step only)

---

## Dependency chain

```
Step 3A (de-stringify artifacts)
    │
    ▼
Step 3B (resume fix)          ← depends on 3A: resumed artifacts must be clean dicts
    │
    ▼
Step 4A (bootstrap protocol)  ← depends on 3A+3B: manifest must encode clean schemas;
    │                            bootstrap idempotency needs resume-awareness
    ▼
Step 4B (experience migration) ← depends on 4A: version tags set in manifest
    │
    ▼
Step 5A (side-by-side/rollback) ← depends on 4: stable schemas needed for rollback baseline;
                                  v5 snapshot must be taken after all schema changes are done
Step 5B (planner contracts)    ← depends on 4: bootstrap capability lists affect resolver
```

**Why this order, not another:**
- 3A before 3B: resuming with dirty artifacts = schema-inconsistent state
- 3 before 4: bootstrap refactor on stringified artifacts = refactoring twice
- 4A before 4B: version tags must be set in the manifest, not retroactively
- 4 before 5: rollback test needs frozen schema; planner needs settled capability lists

---

## Summary: what constitutes Platform-0 completion

After Steps 0–5, the five mandatory platformization blocks from `platformization-phase0.md` are addressed:

| Block | Covered by |
|-------|------------|
| Schema compatibility contract | Steps 1–2 (v5→v6 gate) + Step 3A (clean artifacts) |
| Runtime-directory compatibility / migration | Steps 1–2 (format marker + gate) + Step 3B (resume) |
| Bootstrap/runtime general capability protocol | Step 4A (manifest with `requires` + capability check at bootstrap time) |
| Semantic migration for experience assets | Step 4B (pattern/rule/backlog version + bridge) |
| Side-by-side / rollback / cross-version regression | Step 5A (v5 state snapshot + rollback test + coexistence test + cross-version state round-trip) + Steps 1–2 (compat gate = new-protects-old). **Note**: 5A provides state-level cross-version evidence, not full old-runtime execution; full old-runtime end-to-end is deferred to P1. |

Planner contract metadata (Step 5B) is the bridge from Platform-0 into capability expansion — it establishes the interface that future P1 work will build on.

After Step 5 passes, Platform-0 is complete and capability expansion can resume.

---

## Coexistence Asymmetry Documentation (5A.5)

### Direction: new code on old dirs (v5 → v6)

- **Lossless**. The compat gate (`polaris_compat.py check-runtime-format`) detects the missing `runtime-format.json`, writes it, and proceeds.
- `load_state()` detects `schema_version: 5`, backfills missing fields, upgrades to v6, adds `compat: {upgraded_from: 5, ...}`.
- All key fields survive: `run_id`, `goal`, `status`, `artifacts`, `state_machine.node`, `learning_backlog`.
- Proven by regression: `compat-legacy-dir-upgrade` (Steps 1–2), `coexist-v5-dir-full-run` (Step 5A).

### Direction: old code on new dirs (v6 → v5 rollback)

- **Lossy but non-destructive**. The old code has no compat gate — it ignores `runtime-format.json` and loads the state via its upgrade path.
- What degrades:
  - `compat` field: lost (v5 `default_state()` does not include it; `upgraded.update(state)` may merge it in but v5 code never reads it)
  - `schema_version`: reverts to 5 (v5 loader forces `upgraded["schema_version"] = 5`)
  - `runtime-format.json`: ignored but not deleted (v5 code does not know about it)
  - `asset_version` fields on patterns/rules/backlog items: pass through (v5 code ignores unknown fields in experience assets)
  - `compat.resumed_count`: lost with `compat` field
  - Plan step `requires` and `validates_with` fields: stripped by v5 minimal-density `write_json` (not in v5 whitelist)
- What survives: `run_id`, `goal`, `status`, `artifacts.selected_adapter`, `state_machine.node`, `state_machine.history` (truncated), `learning_backlog`.
- Proven by regression: `rollback-v6-in-v5-loader`, `cross-version-round-trip` (Step 5A).

### Accepted asymmetry

New code protects old dirs (compat gate refuses incompatible formats). Old code may overwrite new dirs (no gate in old code). This asymmetry is **accepted and documented** — fixing it would require patching already-deployed v5 code, which is out of scope for Platform-0.
