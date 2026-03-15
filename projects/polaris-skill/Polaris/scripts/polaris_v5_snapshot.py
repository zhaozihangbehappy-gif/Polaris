#!/usr/bin/env python3
"""Frozen v5 state functions — test fixture extracted from commit 22e5758.

This file is a self-contained snapshot of the v5 polaris_state.py functions
used for cross-version state evidence in Platform-0 Step 5A. It is never
imported by production code and should never be updated after creation.

Source: git show 22e5758:projects/polaris-skill/Polaris/scripts/polaris_state.py
"""
import json
from datetime import datetime, timezone
from pathlib import Path


ALLOWED_TRANSITIONS = {
    "intake": ["planning", "blocked"],
    "planning": ["ready", "executing", "blocked"],
    "ready": ["executing", "blocked"],
    "executing": ["validating", "repairing", "blocked"],
    "repairing": ["ready", "executing", "blocked"],
    "validating": ["completed", "repairing", "blocked"],
    "blocked": ["planning", "ready", "executing", "completed"],
    "completed": [],
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def profile_defaults(profile: str) -> dict:
    defaults = {
        "micro": {"state_density": "minimal", "repair_depth": "shallow", "event_budget": "micro"},
        "standard": {"state_density": "minimal", "repair_depth": "shallow", "event_budget": "standard"},
        "deep": {"state_density": "full", "repair_depth": "deep", "event_budget": "deep"},
    }
    return defaults.get(profile, defaults["deep"]).copy()


def v5_default_state() -> dict:
    defaults = profile_defaults("deep")
    return {
        "schema_version": 5,
        "run_id": None,
        "goal": None,
        "mode": "long",
        "execution_profile": "deep",
        "state_density": defaults["state_density"],
        "repair_depth": defaults["repair_depth"],
        "event_budget": defaults["event_budget"],
        "learning_backlog": [],
        "status": "not_started",
        "progress_pct": 0,
        "phase": "intake",
        "current_step": None,
        "next_action": None,
        "summary_outcome": None,
        "plan": [],
        "checkpoints": [],
        "attempts": [],
        "artifacts": {},
        "lessons": [],
        "success_patterns": [],
        "references": [],
        "runtime": {
            "lifecycle_stage": "initialized",
            "started_at": now(),
            "last_heartbeat_at": now(),
            "completed_at": None,
            "durable_status_surfaces": {},
            "metrics": {
                "state_write_count": 0,
                "learning_hot_path_ops": 0,
            },
        },
        "state_machine": {
            "node": "intake",
            "active_branch": None,
            "history": [],
            "history_summary": [],
            "branches": [],
            "recovery": [],
            "blocked": {
                "is_blocked": False,
                "reason": None,
                "references": [],
            },
            "allowed_transitions": ALLOWED_TRANSITIONS,
        },
        "rule_context": {
            "active_layers": ["hard", "soft"],
            "applied_rules": [],
        },
        "updated_at": now(),
    }


def v5_load_state(path: Path) -> dict:
    if not path.exists():
        return v5_default_state()
    state = json.loads(path.read_text())
    if state.get("schema_version") == 5:
        profile = state.setdefault("execution_profile", "deep")
        defaults = profile_defaults(profile)
        state.setdefault("state_density", defaults["state_density"])
        state.setdefault("repair_depth", defaults["repair_depth"])
        state.setdefault("event_budget", defaults["event_budget"])
        state.setdefault("learning_backlog", [])
        state.setdefault("summary_outcome", None)
        state.setdefault("references", [])
        state.setdefault("plan", [])
        state.setdefault("checkpoints", [])
        state.setdefault("attempts", [])
        state.setdefault("artifacts", {})
        state.setdefault("lessons", [])
        state.setdefault("success_patterns", [])
        runtime = state.setdefault("runtime", {})
        runtime.setdefault("lifecycle_stage", "initialized")
        runtime.setdefault("started_at", now())
        runtime.setdefault("last_heartbeat_at", now())
        runtime.setdefault("completed_at", None)
        runtime.setdefault("durable_status_surfaces", {})
        runtime.setdefault("metrics", {"state_write_count": 0, "learning_hot_path_ops": 0})
        machine = state.setdefault("state_machine", {})
        machine.setdefault("active_branch", None)
        machine.setdefault("branches", [])
        machine.setdefault("history_summary", [])
        machine.setdefault("recovery", [])
        machine.setdefault("blocked", {"is_blocked": False, "reason": None, "references": []})
        machine.setdefault("allowed_transitions", ALLOWED_TRANSITIONS)
        return state
    upgraded = v5_default_state()
    upgraded.update(state)
    upgraded["schema_version"] = 5
    profile = state.get("execution_profile", "deep")
    defaults = profile_defaults(profile)
    upgraded["execution_profile"] = profile
    upgraded["state_density"] = state.get("state_density", defaults["state_density"])
    upgraded["repair_depth"] = state.get("repair_depth", defaults["repair_depth"])
    upgraded["event_budget"] = state.get("event_budget", defaults["event_budget"])
    upgraded["learning_backlog"] = state.get("learning_backlog", [])
    upgraded["summary_outcome"] = state.get("summary_outcome")
    upgraded["references"] = state.get("references", [])
    upgraded["state_machine"]["history"] = state.get("state_machine", {}).get("history", [])
    upgraded["state_machine"]["history_summary"] = state.get("state_machine", {}).get("history_summary", [])
    upgraded.setdefault("runtime", {}).setdefault("metrics", {"state_write_count": 0, "learning_hot_path_ops": 0})
    upgraded["updated_at"] = now()
    return upgraded


def compact_history(payload: dict, keep_last: int = 6) -> None:
    machine = payload.setdefault("state_machine", {})
    history = machine.setdefault("history", [])
    if len(history) <= keep_last:
        return
    compacted = history[:-keep_last]
    recent = history[-keep_last:]
    by_node = {}
    by_branch = {}
    for item in compacted:
        by_node[item.get("to")] = by_node.get(item.get("to"), 0) + 1
        branch = item.get("branch_id") or "none"
        by_branch[branch] = by_branch.get(branch, 0) + 1
    machine.setdefault("history_summary", []).append(
        {
            "compacted_at": now(),
            "from_ts": compacted[0]["ts"],
            "to_ts": compacted[-1]["ts"],
            "entry_count": len(compacted),
            "by_node": by_node,
            "by_branch": by_branch,
            "first_summary": compacted[0]["summary"],
            "last_summary": compacted[-1]["summary"],
        }
    )
    machine["history"] = recent


def v5_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    runtime = payload.setdefault("runtime", {})
    metrics = runtime.setdefault("metrics", {"state_write_count": 0, "learning_hot_path_ops": 0})
    metrics["state_write_count"] = int(metrics.get("state_write_count", 0)) + 1
    compact_history(payload)
    payload["updated_at"] = now()
    persisted = payload
    if payload.get("state_density") == "minimal":
        plan = []
        for item in payload.get("plan", []):
            plan.append(
                {
                    "index": item.get("index"),
                    "phase": item.get("phase"),
                    "step": item.get("step"),
                    "status": item.get("status"),
                }
            )
        persisted = {
            "schema_version": payload.get("schema_version"),
            "run_id": payload.get("run_id"),
            "goal": payload.get("goal"),
            "mode": payload.get("mode"),
            "execution_profile": payload.get("execution_profile"),
            "state_density": payload.get("state_density"),
            "repair_depth": payload.get("repair_depth"),
            "event_budget": payload.get("event_budget"),
            "learning_backlog": payload.get("learning_backlog", [])[-3:],
            "status": payload.get("status"),
            "progress_pct": payload.get("progress_pct"),
            "phase": payload.get("phase"),
            "current_step": payload.get("current_step"),
            "next_action": payload.get("next_action"),
            "summary_outcome": payload.get("summary_outcome"),
            "plan": plan,
            "runtime": {
                "lifecycle_stage": payload.get("runtime", {}).get("lifecycle_stage"),
                "started_at": payload.get("runtime", {}).get("started_at"),
                "last_heartbeat_at": payload.get("runtime", {}).get("last_heartbeat_at"),
                "completed_at": payload.get("runtime", {}).get("completed_at"),
                "durable_status_surfaces": payload.get("runtime", {}).get("durable_status_surfaces", {}),
                "last_heartbeat_summary": payload.get("runtime", {}).get("last_heartbeat_summary"),
                "metrics": payload.get("runtime", {}).get("metrics", {}),
            },
            "state_machine": {
                "node": payload.get("state_machine", {}).get("node"),
                "active_branch": payload.get("state_machine", {}).get("active_branch"),
                "blocked": payload.get("state_machine", {}).get("blocked", {}),
                "history": payload.get("state_machine", {}).get("history", [])[-2:],
                "allowed_transitions": ALLOWED_TRANSITIONS,
            },
            "rule_context": {
                "active_layers": payload.get("rule_context", {}).get("active_layers", []),
                "applied_rules": payload.get("rule_context", {}).get("applied_rules", []),
            },
            "artifacts": {
                key: value
                for key, value in payload.get("artifacts", {}).items()
                if key in {"selected_adapter", "selected_pattern", "execution_kind", "baseline_execution_contract", "execution_contract_diff", "baseline_validator", "validator_diff", "execution_contract", "execution_result", "executor_result", "validation_result", "resumed_execution_contract", "resumed_executor_result", "resumed_validation_result", "repair_report", "repair_plan", "repair_results", "learning_summary", "efficiency_metrics", "family_transfer_applied", "transfer_key", "transfer_source_pattern", "transfer_reason", "transfer_contract_diff"}
            },
            "references": payload.get("references", [])[-2:],
            "updated_at": payload.get("updated_at"),
        }
    path.write_text(json.dumps(persisted, indent=2, sort_keys=True) + "\n", encoding="utf-8")
