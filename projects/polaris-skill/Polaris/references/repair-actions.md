# Repair Actions

## Purpose

Translate a repairable local failure into a bounded local probe plan.
Preserve explicit stop classifications instead of collapsing every denial into repair.

## Flow

1. `diagnose` decides whether the failure is repairable or a `nonrepair_stop`.
2. `plan` creates a small local action tree only for repairable failures.
3. `execute` runs reversible local leaves and records evidence.

## Routing

- repairable -> continue through `shallow`, `medium`, or `deep`
- `nonrepair_stop` -> no repair execution, no repair learning, no retry-as-bug guidance

## Depth Routing

- `shallow`: first-failure pass for `micro` and `standard`; keep probes very small
- `medium`: use after repeated failure or blocked progress; widen evidence collection carefully
- `deep`: preserve the full repair tree for deep-profile work and re-execute after recovery

## Current Trees

- `dependency_probe_tree`: interpreter, executable, pip, and package visibility probes
- `tool_probe_tree`: PATH and local tool-resolution probes
- `path_probe_tree`: working-directory and nearby-file inspection
- `generic_probe_tree`: minimum evidence collection
- `nonrepair_stop`: explicit stop classification for non-repair denials

## Repair Contract

Automatic repair execution must stay:

- local
- reversible or inspectable
- evidence-producing
- inside the current execution contract

If a repair plan cannot satisfy those conditions, Polaris should stop instead of broadening the task on its own.
