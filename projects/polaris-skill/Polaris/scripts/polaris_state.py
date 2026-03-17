#!/usr/bin/env python3
import argparse
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


def default_state() -> dict:
    defaults = profile_defaults("deep")
    return {
        "schema_version": 6,
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
                "nonrepair_stop": False,
            },
            "allowed_transitions": ALLOWED_TRANSITIONS,
        },
        "rule_context": {
            "active_layers": ["hard", "soft"],
            "applied_rules": [],
        },
        "fallback_state": {
            "attempted_adapters": [],
            "fallback_count": 0,
            "max_fallback_attempts": 0,
        },
        "compat": {
            "upgraded_from": None,
            "upgraded_at": None,
            "runtime_format": 1,
            "resumed_count": 0,
        },
        "updated_at": now(),
    }


def _backfill_v5_defaults(state: dict) -> None:
    """Fill missing optional fields that may be absent in a v5 state file."""
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
    machine.setdefault("blocked", {"is_blocked": False, "reason": None, "references": [], "nonrepair_stop": False})
    machine["blocked"].setdefault("nonrepair_stop", False)
    machine.setdefault("allowed_transitions", ALLOWED_TRANSITIONS)
    state.setdefault("rule_context", {"active_layers": ["hard", "soft"], "applied_rules": []})
    state.setdefault("fallback_state", {"attempted_adapters": [], "fallback_count": 0, "max_fallback_attempts": 0})


def _migrate_backlog_versions(state: dict) -> None:
    """Tag old backlog items that lack asset_version with version 1."""
    for item in state.get("learning_backlog", []):
        if "asset_version" not in item:
            item["asset_version"] = 1


def _migrate_stringified_artifacts(state: dict) -> None:
    """De-stringify any artifact values that are JSON strings encoding dicts, lists, or bools."""
    artifacts = state.get("artifacts")
    if not artifacts or not isinstance(artifacts, dict):
        return
    for key, value in artifacts.items():
        if not isinstance(value, str):
            continue
        try:
            parsed = json.loads(value)
            if isinstance(parsed, (dict, list, bool, int, float)):
                artifacts[key] = parsed
        except (json.JSONDecodeError, TypeError):
            pass


def load_state(path: Path) -> dict:
    if not path.exists():
        return default_state()
    state = json.loads(path.read_text())
    version = state.get("schema_version")

    if version == 6:
        _backfill_v5_defaults(state)
        _migrate_stringified_artifacts(state)
        _migrate_backlog_versions(state)
        compat = state.setdefault("compat", {"upgraded_from": None, "upgraded_at": None, "runtime_format": 1, "resumed_count": 0})
        compat.setdefault("resumed_count", 0)
        return state

    if version == 5:
        _backfill_v5_defaults(state)
        _migrate_stringified_artifacts(state)
        _migrate_backlog_versions(state)
        state["schema_version"] = 6
        state["compat"] = {"upgraded_from": 5, "upgraded_at": now(), "runtime_format": 1, "resumed_count": 0}
        return state

    # Unknown / incompatible version — refuse, do not silently upgrade
    raise SystemExit(
        f"Incompatible state schema version {version}. "
        f"This Polaris version supports: {sorted({5, 6})}. "
        f"Refusing to load."
    )


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


