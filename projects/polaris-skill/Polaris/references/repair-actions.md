# Repair Actions

## Purpose

Move from diagnosis to bounded local action without confusing troubleshooting with policy evasion.

## Flow

1. `diagnose` classifies the failure and routes it to `shallow`, `medium`, or `deep`.
2. `plan` creates a controlled local action tree with an execution order and safety gate.
3. `execute` runs only reversible local leaves when the plan is safe.

## Depth Routing

- `shallow`: first-failure pass for `micro` and `standard`; keep probes to a very small budget.
- `medium`: use after repeated failure or blocked progress; expand evidence collection without opening the full tree.
- `deep`: preserve the full repair tree for `deep` profile work.
- Boundary and approval failures still stop immediately instead of escalating.

## Current Trees

- `dependency_probe_tree`: interpreter, executable, pip, and package visibility probes
- `tool_probe_tree`: PATH and local tool-resolution probes
- `path_probe_tree`: working-directory and nearby-file inspection
- `generic_probe_tree`: minimum evidence collection
- `boundary_stop`: explicit no-execute stop for safeguard or approval boundaries

## Rule

Automatic repair action execution must stay local, reversible, auditable, and subordinate to safety boundaries.
