# State And Rules

## Execution State Shape

```json
{
  "schema_version": 5,
  "run_id": "20260313-demo",
  "goal": "Upgrade a local skill deliverable",
  "mode": "long",
  "execution_profile": "deep",
  "state_density": "full",
  "repair_depth": "deep",
  "event_budget": "deep",
  "status": "in_progress",
  "phase": "repairing",
  "current_step": "Run local verification",
  "next_action": "Inspect the verification outputs",
  "summary_outcome": null,
  "attempts": [
    {
      "ts": "2026-03-13T00:00:00Z",
      "step": "Run local verification",
      "status": "failed",
      "summary": "ModuleNotFoundError: No module named pywinauto",
      "evidence": ["ModuleNotFoundError: No module named pywinauto"],
      "branch_id": "execution-main"
    }
  ],
  "references": [
    {
      "ts": "2026-03-13T00:02:00Z",
      "kind": "patterns",
      "value": "runtime-demo/success-patterns.json",
      "label": "success pattern store"
    }
  ],
  "success_patterns": [
    {
      "pattern_id": "missing-dependency-repair-loop",
      "summary": "Repair branch captured a reusable local recovery pattern",
      "evidence": ["runtime-repair-results.json"],
      "confidence": 78,
      "reusable": true,
      "captured_at": "2026-03-13T00:05:00Z"
    }
  ],
  "state_machine": {
    "node": "repairing",
    "active_branch": "repair-local",
    "blocked": {
      "is_blocked": false,
      "reason": null,
      "references": []
    },
    "branches": [
      {
        "branch_id": "execution-main",
        "label": "Primary execution path",
        "kind": "primary",
        "origin_node": "ready",
        "status": "active",
        "summary": "Main local execution branch opened",
        "references": ["adapters.json", "rules.json"],
        "opened_at": "2026-03-13T00:01:00Z"
      }
    ],
    "recovery": [
      {
        "ts": "2026-03-13T00:06:00Z",
        "branch_id": "repair-local",
        "to": "ready",
        "summary": "Repair branch completed and run is ready to continue",
        "references": ["runtime-repair-results.json"]
      }
    ],
    "history": [
      {
        "ts": "2026-03-13T00:01:00Z",
        "from": "ready",
        "to": "executing",
        "summary": "Execution branch started",
        "branch_id": "execution-main"
      }
    ]
  },
  "rule_context": {
    "active_layers": ["hard", "soft"],
    "applied_rules": [
      {
        "rule_id": "stop-on-nonrepair-denial",
        "layer": "hard",
        "action": "Stop and adjust the request or environment instead of retrying the same blocked path",
        "scope": "all Polaris runs",
        "tags": ["stop", "runtime", "local"]
      }
    ]
  },
  "artifacts": {
    "selected_adapter": "python-runtime-local",
    "selected_pattern": "bounded-local-repair",
    "execution_contract": "{...}",
    "execution_result": "runtime-execution-result.json",
    "learning_summary": "{...}"
  }
}
```

## Rule Store Shape

```json
{
  "schema_version": 3,
  "rules": [
    {
      "rule_id": "stop-on-nonrepair-denial",
      "layer": "hard",
      "trigger": "an explicit non-repair denial appears",
      "action": "stop and adjust the task scope or environment instead of retrying the blocked path",
      "evidence": "explicit runtime stop classification during local execution",
      "scope": "all Polaris runs",
      "tags": ["stop", "runtime"],
      "validation": "explicit runtime stop classification",
      "priority": 100,
      "created_at": "2026-03-13T00:00:00Z"
    }
  ]
}
```

## Success Pattern Store Shape

```json
{
  "schema_version": 1,
  "patterns": [
    {
      "pattern_id": "layered-local-orchestration",
      "summary": "Plan, rank adapters, choose a pattern, validate, then promote the result",
      "trigger": "long local task",
      "sequence": ["init", "plan", "select-rules", "rank-adapters", "select-patterns", "execute", "validate"],
      "outcome": "resumable orchestration with reviewable state",
      "evidence": ["execution-state.json"],
      "adapter": "python-local",
      "tags": ["orchestration", "local"],
      "modes": ["long"],
      "confidence": 90,
      "lifecycle_state": "preferred"
    }
  ]
}
```

## Layer Meanings

- `hard`: stop/route rules and invariants
- `soft`: validated practices that should usually be applied
- `experimental`: narrow candidate improvements that still need repeated proof

## Density Meanings

- `minimal`: keep the current step, plan summary, selected adapter, blocked reason, and a short transition tail
- `full`: keep branches, recovery, attempts, references, history summaries, and durable status surfaces

Defaults:
- `micro -> minimal`
- `standard -> minimal`
- `deep -> full`

## Execution Contract Notes

- `artifacts.execution_contract` stores the concrete adapter invocation plan used for the run.
- `artifacts.execution_result` points at the per-run runtime output file that must validate before success is recorded.
- `rule_context.applied_rules` is no longer empty bookkeeping; it is the rule payload forwarded into the execution contract.
- `selected_pattern` is forwarded into the execution contract and can guide validation and follow-up execution choices.

## Promotion Guidance

- Promote `experimental -> soft` rules only after verified local evidence.
- Promote patterns from `experimental -> validated -> preferred` as they prove repeatable.
- Demote, retire, or expire guidance when confidence drops or the environment changes.
