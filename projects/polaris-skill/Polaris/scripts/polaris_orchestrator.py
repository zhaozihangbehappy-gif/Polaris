#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from pathlib import Path


PROFILE_POLICIES = {
    "micro": {
        "state_density": "minimal",
        "report_detail": "minimal",
        "surface_detail": "minimal",
        "event_keys": {"start", "complete"},
        "surface_keys": {"complete"},
        "include_last_event": "no",
        "adapter_capabilities": "local-exec,reporting",
        "failure_type": "bounded_local_task",
        "require_durable_status": "no",
        "select_patterns": False,
        "write_references": False,
        "allow_repair": True,
        "repair_depth": "shallow",
    },
    "standard": {
        "state_density": "minimal",
        "report_detail": "minimal",
        "surface_detail": "minimal",
        "event_keys": {"planning", "execution", "validate", "complete"},
        "surface_keys": {"planning", "validate", "complete"},
        "include_last_event": "no",
        "adapter_capabilities": "local-exec,reporting",
        "failure_type": "moderate_local_task",
        "require_durable_status": "no",
        "select_patterns": True,
        "write_references": True,
        "allow_repair": True,
        "repair_depth": "shallow",
    },
    "deep": {
        "state_density": "full",
        "report_detail": "full",
        "surface_detail": "full",
        "event_keys": {"planning", "execution", "repair", "validate", "complete"},
        "surface_keys": {"planning", "execution", "repair", "validate", "complete"},
        "include_last_event": "yes",
        "adapter_capabilities": "local-exec,reporting,durable-status",
        "failure_type": "long_running_local_task",
        "require_durable_status": "yes",
        "select_patterns": True,
        "write_references": True,
        "allow_repair": True,
        "repair_depth": "deep",
    },
}


