# Adapter Registration

## Purpose

Adapters let Polaris add or swap local tools without rewriting the planner or orchestrator.

## Adapter Record

```json
{
  "tool": "python-local",
  "command": "python3 <script>.py",
  "inputs": ["script_path", "args"],
  "capabilities": ["local-exec", "reporting", "repair-probes"],
  "modes": ["short", "long"],
  "prerequisites": ["python3"],
  "selectors": ["prefer for local JSON tooling", "good default for demos"],
  "failure_notes": ["No module named means the environment is incomplete"],
  "fallbacks": ["shell-local"],
  "fallback_notes": ["use shell-local for generic shell inspection"],
  "mode_preferences": {"long": 4, "short": 2},
  "trust_level": "workspace",
  "cost_hint": 1,
  "latency_hint": 1,
  "safe_retry": true,
  "notes": "General local execution adapter",
  "updated_at": "2026-03-13T00:00:00Z"
}
```

## Ranking Rules

- Require capabilities instead of matching by tool name.
- Filter out adapters that exceed the allowed trust or cost envelope.
- Rank by capability fit, retry safety, selectors, mode preference, trust cost, latency, and fallback coverage.
- Reuse a recent successful adapter directly when the same scenario fingerprint still matches and prerequisites still pass.
- Return ranked candidates plus a selected adapter instead of a bare registry hit.
- Do not register adapters that imply bypassing approvals, policies, or sandbox limits.

## Sticky Reuse

- The fingerprint includes required capabilities, `mode`, `execution_profile`, `failure_type`, trust ceiling, cost ceiling, and durable-status requirement.
- `select --sticky-cache <path>` checks the cache before reranking the full registry.
- Reuse is skipped when the cached adapter is missing, prerequisites now fail, the success is stale, or the same fingerprint has a newer failure than success.
- `record --cache <path> ... --status success|failure` updates the per-fingerprint audit trail with timestamps, failure count, and prerequisite snapshot.

## Typical Capability Tags

- `local-exec`
- `reporting`
- `repair-probes`
- `validation`
- `file-transform`
- `repo-inspection`

## Registration Guidance

1. Keep the command minimal and declarative.
2. List only real local prerequisites.
3. Include evidence-based failure notes and fallback notes.
4. Keep fallback chains explicit and reviewable.
5. Prefer the lowest adequate trust and cost profile.
