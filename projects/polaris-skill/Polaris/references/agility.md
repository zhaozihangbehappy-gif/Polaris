# Polaris Agility Refactor

Goal: keep Polaris structurally powerful without making everyday execution slow, ceremonious, or over-administered.

## Design Principle

Make Polaris **deep in reserve, light in motion**.

- Keep strong state, repair, adapter, and pattern systems available.
- Only activate expensive machinery when task shape justifies it.
- Separate **doing the current task quickly** from **learning from the task thoroughly**.

## Primary Risks To Prevent

1. Every task triggers the full orchestration stack.
2. State writes become too frequent for short work.
3. Adapter ranking reruns from scratch for familiar scenarios.
4. Success-pattern logic competes with foreground execution.
5. Repair expands into deep diagnosis for shallow failures.
6. Reporting and live surfaces create write amplification.
7. Growth features accumulate faster than dispatch remains agile.

## Refactor Pillars

### 1. Execution Profiles

Introduce three execution profiles and route into the lightest valid one.

#### `micro`
Use for:
- short local tasks
- known tool + known path + low ambiguity
- one-shot edits or bounded checks

Behavior:
- skip full planner
- skip deep adapter ranking
- skip full pattern scan
- skip repair tree unless repeated failure
- write minimal state only

#### `standard`
Use for:
- moderate local tasks
- some uncertainty, but not long-running orchestration
- one fallback path likely enough

Behavior:
- short planner
- shortlist adapters instead of full deliberation
- top-1 pattern only
- shallow repair first
- phase-level status surfaces

#### `deep`
Use for:
- long tasks
- failure-prone tasks
- resumable multi-step work
- cross-tool local orchestration
- work that benefits from explicit branching/recovery/state surfaces

Behavior:
- full Polaris orchestration
- rich state machine
- full repair depth escalation available
- durable runtime surfaces and detailed event logs

### 2. Hot Path vs Cold Path

Keep foreground execution thin.

#### Hot path
Must stay fast:
- route profile
- choose tool quickly
- act
- validate
- continue

#### Cold path
Can run at task end, phase end, or deferred:
- success-pattern merge
- confidence updates
- lifecycle promotion
- history compaction
- rule promotion decisions
- richer reporting snapshots

Rule: do not let learning work delay the next effective action unless the task is already in `deep` mode or explicitly blocked.

### 3. State Density Levels

Keep the state machine, but scale write density.

#### `minimal`
Store only:
- run_id
- goal
- mode/profile
- phase
- current_step
- next_action
- selected_adapter
- summary outcome
- blocked reason (if any)

#### `full`
Store the existing richer structure:
- branches
- recovery
- references
- attempts
- history_summary
- durable status surfaces
- detailed artifacts

Rule:
- `micro` defaults to `minimal`
- `standard` defaults to `minimal` with selective upgrades
- `deep` defaults to `full`

### 4. Sticky Adapter Selection

Avoid recomputing full adapter ranking for familiar scenarios.

Add a scenario fingerprint using:
- required capabilities
- mode/profile
- failure_type (if any)
- trust ceiling
- cost ceiling
- durable-status requirement

If a recent adapter succeeded for the same fingerprint and prerequisites still pass:
- reuse it directly
- optionally emit a lightweight `sticky_reuse` reason

Only rerank when:
- prerequisites fail
- adapter recently failed in same fingerprint
- user constraints changed
- trust/cost envelope changed
- task escalates to deeper profile

### 5. Repair Depth Escalation

Do not open a full repair tree on first contact.

#### `shallow`
- classify failure
- distinguish repairable vs explicit stop conditions
- retry or switch fallback if obvious
- at most a few probes

#### `medium`
- narrow diagnostic probes
- confirm environment, path, or config direction
- still avoid wide branching

#### `deep`
- full repair tree
- explicit evidence collection
- branch/recovery tracking

Rule:
- default to `shallow`
- escalate only on repeated failure, blocked progress, or deep profile

### 6. Event and Surface Budgets

Visibility must not create drag.

#### `micro`
- 1 start signal
- 1 completion or block signal

#### `standard`
- one event per major phase
- lightweight live surface only when state materially changes

#### `deep`
- full existing behavior is allowed

Rule: never write a richer surface than the task profile needs.

### 7. Two-Stage Success Capture

Split foreground guidance from background consolidation.

#### Online success marker
Cheap write during/after a successful run:
- pattern_id candidate
- adapter used
- brief evidence pointer
- result status

#### Offline consolidation
Heavier work done after success or at phase end:
- merge evidence
- update confidence
- infer best lifecycle
- run promotion logic
- compact history

This preserves learning without letting pattern management slow immediate execution.

## Required Schema Evolution

### State
Add:
- `execution_profile`: `micro | standard | deep`
- `state_density`: `minimal | full`
- `repair_depth`: `shallow | medium | deep`
- `learning_backlog`: queued pattern/rule updates not yet consolidated
- `event_budget`: optional numeric or symbolic budget per profile

### Runtime / Selection Cache
Add a lightweight cache file or state subobject for sticky adapter reuse:
- scenario fingerprint
- selected adapter
- last success timestamp
- prerequisite snapshot
- failure count / last failure timestamp

### Success Patterns
Add separation between:
- lightweight online markers
- consolidated pattern store updates

## Dispatch Rules

### Prefer the lightest valid profile
Start optimistic, escalate only when evidence says so.

Suggested initial routing:
- one-file edit / one command / one check -> `micro`
- medium local task with small ambiguity -> `standard`
- long task, resumable work, multi-step coordination, failure-prone path -> `deep`

### Escalate, do not overstart
Allowed escalation:
- `micro -> standard`
- `standard -> deep`

Avoid de-escalating mid-run unless resuming from a new invocation.

## Acceptance Criteria

### Agility
- short tasks do not run full deep orchestration by default
- first effective action happens faster than current full-stack path
- adapter reuse works for repeated similar local scenarios
- shallow failures do not immediately trigger full repair trees

### Runtime Stop Semantics
- explicit stop classifications are preserved instead of being collapsed into repair
- non-repair denials still stop immediately
- deeper automation only activates when the current run remains repairable

### Learning Quality
- success-pattern quality does not regress
- rerun stability remains monotonic/evidence-bounded
- cold-path consolidation preserves auditable history

### Observability
- deep mode keeps rich visibility
- micro/standard modes remain visible enough without noisy write amplification

## Rollout Order

### Phase 1 — Dispatch and profile foundations
Implement first:
1. execution profiles in orchestrator
2. state density control in state/runtime layers
3. event budget / lighter reporting behavior

### Phase 2 — Fast reuse
Implement next:
1. sticky adapter cache
2. shallow/medium/deep repair depth routing

### Phase 3 — Learning decoupling
Implement after the above:
1. online success markers
2. offline consolidation path for patterns and rules

## Anti-Goals

Do not:
- remove explicit state entirely
- remove repair capability entirely
- remove success-pattern learning entirely
- make deep mode impossible
- trade explicit stop semantics for speed

The target is not a weaker Polaris.
The target is a Polaris that stays sharp by default and unfolds depth only when needed.
