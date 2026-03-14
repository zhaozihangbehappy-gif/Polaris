# Polaris Architecture

## Overview

Polaris is a local-first orchestration pattern for long or failure-prone work. It avoids a monolithic autonomous loop by separating planning, execution, repair, reporting, rules, and adapter choice into small auditable parts.

## Components

### Planner

- Builds short ordered steps with `phase`, `rule_layers`, and `success_signal`
- Keeps plans resumable and concrete

### State Machine

- Maintains lifecycle nodes: `intake`, `planning`, `ready`, `executing`, `repairing`, `validating`, `blocked`, `completed`
- Makes retries, blocked states, repair branches, and recovery references explicit instead of implicit loops

### Orchestrator

- Coordinates the modules without owning their logic
- Reads rules, selects adapters, advances state, emits reports, and captures reusable outcomes

### Reporter

- Produces append-only JSONL events plus a current status snapshot
- Uses the same fields for human and machine inspection

### Repair Engine

- Classifies local failures
- Marks explicit non-repair denials as stop classifications
- Suggests a rule layer for future capture when relevant

### Repair Action Layer

- Converts diagnosis into bounded local action trees
- Executes only reversible, auditable actions
- Refuses automatic execution when the failure is already classified as a stop condition

### Rule Store

- Stores layered rules only
- Supports evidence-based rule iteration without mixing in pattern lifecycle

### Success Pattern Store

- Stores reusable sequences separately from rules
- Tracks confidence, promotion, demotion, expiry, adapter linkage, and selection history

### Adapter Registry

- Registers tool metadata declaratively
- Supports ranking by capability, mode, trust level, cost, latency, selectors, and fallback coverage

## Data Flow

1. Initialize state and active rule layers.
2. Create a plan.
3. Select rules, rank adapters, and select prior success patterns for the next phase.
4. Execute and report.
5. If a failure occurs, branch into `repairing`.
6. Diagnose, probe, return to `ready` or stop at `blocked`.
7. Validate outputs and capture rules and success patterns in their dedicated stores.
8. Finish with a reviewable state snapshot and event trail.

## Design Properties

- Local-first: all runtime artifacts are local files
- Modular: each script owns a single concern
- Layered: hard route/stop rules and soft heuristics stay separate
- Extensible: new adapters and rules do not require orchestrator rewrites
- Auditable: every significant decision lands in JSON