def write_json(path: Path, payload: dict) -> None:
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
            entry = {
                "index": item.get("index"),
                "phase": item.get("phase"),
                "step": item.get("step"),
                "status": item.get("status"),
            }
            if "requires" in item:
                entry["requires"] = item["requires"]
            if "validates_with" in item:
                entry["validates_with"] = item["validates_with"]
            plan.append(entry)
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
                if key in {"selected_adapter", "selected_pattern", "execution_kind", "baseline_execution_contract", "execution_contract_diff", "baseline_validator", "validator_diff", "execution_contract", "execution_result", "executor_result", "validation_result", "resumed_execution_contract", "resumed_executor_result", "resumed_validation_result", "repair_report", "repair_plan", "repair_results", "learning_summary", "efficiency_metrics", "family_transfer_applied", "transfer_key", "transfer_source_pattern", "transfer_reason", "transfer_contract_diff", "task_fingerprint", "experience_hints", "experience_applied_count", "failure_record_written", "execution_family_trace", "hot_path_budget"}
            },
            "fallback_state": payload.get("fallback_state", {"attempted_adapters": [], "fallback_count": 0, "max_fallback_attempts": 0}),
            "compat": payload.get("compat", {"upgraded_from": None, "upgraded_at": None, "runtime_format": 1}),
            "references": payload.get("references", [])[-2:],
            "updated_at": payload.get("updated_at"),
        }
    path.write_text(json.dumps(persisted, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_history(state: dict, to_node: str, summary: str, branch_id: str | None = None) -> None:
    machine = state.setdefault("state_machine", {})
    history = machine.setdefault("history", [])
    history.append(
        {
            "ts": now(),
            "from": machine.get("node"),
            "to": to_node,
            "summary": summary,
            "branch_id": branch_id,
        }
    )
    machine["node"] = to_node
    state["phase"] = to_node
    runtime = state.setdefault("runtime", {})
    runtime["lifecycle_stage"] = to_node
    runtime["last_heartbeat_at"] = now()
    if to_node != "blocked":
        machine.setdefault("blocked", {})["is_blocked"] = False
        machine["blocked"]["reason"] = None
        machine["blocked"]["references"] = []
    if to_node == "completed":
        machine["active_branch"] = None
        runtime["completed_at"] = now()


def update_plan_step(state: dict, phase: str, status: str) -> None:
    plan = state.get("plan", [])
    target = next((item for item in plan if item.get("phase") == phase and item.get("status") != "completed"), None)
    if not target:
        return
    target["status"] = status
    target["updated_at"] = now()
    if status == "in_progress":
        state["current_step"] = target["step"]
        next_pending = next((item for item in plan if item.get("index", 0) > target.get("index", 0) and item.get("status") == "pending"), None)
        state["next_action"] = next_pending["step"] if next_pending else None
    if status == "completed":
        next_pending = next((item for item in plan if item.get("status") == "pending"), None)
        if next_pending:
            next_pending["status"] = "in_progress"
            next_pending["updated_at"] = now()
            state["current_step"] = next_pending["step"]
            later = next((item for item in plan if item.get("index", 0) > next_pending.get("index", 0) and item.get("status") == "pending"), None)
            state["next_action"] = later["step"] if later else None
        else:
            state["current_step"] = "Completed"
            state["next_action"] = "Review outputs"


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage Polaris execution state.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--state", required=True)
    init_parser.add_argument("--goal", required=True)
    init_parser.add_argument("--run-id", default="polaris-run")
    init_parser.add_argument("--mode", choices=["short", "long"], default="long")
    init_parser.add_argument("--execution-profile", choices=["micro", "standard", "deep"], default="deep")
    init_parser.add_argument("--state-density", choices=["minimal", "full"])
    init_parser.add_argument("--active-layers", default="hard,soft")

    checkpoint_parser = subparsers.add_parser("checkpoint")
    checkpoint_parser.add_argument("--state", required=True)
    checkpoint_parser.add_argument("--value", required=True)
    checkpoint_parser.add_argument("--kind", default="milestone")

    plan_step_parser = subparsers.add_parser("plan-step")
    plan_step_parser.add_argument("--state", required=True)
    plan_step_parser.add_argument("--phase", required=True)
    plan_step_parser.add_argument("--status", choices=["pending", "in_progress", "completed"], required=True)

    set_parser = subparsers.add_parser("set")
    set_parser.add_argument("--state", required=True)
    set_parser.add_argument("--status")
    set_parser.add_argument("--progress-pct", type=int)
    set_parser.add_argument("--current-step")
    set_parser.add_argument("--next-action")
    set_parser.add_argument("--phase")
    set_parser.add_argument("--active-layers")
    set_parser.add_argument("--summary-outcome")
    set_parser.add_argument("--repair-depth", choices=["shallow", "medium", "deep"])
    set_parser.add_argument("--resumed-count", type=int)

    attempt_parser = subparsers.add_parser("attempt")
    attempt_parser.add_argument("--state", required=True)
    attempt_parser.add_argument("--step", required=True)
    attempt_parser.add_argument("--status", required=True)
    attempt_parser.add_argument("--summary", required=True)
    attempt_parser.add_argument("--evidence", default="")
    attempt_parser.add_argument("--branch-id")

    transition_parser = subparsers.add_parser("transition")
    transition_parser.add_argument("--state", required=True)
    transition_parser.add_argument("--to", required=True, choices=sorted(ALLOWED_TRANSITIONS))
    transition_parser.add_argument("--summary", required=True)
    transition_parser.add_argument("--branch-id")

    branch_parser = subparsers.add_parser("branch")
    branch_parser.add_argument("--state", required=True)
    branch_parser.add_argument("--branch-id", required=True)
    branch_parser.add_argument("--label", required=True)
    branch_parser.add_argument("--kind", choices=["primary", "repair", "blocked", "validation"], required=True)
    branch_parser.add_argument("--summary", required=True)
    branch_parser.add_argument("--references", default="")

    recover_parser = subparsers.add_parser("recover")
    recover_parser.add_argument("--state", required=True)
    recover_parser.add_argument("--branch-id", required=True)
    recover_parser.add_argument("--to", required=True, choices=sorted(ALLOWED_TRANSITIONS))
    recover_parser.add_argument("--summary", required=True)
    recover_parser.add_argument("--references", default="")

    block_parser = subparsers.add_parser("block")
    block_parser.add_argument("--state", required=True)
    block_parser.add_argument("--reason", required=True)
    block_parser.add_argument("--references", default="")
    block_parser.add_argument("--nonrepair-stop", choices=["true", "false"], default="false")

    artifact_parser = subparsers.add_parser("artifact")
    artifact_parser.add_argument("--state", required=True)
    artifact_parser.add_argument("--key", required=True)
    artifact_parser.add_argument("--value", required=True)

    apply_rules_parser = subparsers.add_parser("apply-rules")
    apply_rules_parser.add_argument("--state", required=True)
    apply_rules_parser.add_argument("--rules-json", required=True)

    reference_parser = subparsers.add_parser("reference")
    reference_parser.add_argument("--state", required=True)
    reference_parser.add_argument("--kind", required=True)
    reference_parser.add_argument("--value", required=True)
    reference_parser.add_argument("--label", default="")

    success_parser = subparsers.add_parser("success")
    success_parser.add_argument("--state", required=True)
    success_parser.add_argument("--pattern-id", required=True)
    success_parser.add_argument("--summary", required=True)
    success_parser.add_argument("--evidence", required=True)
    success_parser.add_argument("--confidence", type=int, default=60)
    success_parser.add_argument("--reusable", choices=["yes", "no"], default="yes")

    backlog_add_parser = subparsers.add_parser("backlog-add")
    backlog_add_parser.add_argument("--state", required=True)
    backlog_add_parser.add_argument("--kind", choices=["success_marker", "rule_candidate"], required=True)
    backlog_add_parser.add_argument("--payload", required=True)

    backlog_clear_parser = subparsers.add_parser("backlog-clear")
    backlog_clear_parser.add_argument("--state", required=True)

    backlog_replace_parser = subparsers.add_parser("backlog-replace")
    backlog_replace_parser.add_argument("--state", required=True)
    backlog_replace_parser.add_argument("--payload", required=True)

    compact_parser = subparsers.add_parser("compact-history")
    compact_parser.add_argument("--state", required=True)

    heartbeat_parser = subparsers.add_parser("heartbeat")
    heartbeat_parser.add_argument("--state", required=True)
    heartbeat_parser.add_argument("--summary", default="")

    surface_parser = subparsers.add_parser("surface")
    surface_parser.add_argument("--state", required=True)
    surface_parser.add_argument("--kind", required=True)
    surface_parser.add_argument("--value", required=True)

    fallback_record_parser = subparsers.add_parser("fallback-record")
    fallback_record_parser.add_argument("--state", required=True)
    fallback_record_parser.add_argument("--adapter", required=True)
    fallback_record_parser.add_argument("--max-fallback-attempts", type=int, required=True)

    fallback_reset_parser = subparsers.add_parser("fallback-reset")
    fallback_reset_parser.add_argument("--state", required=True)

    args = parser.parse_args()
    state_path = Path(getattr(args, "state"))
    state = load_state(state_path)

    if args.command == "init":
        defaults = profile_defaults(args.execution_profile)
        state = default_state()
        state.update(
            {
                "run_id": args.run_id,
                "goal": args.goal,
                "mode": args.mode,
                "execution_profile": args.execution_profile,
                "state_density": args.state_density or defaults["state_density"],
                "repair_depth": defaults["repair_depth"],
                "event_budget": defaults["event_budget"],
                "status": "in_progress",
                "phase": "intake",
                "current_step": "Initialize run",
                "next_action": "Build plan",
                "rule_context": {
                    "active_layers": parse_csv(args.active_layers) or ["hard", "soft"],
                    "applied_rules": [],
                },
                "runtime": {
                    "lifecycle_stage": "intake",
                    "started_at": now(),
                    "last_heartbeat_at": now(),
                    "completed_at": None,
                    "durable_status_surfaces": {},
                },
            }
        )
    elif args.command == "checkpoint":
        state["checkpoints"].append({"value": args.value, "kind": args.kind, "ts": now()})
    elif args.command == "plan-step":
        update_plan_step(state, args.phase, args.status)
    elif args.command == "set":
        if args.status:
            state["status"] = args.status
        if args.progress_pct is not None:
            state["progress_pct"] = args.progress_pct
        if args.current_step:
            state["current_step"] = args.current_step
        if args.next_action:
            state["next_action"] = args.next_action
        if args.phase:
            state["phase"] = args.phase
        if args.active_layers:
            state["rule_context"]["active_layers"] = parse_csv(args.active_layers)
        if args.summary_outcome:
            state["summary_outcome"] = args.summary_outcome
        if args.repair_depth:
            state["repair_depth"] = args.repair_depth
        if args.resumed_count is not None:
            state.setdefault("compat", {})["resumed_count"] = args.resumed_count
    elif args.command == "attempt":
        state["attempts"].append(
            {
                "ts": now(),
                "step": args.step,
                "status": args.status,
                "summary": args.summary,
                "evidence": parse_csv(args.evidence),
                "branch_id": args.branch_id,
            }
        )
    elif args.command == "transition":
        current = state.get("state_machine", {}).get("node", "intake")
        allowed = ALLOWED_TRANSITIONS.get(current, [])
        if args.to not in allowed:
            raise SystemExit(f"invalid transition: {current} -> {args.to}")
        append_history(state, args.to, args.summary, args.branch_id)
    elif args.command == "branch":
        branch = {
            "branch_id": args.branch_id,
            "label": args.label,
            "kind": args.kind,
            "origin_node": state["state_machine"].get("node"),
            "status": "active",
            "summary": args.summary,
            "references": parse_csv(args.references),
            "opened_at": now(),
        }
        branches = state["state_machine"].setdefault("branches", [])
        branches = [item for item in branches if item.get("branch_id") != args.branch_id or item.get("status") == "recovered"]
        branches.append(branch)
        state["state_machine"]["branches"] = branches
        state["state_machine"]["active_branch"] = args.branch_id
    elif args.command == "recover":
        for branch in state["state_machine"].get("branches", []):
            if branch.get("branch_id") == args.branch_id:
                branch["status"] = "recovered"
                branch["closed_at"] = now()
                branch.setdefault("references", []).extend(parse_csv(args.references))
                break
        state["state_machine"].setdefault("recovery", []).append(
            {
                "ts": now(),
                "branch_id": args.branch_id,
                "to": args.to,
                "summary": args.summary,
                "references": parse_csv(args.references),
            }
        )
        state["state_machine"]["active_branch"] = None
        append_history(state, args.to, args.summary, args.branch_id)
    elif args.command == "block":
        state["state_machine"]["blocked"] = {
            "is_blocked": True,
            "reason": args.reason,
            "references": parse_csv(args.references),
            "nonrepair_stop": args.nonrepair_stop == "true",
        }
        state["summary_outcome"] = args.reason
        append_history(state, "blocked", args.reason, state["state_machine"].get("active_branch"))
    elif args.command == "artifact":
        value = args.value
        try:
            parsed = json.loads(value)
            if isinstance(parsed, (dict, list, bool, int, float)):
                value = parsed
        except (json.JSONDecodeError, TypeError):
            pass
        state.setdefault("artifacts", {})[args.key] = value
    elif args.command == "apply-rules":
        state.setdefault("rule_context", {})["applied_rules"] = json.loads(args.rules_json)
    elif args.command == "reference":
        state.setdefault("references", []).append(
            {"ts": now(), "kind": args.kind, "value": args.value, "label": args.label or None}
        )
    elif args.command == "success":
        state.setdefault("success_patterns", []).append(
            {
                "pattern_id": args.pattern_id,
                "summary": args.summary,
                "evidence": parse_csv(args.evidence),
                "confidence": args.confidence,
                "reusable": args.reusable == "yes",
                "captured_at": now(),
            }
        )
        state["summary_outcome"] = args.summary
    elif args.command == "backlog-add":
        payload = json.loads(args.payload)
        state.setdefault("learning_backlog", []).append(
            {
                "queued_at": now(),
                "kind": args.kind,
                "payload": payload,
                "asset_version": 2,
            }
        )
        runtime = state.setdefault("runtime", {})
        metrics = runtime.setdefault("metrics", {"state_write_count": 0, "learning_hot_path_ops": 0})
        metrics["learning_hot_path_ops"] = int(metrics.get("learning_hot_path_ops", 0)) + 1
    elif args.command == "backlog-clear":
        state["learning_backlog"] = []
    elif args.command == "backlog-replace":
        state["learning_backlog"] = json.loads(args.payload)
    elif args.command == "compact-history":
        compact_history(state)
    elif args.command == "heartbeat":
        state.setdefault("runtime", {})["last_heartbeat_at"] = now()
        if args.summary:
            state.setdefault("runtime", {})["last_heartbeat_summary"] = args.summary
    elif args.command == "surface":
        state.setdefault("runtime", {}).setdefault("durable_status_surfaces", {})[args.kind] = args.value
    elif args.command == "fallback-record":
        fb = state.setdefault("fallback_state", {"attempted_adapters": [], "fallback_count": 0, "max_fallback_attempts": 0})
        if args.adapter not in fb["attempted_adapters"]:
            fb["attempted_adapters"].append(args.adapter)
        fb["fallback_count"] = len(fb["attempted_adapters"])
        # Freeze max_fallback_attempts on first record; never overwrite with a different value
        if int(fb.get("max_fallback_attempts", 0)) == 0:
            fb["max_fallback_attempts"] = args.max_fallback_attempts
    elif args.command == "fallback-reset":
        state["fallback_state"] = {"attempted_adapters": [], "fallback_count": 0, "max_fallback_attempts": 0}

    write_json(state_path, state)
    print(json.dumps(state, sort_keys=True))


if __name__ == "__main__":
    main()
