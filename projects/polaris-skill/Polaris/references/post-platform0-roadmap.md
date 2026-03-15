# Post–Platform-0 Roadmap: From Infrastructure to Impact

_Gate contract — 2026-03-15 (rev 2: incorporates OpenClaw + Codex audit + owner directive)_
_Author: Claude (to be audited by OpenClaw and Codex)_
_Baseline: Platform-0 ALL STEPS COMPLETE, regression EXIT=0 from project root and `/tmp`_
_Main line: Route A (open-source skill). Routes B/C/D derive from A, not parallel._
_Owner directive: before any external publish, Polaris must be deployed on the owner's local OpenClaw and demonstrate a qualitative leap. Claude and Codex are both responsible for testing and maintaining it._

---

## Strategic Principle

**Platform-0 proved Polaris is safely evolvable. The next work proves it is useful.**

The gap: today Polaris has ~97% infrastructure and ~3% real execution. Every regression scenario runs through `polaris_runtime_demo.sh` with simulated errors. No scenario executes a real user task, captures a real experience, and replays it to measurably improve a second run.

The roadmap has four phases. Each phase has a hard gate. No phase starts before the prior gate passes.

---

## Experience Capability Layers × Delivery Phases

Polaris's经验能力has five depth layers. The delivery phases are not independent of these layers — each phase targets a specific layer ceiling:

| Layer | Capability | Description | Enters at Phase | User perception |
|-------|-----------|-------------|-----------------|----------------|
| L1 | Recording | Record what happened (command, result, duration) | Phase 1A-1B | "It remembers what I did" |
| L2 | Path Pruning | Skip paths known to fail, prefer paths known to succeed | **Phase 1C** | **"It learned from my mistakes"** — first moment users feel the skill is intelligent |
| L3 | Semantic Generalization | `deploy.sh` experience transfers to `deploy-staging.sh` | Phase 2C+ | "It recognizes similar tasks" |
| L4 | Causal Reasoning | Knows "failed because port 8080 was occupied", not just "stderr had error" | Phase 3+ | "It understands why things fail" |
| L5 | Strategy Emergence | Autonomously decides "check port before deploy" | No current engineering path | "It anticipates problems" |

**Critical design implication**: Phase 1C's `experience_hints` must be designed for L2 (path pruning), not just L1 (replay). The difference:

| | L1: Pure Replay | L2: Path Pruning |
|---|---|---|
| Success hint | "Last time used `--force` flag" | "Last time used `--force` flag" |
| Failure hint | _(none — L1 only records success)_ | **"Last time failed without `--force`, skip that path"** |
| Adapter behavior | Copy last success | Avoid known failures + prefer known successes |
| Regression proof | `real-experience-replay` | **`real-experience-avoids-failure`** |

**Phase 1 gate is set at L2, not L1.** A skill that only replays successes is a macro recorder. A skill that also avoids known failures is an experience accumulator. The `real-experience-avoids-failure` scenario is the L2 proof — without it, Phase 1 is incomplete.

**L3 is the Phase 2 stretch target.** Multi-task experience isolation (2C) requires defining "task similarity" — this is the natural entry point for semantic generalization. Phase 2 must at minimum support exact-match task fingerprinting (L2), but the architecture should not preclude fuzzy matching (L3).

**L4-L5 are post-SDK.** Causal reasoning requires structured error analysis beyond string matching. Strategy emergence requires enough L2-L3 data to discover patterns across patterns. Both are gated on SDK stability + real-world usage data, not on engineering capability.

---

## Phase 1: Real Experience Loop (体验闭环)

### Goal

One end-to-end cycle: user invokes Polaris on a real local task → task runs → experience captured → same task type invoked again → Polaris applies captured experience → measurable improvement (fewer retries, faster completion, or avoided known failure).

### Why this is Phase 1

Without this loop working on at least one real scenario, Polaris is an orchestration framework, not an experience accumulation skill. Everything downstream (release, SDK, adoption) depends on this loop being real.

### Must-do

#### 1A. Real Execution Adapter

Today `polaris_task_runner.py` simulates execution. Phase 1 needs at least one adapter that executes real work:

| Candidate adapter | What it does | Why it's a good first target |
|---|---|---|
| `shell-command` | Runs a user-provided shell command, captures stdout/stderr/exit code | Minimal scope, maximum generality |