def run(cmd: list[str]) -> dict:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return {
        "command": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def run_json(cmd: list[str]) -> dict:
    result = run(cmd)
    if result["returncode"] == 0 and result["stdout"]:
        result["parsed"] = json.loads(result["stdout"])
    return result


def infer_profile(goal: str, mode: str, simulate_error: str | None) -> str:
    goal_l = goal.lower()
    if mode == "long" or simulate_error:
        return "deep"
    if any(term in goal_l for term in ["check", "lint", "format", "one-file", "single file", "small", "short", "bounded"]):
        return "micro"
    return "standard"


def emit_progress(
    base: Path,
    policy: dict,
    key: str,
    run_id: str,
    phase: str,
    status: str,
    summary: str,
    progress: int,
    current: str,
    next_action: str,
    state_node: str,
    layers: str,
    selected_adapter: str | None,
    active_branch: str | None,
    blocked_reason: str | None = None,
    state_file: str | None = None,
) -> dict | None:
    if key not in policy["event_keys"]:
        return None
    return run(
        [
            sys.executable,
            str(base / "polaris_report.py"),
            "--run-id",
            run_id,
            "--phase",
            phase,
            "--status",
            status,
            "--summary",
            summary,
            "--progress-pct",
            str(progress),
            "--current-step",
            current,
            "--next-action",
            next_action,
            "--state-node",
            state_node,
            "--active-rule-layers",
            layers,
            "--selected-adapter",
            selected_adapter or "",
            "--active-branch",
            active_branch or "",
            "--blocked-reason",
            blocked_reason or "",
            "--authoritative-state",
            state_file or "",
            "--event-log",
            str(base.parent / "runtime-events.jsonl"),
            "--status-file",
            str(base.parent / "runtime-status.json"),
            "--detail",
            policy["report_detail"],
        ]
    )


def emit_runtime_surface(base: Path, policy: dict, key: str, state_file: str, kind: str) -> dict | None:
    if key not in policy["surface_keys"]:
        return None
    return run(
        [
            sys.executable,
            str(base / "polaris_runtime.py"),
            "surface",
            "--state",
            state_file,
            "--status-file",
            str(base.parent / "runtime-live-status.json"),
            "--event-log",
            str(base.parent / "runtime-events.jsonl"),
            "--surface-kind",
            kind,
            "--detail",
            policy["surface_detail"],
            "--include-last-event",
            policy["include_last_event"],
        ]
    )


def append(history: list[dict], item: dict | None) -> None:
    if item is not None:
        history.append(item)


def record_adapter_outcome(base: Path, cache_file: str, policy: dict, execution_profile: str, adapter_name: str | None, status: str, score: int | None) -> dict | None:
    if not adapter_name:
        return None
    return run(
        [
            sys.executable,
            str(base / "polaris_adapters.py"),
            "record",
            "--cache",
            cache_file,
            "--registry",
            policy["adapter_registry"],
            "--capabilities",
            policy["adapter_capabilities"],
            "--mode",
            policy["mode"],
            "--execution-profile",
            execution_profile,
            "--max-trust",
            "workspace",
            "--max-cost",
            "5",
            "--failure-type",
            policy["failure_type"],
            "--require-durable-status",
            policy["require_durable_status"],
            "--adapter",
            adapter_name,
            "--status",
            status,
            *(["--score", str(score)] if score is not None else []),
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Polaris local orchestration flow.")
    parser.add_argument("--state", required=True)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--simulate-error")
    parser.add_argument("--adapters", required=True)
    parser.add_argument("--rules", required=True)
    parser.add_argument("--patterns", required=True)
    parser.add_argument("--mode", choices=["short", "long"], default="long")
    parser.add_argument("--execution-profile", choices=["auto", "micro", "standard", "deep"], default="auto")
    parser.add_argument("--state-density", choices=["auto", "minimal", "full"], default="auto")
    args = parser.parse_args()

    base = Path(__file__).resolve().parent
    run_id = "polaris-orchestrated-run"
    layers = "hard,soft,experimental"
    history = []
    execution_branch = "execution-main"
    repair_branch = "repair-local"
    execution_profile = infer_profile(args.goal, args.mode, args.simulate_error) if args.execution_profile == "auto" else args.execution_profile
    policy = PROFILE_POLICIES[execution_profile]
    policy = {**policy, "mode": args.mode, "adapter_registry": args.adapters}
    state_density = policy["state_density"] if args.state_density == "auto" else args.state_density
    sticky_cache = str(Path(args.adapters).with_name("adapter-selection-cache.json"))

    history.append(
        run(
            [
                sys.executable,
                str(base / "polaris_state.py"),
                "init",
                "--state",
                args.state,
                "--goal",
                args.goal,
                "--run-id",
                run_id,
                "--mode",
                args.mode,
                "--execution-profile",
                execution_profile,
                "--state-density",
                state_density,
                "--active-layers",
                layers,
            ]
        )
    )
    if policy["write_references"]:
        history.append(run([sys.executable, str(base / "polaris_state.py"), "reference", "--state", args.state, "--kind", "rules", "--value", args.rules, "--label", "layered rules store"]))
        history.append(run([sys.executable, str(base / "polaris_state.py"), "reference", "--state", args.state, "--kind", "patterns", "--value", args.patterns, "--label", "success pattern store"]))
        history.append(run([sys.executable, str(base / "polaris_state.py"), "reference", "--state", args.state, "--kind", "adapters", "--value", args.adapters, "--label", "adapter registry"]))
    history.append(run([sys.executable, str(base / "polaris_state.py"), "transition", "--state", args.state, "--to", "planning", "--summary", f"Run initialized and routed to the {execution_profile} profile"]))
    history.append(
        run(
            [
                sys.executable,
                str(base / "polaris_planner.py"),
                "--state",
                args.state,
                "--goal",
                args.goal,
                "--mode",
                args.mode,
                "--execution-profile",
                execution_profile,
            ]
        )
    )

    selected_rules = run_json(
        [
            sys.executable,
            str(base / "polaris_rules.py"),
            "select",
            "--rules",
            args.rules,
            "--tags",
            "orchestration,local",
            "--layers",
            layers,
        ]
    )
    selected_adapter = run_json(
        [
            sys.executable,
            str(base / "polaris_adapters.py"),
            "select",
            "--registry",
            args.adapters,
            "--capabilities",
            policy["adapter_capabilities"],
            "--mode",
            args.mode,
            "--execution-profile",
            execution_profile,
            "--max-trust",
            "workspace",
            "--max-cost",
            "5",
            "--failure-type",
            policy["failure_type"],
            "--require-durable-status",
            policy["require_durable_status"],
            "--verify-prereqs",
            "yes",
            "--sticky-cache",
            sticky_cache,
        ]
    )
    adapter_name = None
    adapter_score = None
    adapter_attempt_count = 1
    adapter_selection = selected_adapter.get("parsed", {}).get("selected", [])
    if adapter_selection:
        adapter_name = adapter_selection[0]["adapter"]["tool"]
        adapter_score = adapter_selection[0].get("score")
    sticky_entry = selected_adapter.get("parsed", {}).get("selection_trace", {}).get("sticky_reuse", {}).get("entry", {})
    if sticky_entry:
        adapter_attempt_count = int(sticky_entry.get("failure_count", 0)) + 1

    selected_patterns = {"selected": [], "selection_trace": {"skipped": True}}
    pattern_name = None
    if policy["select_patterns"]:
        selected_patterns = run_json(
            [
                sys.executable,
                str(base / "polaris_success_patterns.py"),
                "select",
                "--patterns",
                args.patterns,
                "--tags",
                "orchestration,local",
                "--mode",
                args.mode,
                "--adapter",
                adapter_name or "",
                "--min-confidence",
                "50",
            ]
        )
        top_pattern = selected_patterns.get("parsed", {}).get("selected", [])
        pattern_name = top_pattern[0]["pattern"]["pattern_id"] if top_pattern else None

    history.append(run([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "selected_adapter", "--value", adapter_name or "none"]))
    if pattern_name:
        history.append(run([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "selected_pattern", "--value", pattern_name]))
    append(
        history,
        emit_progress(
            base,
            policy,
            "planning" if execution_profile != "micro" else "start",
            run_id,
            "planning",
            "in_progress",
            f"{execution_profile.title()} profile prepared adapter routing and state budget",
            15,
            "Plan task",
            "Prepare execution path",
            "planning",
            layers,
            adapter_name,
            execution_branch,
            None,
            args.state,
        ),
    )
    history.append(run([sys.executable, str(base / "polaris_state.py"), "heartbeat", "--state", args.state, "--summary", "planning surfaces updated"]))
    if policy["surface_keys"]:
        history.append(run([sys.executable, str(base / "polaris_state.py"), "surface", "--state", args.state, "--kind", "live_status", "--value", str(base.parent / "runtime-live-status.json")]))
    append(history, emit_runtime_surface(base, policy, "planning", args.state, "planning"))
    history.append(run([sys.executable, str(base / "polaris_state.py"), "plan-step", "--state", args.state, "--phase", "planning", "--status", "completed"]))

    if execution_profile == "micro":
        history.append(run([sys.executable, str(base / "polaris_state.py"), "branch", "--state", args.state, "--branch-id", execution_branch, "--label", "Primary execution path", "--kind", "primary", "--summary", "Bounded local execution branch opened", "--references", args.adapters]))
        history.append(run([sys.executable, str(base / "polaris_state.py"), "transition", "--state", args.state, "--to", "executing", "--summary", "Micro profile moved directly into execution", "--branch-id", execution_branch]))
    else:
        history.append(run([sys.executable, str(base / "polaris_state.py"), "transition", "--state", args.state, "--to", "ready", "--summary", "Plan and adapter routing completed"]))
        history.append(run([sys.executable, str(base / "polaris_state.py"), "plan-step", "--state", args.state, "--phase", "ready", "--status", "in_progress"]))
        history.append(run([sys.executable, str(base / "polaris_state.py"), "branch", "--state", args.state, "--branch-id", execution_branch, "--label", "Primary execution path", "--kind", "primary", "--summary", "Main local execution branch opened", "--references", args.adapters + "," + args.rules]))
        history.append(run([sys.executable, str(base / "polaris_state.py"), "plan-step", "--state", args.state, "--phase", "ready", "--status", "completed"]))
        history.append(run([sys.executable, str(base / "polaris_state.py"), "transition", "--state", args.state, "--to", "executing", "--summary", "Execution branch started", "--branch-id", execution_branch]))

    history.append(run([sys.executable, str(base / "polaris_state.py"), "plan-step", "--state", args.state, "--phase", "executing", "--status", "in_progress"]))
    append(
        history,
        emit_progress(
            base,
            policy,
            "execution",
            run_id,
            "execution",
            "in_progress",
            f"{execution_profile.title()} execution is using the selected local adapter under the current budget",
            40,
            "Prepare execution",
            "Run local task step",
            "executing",
            layers,
            adapter_name,
            execution_branch,
            None,
            args.state,
        ),
    )
    history.append(run([sys.executable, str(base / "polaris_state.py"), "heartbeat", "--state", args.state, "--summary", "execution surfaces updated"]))
    append(history, emit_runtime_surface(base, policy, "execution", args.state, "execution"))

    if args.simulate_error:
        history.append(run([sys.executable, str(base / "polaris_state.py"), "attempt", "--state", args.state, "--step", "simulated_failure", "--status", "failed", "--summary", args.simulate_error, "--evidence", args.simulate_error, "--branch-id", execution_branch]))
        repair_report = run_json(
            [
                sys.executable,
                str(base / "polaris_repair.py"),
                "diagnose",
                "--error",
                args.simulate_error,
                "--write-report",
                str(base.parent / "runtime-repair-report.json"),
                "--repair-depth",
                policy["repair_depth"],
                "--execution-profile",
                execution_profile,
                "--attempt-count",
                str(adapter_attempt_count),
            ]
        )
        resolved_repair_depth = repair_report.get("parsed", {}).get("repair_depth", policy["repair_depth"])
        history.append(run([sys.executable, str(base / "polaris_state.py"), "set", "--state", args.state, "--repair-depth", resolved_repair_depth]))
        repair_plan = run_json(
            [
                sys.executable,
                str(base / "polaris_repair_actions.py"),
                "plan",
                "--error",
                args.simulate_error,
                "--repair-depth",
                resolved_repair_depth,
                "--write-plan",
                str(base.parent / "runtime-repair-plan.json"),
            ]
        )
        repair_results = run_json([sys.executable, str(base / "polaris_repair_actions.py"), "execute", "--plan", str(base.parent / "runtime-repair-plan.json"), "--write-results", str(base.parent / "runtime-repair-results.json")])
        history.extend([repair_report, repair_plan, repair_results])
        history.append(run([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "repair_report", "--value", "runtime-repair-report.json"]))
        history.append(run([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "repair_plan", "--value", "runtime-repair-plan.json"]))
        history.append(run([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "repair_results", "--value", "runtime-repair-results.json"]))

        if execution_profile != "deep":
            history.append(run([sys.executable, str(base / "polaris_state.py"), "transition", "--state", args.state, "--to", "repairing", "--summary", f"{execution_profile.title()} profile opened a {resolved_repair_depth} repair pass", "--branch-id", execution_branch]))
            append(
                history,
                emit_progress(
                    base,
                    policy,
                    "complete",
                    run_id,
                    "repair",
                    "blocked",
                    f"{execution_profile.title()} profile ran a {resolved_repair_depth} repair pass and deferred deeper recovery",
                    60,
                    "Repairing",
                    "Escalate only if the failure repeats",
                    "repairing",
                    layers,
                    adapter_name,
                    execution_branch,
                    args.simulate_error,
                    args.state,
                ),
            )
            history.append(run([sys.executable, str(base / "polaris_state.py"), "block", "--state", args.state, "--reason", f"{execution_profile.title()} profile stopped after {resolved_repair_depth} repair; escalate to {repair_report.get('parsed', {}).get('next_depth') or 'deep'} only if failure repeats", "--references", "runtime-repair-report.json,runtime-repair-plan.json,runtime-repair-results.json"]))
            history.append(run([sys.executable, str(base / "polaris_state.py"), "set", "--state", args.state, "--status", "blocked", "--progress-pct", "60", "--current-step", "Blocked after bounded repair", "--next-action", f"Retry or escalate to {repair_report.get('parsed', {}).get('next_depth') or 'deep'} if the same failure repeats", "--phase", "blocked", "--summary-outcome", args.simulate_error]))
            append(history, record_adapter_outcome(base, sticky_cache, policy, execution_profile, adapter_name, "failure", adapter_score))
            append(history, emit_runtime_surface(base, policy, "complete", args.state, "blocked"))
            print(
                json.dumps(
                    {
                        "status": "blocked",
                        "execution_profile": execution_profile,
                        "selected_rules": selected_rules.get("parsed", {}),
                        "selected_adapter": selected_adapter.get("parsed", {}),
                        "selected_patterns": selected_patterns.get("parsed", selected_patterns),
                        "history": history,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return

        history.append(run([sys.executable, str(base / "polaris_state.py"), "branch", "--state", args.state, "--branch-id", repair_branch, "--label", "Local repair branch", "--kind", "repair", "--summary", "Execution failure triggered repair branch", "--references", "runtime-repair-report.json,runtime-repair-plan.json,runtime-repair-results.json"]))
        history.append(run([sys.executable, str(base / "polaris_state.py"), "transition", "--state", args.state, "--to", "repairing", "--summary", "Execution failure triggered repair branch", "--branch-id", repair_branch]))
        append(
            history,
            emit_progress(
                base,
                policy,
                "repair",
                run_id,
                "repair",
                "in_progress",
                "Failure classified and routed through the deep local repair tree",
                60,
                "Diagnose failure",
                "Record validated fix strategy",
                "repairing",
                layers,
                adapter_name,
                repair_branch,
                None,
                args.state,
            ),
        )
        history.append(run([sys.executable, str(base / "polaris_state.py"), "heartbeat", "--state", args.state, "--summary", "repair surfaces updated"]))
        append(history, emit_runtime_surface(base, policy, "repair", args.state, "repair"))
        history.append(run([sys.executable, str(base / "polaris_rules.py"), "add", "--rules", args.rules, "--rule-id", "repair-known-missing-dependency", "--layer", "experimental", "--trigger", "ModuleNotFoundError", "--action", "Check interpreter, pip, and local environment before retrying", "--evidence", "runtime-repair-results.json,runtime-repair-plan.json,runtime-repair-report.json", "--scope", "local-python-env", "--tags", "repair,python,local", "--validation", "repair action tree probes completed locally", "--priority", "70"]))
        history.append(run([sys.executable, str(base / "polaris_rules.py"), "promote-auto", "--rules", args.rules, "--rule-id", "repair-known-missing-dependency"]))
        history.append(run([sys.executable, str(base / "polaris_success_patterns.py"), "capture", "--patterns", args.patterns, "--pattern-id", "missing-dependency-repair-loop", "--summary", "Dependency failures improve when diagnosis is followed by a bounded local environment probe tree", "--trigger", "ModuleNotFoundError", "--sequence", "diagnose,plan-repair-tree,run-probes,record-rule,recover", "--outcome", "repair path documented without crossing safeguards", "--evidence", "runtime-repair-results.json,runtime-repair-plan.json,runtime-repair-report.json", "--adapter", adapter_name or "", "--tags", "repair,python,orchestration", "--modes", "long", "--confidence", "78", "--lifecycle-state", "experimental"]))
        history.append(run([sys.executable, str(base / "polaris_success_patterns.py"), "promote-auto", "--patterns", args.patterns, "--pattern-id", "missing-dependency-repair-loop"]))
        history.append(run([sys.executable, str(base / "polaris_state.py"), "success", "--state", args.state, "--pattern-id", "missing-dependency-repair-loop", "--summary", "Repair branch captured a reusable local recovery pattern", "--evidence", "runtime-repair-results.json,runtime-repair-plan.json", "--confidence", "78"]))
        history.append(run([sys.executable, str(base / "polaris_state.py"), "recover", "--state", args.state, "--branch-id", repair_branch, "--to", "ready", "--summary", "Repair branch completed and run is ready to continue", "--references", "runtime-repair-results.json,runtime-repair-report.json"]))
        history.append(run([sys.executable, str(base / "polaris_state.py"), "attempt", "--state", args.state, "--step", "repair_guidance_recorded", "--status", "passed", "--summary", "Repair guidance captured and rule stored", "--evidence", "runtime-repair-results.json", "--branch-id", repair_branch]))
        history.append(run([sys.executable, str(base / "polaris_state.py"), "branch", "--state", args.state, "--branch-id", execution_branch, "--label", "Primary execution path", "--kind", "primary", "--summary", "Execution resumed after repair branch", "--references", args.state]))
        history.append(run([sys.executable, str(base / "polaris_state.py"), "transition", "--state", args.state, "--to", "executing", "--summary", "Execution resumed after repair branch", "--branch-id", execution_branch]))
        append(history, record_adapter_outcome(base, sticky_cache, policy, execution_profile, adapter_name, "failure", adapter_score))

    history.append(run([sys.executable, str(base / "polaris_state.py"), "plan-step", "--state", args.state, "--phase", "executing", "--status", "completed"]))
    history.append(run([sys.executable, str(base / "polaris_state.py"), "transition", "--state", args.state, "--to", "validating", "--summary", "Execution outputs ready for validation", "--branch-id", execution_branch]))
    history.append(run([sys.executable, str(base / "polaris_state.py"), "plan-step", "--state", args.state, "--phase", "validating", "--status", "in_progress"]))
    append(
        history,
        emit_progress(
            base,
            policy,
            "validate",
            run_id,
            "validate",
            "in_progress",
            "Validating outputs and finalizing state",
            85,
            "Write final state",
            "Mark run completed",
            "validating",
            layers,
            adapter_name,
            execution_branch,
            None,
            args.state,
        ),
    )
    history.append(run([sys.executable, str(base / "polaris_state.py"), "heartbeat", "--state", args.state, "--summary", "validation surfaces updated"]))
    append(history, emit_runtime_surface(base, policy, "validate", args.state, "validating"))
    if execution_profile == "deep":
        history.append(run([sys.executable, str(base / "polaris_success_patterns.py"), "capture", "--patterns", args.patterns, "--pattern-id", "layered-local-orchestration", "--summary", "Layered rules plus ranked adapter selection keep runs local, resumable, and auditable", "--trigger", "long local task", "--sequence", "init,plan,select-rules,rank-adapters,select-patterns,execute,validate", "--outcome", "resumable orchestration with reviewable state and references", "--evidence", args.state + ",runtime-status.json,Polaris/runtime-events.jsonl", "--adapter", adapter_name or "", "--tags", "orchestration,local,success", "--modes", "long", "--confidence", "88", "--lifecycle-state", "experimental"]))
        history.append(run([sys.executable, str(base / "polaris_success_patterns.py"), "promote-auto", "--patterns", args.patterns, "--pattern-id", "layered-local-orchestration"]))
        history.append(run([sys.executable, str(base / "polaris_state.py"), "success", "--state", args.state, "--pattern-id", "layered-local-orchestration", "--summary", "Full run captured a reusable orchestration pattern", "--evidence", args.state + ",runtime-status.json", "--confidence", "90"]))
    else:
        history.append(run([sys.executable, str(base / "polaris_state.py"), "set", "--state", args.state, "--summary-outcome", f"{execution_profile.title()} run validated locally without deep learning capture"]))
    history.append(run([sys.executable, str(base / "polaris_state.py"), "plan-step", "--state", args.state, "--phase", "validating", "--status", "completed"]))
    if execution_profile != "micro":
        history.append(run([sys.executable, str(base / "polaris_state.py"), "plan-step", "--state", args.state, "--phase", "completed", "--status", "in_progress"]))
    history.append(run([sys.executable, str(base / "polaris_state.py"), "set", "--state", args.state, "--status", "completed", "--progress-pct", "100", "--current-step", "Completed", "--next-action", "Review outputs", "--phase", "completed", "--active-layers", layers, "--summary-outcome", "Run finished cleanly"]))
    append(history, record_adapter_outcome(base, sticky_cache, policy, execution_profile, adapter_name, "success", adapter_score))
    if execution_profile != "micro":
        history.append(run([sys.executable, str(base / "polaris_state.py"), "plan-step", "--state", args.state, "--phase", "completed", "--status", "completed"]))
    history.append(run([sys.executable, str(base / "polaris_state.py"), "transition", "--state", args.state, "--to", "completed", "--summary", "Run finished cleanly", "--branch-id", execution_branch]))
    if execution_profile == "deep":
        history.append(run([sys.executable, str(base / "polaris_state.py"), "compact-history", "--state", args.state]))
    history.append(run([sys.executable, str(base / "polaris_state.py"), "heartbeat", "--state", args.state, "--summary", "run completed"]))
    append(history, emit_runtime_surface(base, policy, "complete", args.state, "completed"))
    append(
        history,
        emit_progress(
            base,
            policy,
            "complete",
            run_id,
            "complete",
            "completed",
            "Polaris orchestration demo completed",
            100,
            "Completed",
            "Inspect outputs",
            "completed",
            layers,
            adapter_name,
            execution_branch,
            None,
            args.state,
        ),
    )

    print(
        json.dumps(
            {
                "status": "pass",
                "execution_profile": execution_profile,
                "selected_rules": selected_rules.get("parsed", {}),
                "selected_adapter": selected_adapter.get("parsed", {}),
                "selected_patterns": selected_patterns.get("parsed", selected_patterns),
                "history": history,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
