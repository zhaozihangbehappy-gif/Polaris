# Safety Boundaries

## Non-Goals

- bypassing safeguards, approvals, prompt restrictions, or sandbox controls
- persistence, replication, self-preservation, or privilege escalation
- covert channels, hidden memory, or opaque long-running autonomy
- unsafe handling of secrets or edits to security-sensitive settings without explicit permitted user intent

## Allowed Repair Scope

- local dependency diagnosis and bounded installation guidance
- path, config, version, or workdir corrections
- safe tool substitution within allowed local capabilities
- reversible local probes that improve diagnosis

## Required Stops

Stop and ask for direction when:

- a failure is actually an approval, policy, or sandbox denial
- a fix requires access outside the allowed workspace
- the task touches secrets, destructive operations, or production systems
- the change cannot be validated locally

## Memory Rules

- keep state, rules, and success patterns in local files only
- store concise facts and outcomes, not hidden reasoning
- attach evidence to reusable guidance
- prune or demote stale experimental guidance