Implementation scope:
- New file: `polaris_adapter_shell.py`
- Accepts: command string, working directory, timeout
- Returns: `{ "status": "ok"|"failed", "exit_code": int, "stdout": str, "stderr": str, "duration_ms": int }`
- Contract: must produce a runner-result-compatible artifact so existing validator works
- `polaris_bootstrap.json`: add `shell-command` adapter entry with `capabilities: ["local-exec"]`
- `polaris_orchestrator.py`: route `execution_kind: "shell_command"` to the new adapter

**Code anchors**:
- `polaris_task_runner.py:1` — current simulated runner, reference for result contract
- `polaris_orchestrator.py:choose_execution_kind()` — dispatch point for new adapter
- `polaris_bootstrap.json` — adapter manifest

#### 1B. Experience Capture from Real Execution

Today `consolidate_backlog()` runs after orchestration, but the captured patterns are from simulated runs. Phase 1 needs:

- Success pattern captured from a real `shell-command` execution includes: actual command, actual working directory, actual exit code, actual duration
- Failure classification from a real `shell-command` failure includes: actual stderr, actual exit code
- `polaris_success_patterns.py capture`: the `trigger`, `sequence`, `outcome` fields must reflect real execution data, not orchestrator-generated placeholders

**Code anchors**:
- `polaris_success_patterns.py:capture` command — where pattern fields are set
- `polaris_orchestrator.py:consolidate_backlog()` — where backlog items are built from execution results
- `polaris_repair.py:classify()` — where failure type is determined from real error output

#### 1C. Experience Replay — L2 Path Pruning (经验回放 — 路径剪枝)

**Layer target: L2 (path pruning), not just L1 (replay).**

Today `select_best_pattern()` picks a pattern and the orchestrator records it in state, but **the selected pattern does not influence execution**. Phase 1 needs both success replay AND failure avoidance:

**Experience hint protocol — restricted primitives (Codex rev3 High resolution):**

Experience hints are NOT free-text suggestions. They are **structured, typed operations** drawn from a closed set of primitives. Each adapter declares which primitives it supports. For supported primitives, the adapter MUST apply or MUST explicitly reject with `unsupported_hint` evidence in the result trace.

Allowed hint primitives (Phase 1 set — may be extended in later phases):

| Primitive | Semantics | Example |
|-----------|-----------|---------|
| `append_flags` | Append CLI flags to the command | `{"kind": "append_flags", "flags": ["--force", "--verbose"]}` |
| `set_env` | Set environment variables before execution | `{"kind": "set_env", "vars": {"PORT": "8081"}}` |
| `rewrite_cwd` | Change working directory | `{"kind": "rewrite_cwd", "cwd": "/app/staging"}` |
| `set_timeout` | Override default timeout | `{"kind": "set_timeout", "timeout_ms": 30000}` |

Adapter support declaration (in `polaris_bootstrap.json` adapter entry):
```json
{
  "adapter_id": "shell-command",
  "capabilities": ["local-exec"],
  "supported_hint_kinds": ["append_flags", "set_env", "rewrite_cwd", "set_timeout"]
}
```

Hint assembly flow:
1. Orchestrator queries success pattern store → extracts `prefer` hints (structured primitives from prior success)
2. Orchestrator queries failure record store → extracts `avoid` hints (structured primitives to prevent prior failure)
3. Orchestrator assembles `experience_hints: { "prefer": [hint...], "avoid": [hint...] }`
4. Orchestrator filters hints to only those in adapter's `supported_hint_kinds`
5. Adapter receives filtered hints. For each supported hint: MUST apply or MUST reject with `{"unsupported_hint": hint, "reason": "..."}` in result trace
6. Result records: `"experience_applied": [list of applied hint kinds]`, `"experience_rejected": [list of rejected hints with reasons]`

**Success path (L1 baseline):**
- When a matching success pattern exists, the orchestrator extracts structured prefer-hints (e.g., `append_flags: ["--force"]`)
- Adapter applies supported hints before execution
- Result records which hints were applied

**Failure path (L2 — the critical differentiation):**
- When a matching failure record exists for the current task, the orchestrator extracts structured avoid-hints (e.g., `append_flags: ["--force"]` derived from "last time failed without `--force`")
- Avoid-hints are generated from failure records by the orchestrator's `build_avoidance_hints()` function, which maps `error_class` + `repair_classification` → concrete primitives
- Adapter applies avoid-hints **before** execution, not after reproducing the failure

**Conflict resolution:** if `prefer` and `avoid` contain contradictory hints for the same primitive kind, `avoid` wins (safety over optimization).

**Unknown hint kinds:** if a future failure record produces a hint kind not in the adapter's `supported_hint_kinds`, the orchestrator logs `{"unsupported_hint_kind": kind, "adapter": adapter_id}` in the trace and proceeds without it — no hard failure.

**Failure experience storage — binding decision (Codex High #1 resolution):**

The failure avoidance data goes into a **dedicated failure store** (`failure-records.json`), NOT into the success pattern store. Rationale:

| Option | Rejected because |
|--------|-----------------|
| Success pattern store with `lifecycle_state: "retired"` | Retired is a negative lifecycle state in `polaris_success_patterns.py:47`; `is_active()` filters it out. Mixing failure semantics into success-pattern ranking/selection would create semantic conflicts. Codex is right — this would need to be ripped out later. |
| Rules store | Rules are policy (general behavioral constraints), not per-task empirical failure records. Mixing them pollutes the rule layer's semantics. |
| **Dedicated failure store** (`polaris_failure_records.py`) | **Selected.** Clean separation: success patterns track "what worked", failure records track "what failed and why". The orchestrator queries both stores and assembles `experience_hints: { "prefer": [...], "avoid": [...] }`. |

**Task fingerprint contract (front-loaded from Phase 2C — Codex rev3 Medium #1 resolution):**

The task fingerprint is the primary key for both success patterns and failure records. It MUST be defined in Phase 1, not deferred to Phase 2, because both stores use it from day one.

New file: `polaris_task_fingerprint.py`
- Single responsibility: compute and store task fingerprints
- Every fingerprint is a dict with three layers:

| Field | Purpose | Example |
|-------|---------|---------|
| `raw_descriptor` | Original user input, verbatim | `"deploy.sh --env staging"` |
| `normalized_descriptor` | Canonicalized form (sorted args, resolved paths) | `"deploy.sh --env=staging"` |
| `matching_key` | Deterministic hash for exact-match lookup | `sha256(normalized_descriptor + cwd)` |

- `compute(command: str, cwd: str, task_name: str | None = None) → TaskFingerprint`
- `matches(fp_a: TaskFingerprint, fp_b: TaskFingerprint) → bool` — exact-match on `matching_key` (L2); this function is the future L3 extension point
- Success patterns and failure records both store the full fingerprint dict, not just the hash

This means Phase 2C's task isolation work inherits an already-stable fingerprint contract instead of inventing one and migrating.

New file: `polaris_failure_records.py`
- `record(fingerprint: TaskFingerprint, command, error_class, stderr_summary, repair_classification) → failure_record`
- `query(fingerprint: TaskFingerprint) → list[failure_record]` — returns all known failures matching this fingerprint
- `load_store(path)` / `write_store(path)` — same pattern as `polaris_success_patterns.py`, with `asset_version` from day one
- Each record: `{ "task_fingerprint": TaskFingerprint, "command": str, "error_class": str, "stderr_summary": str, "repair_classification": str, "avoidance_hints": [structured hint primitives], "recorded_at": str, "asset_version": 2 }`
- The orchestrator calls `query()` alongside `select_best_pattern()` and merges results into `experience_hints`

**Why L2 is the minimum, not a stretch goal:**
A skill that only replays successes is equivalent to shell history + alias. The moment Polaris says "I'm not going to do it the way that failed last time" is the moment users perceive genuine intelligence. This is the entire value proposition.

**Code anchors**:
- `polaris_orchestrator.py` — pattern selection result is in `state.artifacts.selected_pattern`
- `polaris_success_patterns.py:select_best_pattern()` — returns pattern with `strategy_hints`
- `polaris_success_patterns.py:47` — `is_active()` filters retired patterns; failure records must NOT go here
- `polaris_repair.py:classify()` — failure classification output, source of `error_class` for failure records
- New: `polaris_failure_records.py` — dedicated failure experience store
- New: adapter interface gains `experience_hints: { "prefer": [...], "avoid": [...] }` parameter

#### 1D. Regression: Real Experience Loop

New regression scenarios (all must use `POLARIS_ROOT`, pass from `/tmp`):

| Scenario | What it proves | Layer |
|---|---|---|
| `real-shell-success` | `shell-command` adapter runs `echo hello`, captures result, success pattern recorded | L1 |
| `real-shell-failure-classified` | `shell-command` adapter runs a command that fails → `polaris_repair.py` classifies real stderr → failure record written to failure store. **Does NOT require repair-then-success.** Only proves: real failure → real classification → real recording. | L1 |
| `real-experience-replay` | Run 1: `shell-command` succeeds, pattern captured. Run 2: same task type, pattern selected, `experience_hints.prefer` passed to adapter, `experience_applied: true` in result | L1→L2 |
| `real-experience-avoids-failure` | Run 1: command fails with specific error, failure record captured. Run 2: same task fingerprint, Polaris reads failure store, passes `experience_hints.avoid` to adapter, adapter modifies execution **before running**, avoids the prior failure path. **The adapter must NOT reproduce the failure first.** | L2 |

**Codex High #2 resolution**: the old `real-shell-failure-repair` conflated "repair classifies stderr" with "repair auto-fixes and succeeds". Now split into `real-shell-failure-classified` (proves classification) and `real-experience-avoids-failure` (proves experience-driven avoidance). Repair's job is classification and probe, not automatic fixing — the roadmap no longer pretends otherwise.

### Acceptance Criteria (Phase 1)

| # | Criterion | Verification |
|---|-----------|-------------|
| 1.1 | `shell-command` adapter executes real commands and produces runner-result-compatible output | `real-shell-success` scenario |
| 1.2 | Real execution failures are classified by `polaris_repair.py` using actual stderr, and failure record written to dedicated failure store | `real-shell-failure-classified` scenario |
| 1.3 | Success patterns from real executions contain actual command/exit_code/duration | Inspect pattern store after `real-shell-success` |
| 1.4 | Second run of same task type selects prior pattern and passes `experience_hints.prefer` to adapter | `real-experience-replay` scenario |
| 1.5 | Experience replay produces measurable difference: must include at least one of: (a) fewer retries, (b) avoided a previously observed failure path, (c) reduced stage count, (d) reduced adapter selection cost. **`experience_applied: true` alone is NOT sufficient** — there must be an observable behavioral difference in the execution trace | `real-experience-avoids-failure` scenario |
| 1.6 | Failure records stored in dedicated failure store, not in success pattern store | Inspect `failure-records.json` after `real-shell-failure-classified`; inspect `success-patterns.json` has zero failure-type entries |
| 1.7 | Task fingerprints in both success patterns and failure records contain all three layers (`raw_descriptor`, `normalized_descriptor`, `matching_key`) | Inspect both stores after any Phase 1 scenario |
| 1.8 | Experience hints are structured primitives from the closed set (`append_flags`, `set_env`, `rewrite_cwd`, `set_timeout`), not free-text | Inspect `experience_hints` in execution trace after `real-experience-avoids-failure` |
| 1.9 | `shell-command` adapter declares `supported_hint_kinds` in bootstrap manifest | Inspect `polaris_bootstrap.json` |
| 1.10 | For supported hint kinds, adapter either applies or explicitly rejects with `unsupported_hint` evidence | Inspect result trace after `real-experience-replay` and `real-experience-avoids-failure` |
| 1.11 | All Platform-0 regression scenarios still pass | EXIT=0 |

### Veto (Phase 1)

1. **`shell-command` adapter only works with simulated commands** (e.g., hardcoded `echo` inside adapter code) → Phase 1 fails.
2. **Captured patterns contain placeholder data instead of real execution results** → Phase 1 fails.
3. **Pattern selection happens but selected pattern has zero influence on the next execution** → Phase 1 fails. The experience loop is broken at the replay step.
4. **`real-experience-avoids-failure` does not demonstrate a concrete before/after difference** → Phase 1 fails. "Experience accumulation" without observable improvement is decoration.
5. **Adapter applies experience hints only AFTER reproducing the prior failure once** → Phase 1 fails. L2 path pruning means avoiding the failure path before execution, not recovering faster after hitting it again. If the second run still fails first and then applies hints, it is repair optimization, not experience replay.
6. **Experience hints contain free-text fields** (e.g., `"suggested_modification": "add --force"`) instead of structured primitives from the closed set → Phase 1 fails. Free-text hints push the semantic boundary problem onto the adapter, which has no safe way to interpret arbitrary suggestions. Only typed primitives (`append_flags`, `set_env`, `rewrite_cwd`, `set_timeout`) are allowed.
7. **Task fingerprint is a single opaque hash without preserving `raw_descriptor` and `normalized_descriptor`** → Phase 1 fails. A hash-only fingerprint makes L3 fuzzy matching impossible without migrating all existing records.

---

## Phase 2: Local OpenClaw Deployment — Proven Value (本地部署验证)

### Goal

Polaris deployed on the owner's local OpenClaw instance, demonstrating a **qualitative leap** in agent task execution. Claude and Codex are both responsible for testing and maintaining it. This is NOT a packaging exercise — it is a production proof on a real agent.

**Only after this gate passes does external publishing (ClawHub) become relevant.**

### Entry Criteria

Phase 1 gate passed. Real experience loop works for at least one adapter.

### Must-do

#### 2A. Skill Manifest & Entry Point

- `POLARIS_TASK.md` or equivalent skill manifest that the local OpenClaw can discover
- Single entry point: `polaris run <command>` or equivalent — user does not need to know about orchestrator, planner, state, bootstrap
- First-run experience: if no runtime dir exists, auto-bootstrap with defaults
- Runtime dir defaults to `~/.polaris/` or `$POLARIS_HOME` (not project-internal path)
- **Platform-0 compatibility constraint (Codex Medium #1)**: default runtime home MUST retain `runtime-format.json` version marker, support compat read/write, and preserve side-by-side/rollback semantics. Multiple Polaris versions or skill instances sharing a machine must not corrupt each other's runtime dirs. "User directory is more convenient" does not override Platform-0's compatibility contract.

**Code anchors**:
- `polaris_runtime_demo.sh` — current entry point, must be replaced or wrapped by a user-facing CLI
- `polaris_bootstrap.py` — auto-bootstrap logic already exists, needs to be triggered on first run
- `polaris_compat.py` — runtime format gate, must be invoked on every run even with user-facing CLI
- `/home/administrator/.openclaw/workspace/projects/polaris-skill/specs/POLARIS_TASK.md` — existing spec file

#### 2B. User-Facing Output

Today all output is JSON artifacts in a runtime dir. A user needs:

- Human-readable summary after each run: what happened, what was learned, what will be different next time
- Use existing `polaris_report.py` / `polaris_emit_text.py` — extend, don't replace
- Output format: concise terminal text, not JSON dump

**Code anchors**:
- `polaris_report.py` — existing reporter
- `polaris_emit_text.py` — existing text emitter

#### 2C. Multi-Task Experience Isolation (L3 Entry Point)

**Layer target: L2 minimum (exact task fingerprint match), L3 architecture-ready (fuzzy match extension point).**

Today all runs share one runtime dir. When a user runs different tasks, experiences must not cross-contaminate:

- Pattern matching scoped by task fingerprint (contract already defined in Phase 1C via `polaris_task_fingerprint.py`)
- Rules remain global (they encode general policies, not task-specific patterns)
- State per-task or per-task-family
- **L3 extension**: replace `polaris_task_fingerprint.matches()` exact-match implementation with a fuzzy variant that operates on `normalized_descriptor` or `raw_descriptor`. The three-layer fingerprint contract from Phase 1 ensures old patterns remain queryable — no migration needed.
- Phase 2C does NOT implement L3 fuzzy matching, but must verify that swapping the match function does not require schema changes to existing stores

#### 2D. Local OpenClaw Integration Testing

**This is the core of Phase 2, not documentation.**

- Deploy Polaris as a skill on the owner's local OpenClaw
- Claude and Codex both run real tasks through OpenClaw + Polaris, on at least 3 different task types
- Collect evidence of qualitative improvement: before/after comparison on repeated tasks
- Fix integration issues discovered during real use — this is expected to surface problems that regression tests miss
- Maintain the deployment: if OpenClaw updates break Polaris, Claude or Codex must fix it

#### 2E. Documentation

- `README.md` rewritten for end users (not internal development notes)
- 3 usage examples: (1) simple command, (2) repeated command showing experience improvement, (3) failure → avoidance on second run
- No architecture diagrams or internal references — user-facing only

### Acceptance Criteria (Phase 2)

| # | Criterion | Verification |
|---|-----------|-------------|
| 2.1 | `polaris run "echo hello"` works with zero prior setup | Fresh machine test (new temp dir, no pre-existing runtime) |
| 2.2 | Second run of same command produces human-readable "experience applied" message | Terminal output check |
| 2.3 | Two different commands produce isolated experience stores | Run command A and B, verify A's patterns don't leak into B's selection |
| 2.4 | Polaris deployed and functional on owner's local OpenClaw | `openclaw skill list` shows Polaris; real tasks execute through it |
| 2.5 | Qualitative improvement demonstrated on ≥3 real task types | Before/after evidence collected by Claude and Codex |
| 2.6 | Default runtime dir respects Platform-0 compatibility contract (version marker, compat gate, side-by-side safety) | Regression: two Polaris versions using same `~/.polaris/` do not corrupt each other |
| 2.7 | Task fingerprint contract (inherited from Phase 1) still intact — no schema drift | Inspect fingerprint fields in stores match Phase 1 contract |
| 2.8 | Claude and Codex have both independently tested the deployment | Test logs from both agents |

### Veto (Phase 2)

1. **User must edit any config file before first run** → Phase 2 fails. Zero-config or nothing.
2. **Output is raw JSON with no human-readable summary** → Phase 2 fails.
3. **Experience from task A influences task B** → Phase 2 fails. Cross-contamination breaks trust.
4. **Polaris is not actually deployed on local OpenClaw** → Phase 2 fails. Packaging without local production proof is premature.
5. **Default runtime dir does not enforce Platform-0 compatibility gate** → Phase 2 fails. Convenience does not override safe evolution.

---

## Phase 2.5: External Publish (外部发布)

### Goal

After local OpenClaw proves value, publish to ClawHub or equivalent marketplace.

### Entry Criteria

Phase 2 gate passed. Owner confirms qualitative leap is real, not just test artifacts. ClawHub API/interface available.

### Must-do

- Adapt skill manifest to ClawHub packaging requirements (unknown until API available)
- README finalized based on real local deployment experience
- Any integration issues found in Phase 2 are fixed

### Acceptance Criteria

| # | Criterion | Verification |
|---|-----------|-------------|
| 2.5.1 | Skill discoverable and installable via ClawHub | External user can find and install |
| 2.5.2 | A user who has never seen the code can get value in under 5 minutes | External reviewer test |

---

## Phase 3: SDK Extraction (SDK 化)

### Goal

Core Polaris logic (experience capture, pattern matching, failure classification, state machine) is importable as a Python library with <10 public functions, no CLI dependency, no file-path assumptions.

### Entry Criteria

Phase 2 gate passed. At least 10 real users have used the skill and provided feedback. Pattern/rule/state interfaces are stable (no breaking changes in 2+ weeks).

### Must-do (directional — will be refined after Phase 2 feedback)

#### 3A. Interface Extraction

- `polaris_core` package with:
  - `PolarisSession` — manages state, patterns, rules for one task execution
  - `capture(result) → Pattern` — records execution outcome
  - `match(task_descriptor) → Pattern | None` — finds relevant prior experience
  - `classify_failure(error) → FailureType` — categorizes errors
  - `should_retry(failure, history) → bool` — retry/stop decision
- No subprocess calls, no argparse, no file I/O in core (I/O in adapters only)

#### 3B. Storage Backend Abstraction

- `StorageBackend` protocol: `load(key) → dict`, `save(key, payload)`
- Default: `FileBackend` (current JSON files)
- Future: `MemoryBackend` (for testing), `APIBackend` (for Route D)

#### 3C. Package & Distribution

- `pyproject.toml`, published to PyPI
- `pip install polaris-experience` → ready to use in 3 lines:
  ```python
  from polaris_core import PolarisSession
  session = PolarisSession()
  hint = session.match({"command": "deploy.sh", "cwd": "/app"})
  ```

### Acceptance Criteria (Phase 3)

| # | Criterion | Verification |
|---|-----------|-------------|
| 3.1 | `import polaris_core` works with no side effects | Unit test: import in clean venv |
| 3.2 | Full experience loop (capture → match → replay) works via API, no CLI | Integration test |
| 3.3 | `StorageBackend` protocol allows swapping file backend for memory backend | Unit test with `MemoryBackend` |
| 3.4 | Published to PyPI, installable via pip | `pip install polaris-experience` in clean venv |
| 3.5 | API surface ≤ 10 public functions/classes | Automated check |

---

## Phase 4: Framework Integration (框架集成)

### Goal

At least one major agent framework (LangChain agents, AutoGPT, Claude Code, OpenClaw) integrates `polaris-experience` SDK and ships experience accumulation to their users.

### Entry Criteria

Phase 3 gate passed. SDK is stable (no breaking changes in 4+ weeks). At least 100 pip installs from non-team users.

### Must-do (directional — will be refined after Phase 3)

- Integration guide: "Add experience accumulation to your agent in 15 minutes"
- Reference integration for one framework (likely OpenClaw, since it's the home ecosystem)
- Performance contract: experience lookup adds <50ms to agent execution latency (hot path budget)
- Telemetry: opt-in metrics showing experience hit rate, replay success rate

### Success Signal

- Framework ships a release with Polaris experience integration
- Users of that framework see "experience applied" in their agent runs without knowing Polaris exists

---

## Route Derivation Map

How Routes B/C/D derive from Route A work at each phase:

| Phase | Route A (skill) deliverable | Route B (protocol) derivative | Route C (SDK) derivative | Route D (cloud) derivative |
|---|---|---|---|---|
| Phase 1 | Real experience loop | — | — | — |
| Phase 2 | Local OpenClaw deployment + proven value | Task fingerprint contract → draft spec seed | — | — |
| Phase 2.5 | External publish (ClawHub) | Pattern/rule/failure JSON schema → draft spec | — | — |
| Phase 3 | — | Spec formalized from SDK interfaces | **Main deliverable** | `APIBackend` implements `StorageBackend` |
| Phase 4 | — | Multi-framework adoption validates spec | SDK integrated into framework | Cloud backend available for team sync |

Each route activates only when Route A's work creates the natural substrate for it. No parallel investment needed.

---

## Distance Estimate

| Phase | Scope | Primary constraint |
|---|---|---|
| Phase 1 | Real adapter + capture + replay + failure avoidance | Engineering (weeks) |
| Phase 2 | Local OpenClaw deployment + real-task proof | Engineering + integration + maintenance (weeks) |
| Phase 2.5 | External publish | ClawHub API availability (blocked until available) |
| Phase 3 | Refactor to library | Engineering + API design (weeks, after real-user feedback stabilizes interfaces) |
| Phase 4 | External adoption | Ecosystem + relationships (months, mostly not engineering) |

**Total engineering distance to "owner sees qualitative leap on local OpenClaw" (end of Phase 2): order of magnitude = weeks, not months.**

Phase 2.5 is blocked on ClawHub API availability. Phase 3-4 depend on external factors that cannot be engineered faster.

---

## Testing & Maintenance Responsibility

| Agent | Responsibilities |
|-------|-----------------|
| **Claude** | Implement all phases. Run regression after every change. Test Polaris on local OpenClaw during Phase 2. Fix integration issues. |
| **Codex** | Audit every phase gate. Independently test Polaris on local OpenClaw during Phase 2. Report findings with code-anchored evidence. |
| **Both** | Maintain the local OpenClaw deployment. If OpenClaw updates or environment changes break Polaris, the agent who discovers the breakage is responsible for fixing it or escalating to the owner. |

---

## Layer Progression Contract

Each layer has an explicit entry gate and proof artifact:

| Layer | Entry Gate | Proof Artifact | Hard Dependency |
|-------|-----------|---------------|----------------|
| L1 | Phase 1A-1B complete | `real-shell-success`: real execution + real capture | None |
| L2 | Phase 1C complete | `real-experience-avoids-failure`: failure avoidance demonstrated | L1 (must have real data to prune) |
| L3 | Phase 2C complete + ≥50 accumulated patterns from real users | Fuzzy match returns useful results on related-but-not-identical tasks | L2 + user data (similarity needs diverse examples) |
| L4 | Phase 3 SDK stable + external error analysis integration | Failure classification includes causal chain, not just string match | L3 + structured error corpus |
| L5 | L4 proven on ≥3 task families + sufficient L2-L3 pattern volume | Agent proposes a strategy not seen in any prior execution | L4 + statistical significance |

**L1-L2 are engineering deliverables (Phase 1).** L3 is an engineering + data deliverable (Phase 2-3). L4-L5 are research deliverables — they require hypotheses, experiments, and may not succeed on first attempt.

---

## What This Roadmap Does NOT Cover

- L4-L5 implementation details — these are research problems, not engineering tasks; they will get their own gate contracts when L3 is proven
- Multi-language SDK (Python first, others follow demand)
- Pricing/business model (Route D concern, irrelevant until Phase 4)
- Marketing/community building — out of scope for engineering roadmap
