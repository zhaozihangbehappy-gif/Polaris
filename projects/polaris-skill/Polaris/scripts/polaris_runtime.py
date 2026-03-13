#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def latest_event(path: Path | None) -> dict | None:
    if not path or not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    if not lines:
        return None
    return json.loads(lines[-1])


def main() -> None:
    parser = argparse.ArgumentParser(description="Write durable Polaris runtime status surfaces.")
    sub = parser.add_subparsers(dest="command", required=True)

    surface = sub.add_parser("surface")
    surface.add_argument("--state", required=True)
    surface.add_argument("--status-file", required=True)
    surface.add_argument("--event-log")
    surface.add_argument("--surface-kind", default="snapshot")
    surface.add_argument("--detail", choices=["minimal", "full"], default="full")
    surface.add_argument("--include-last-event", choices=["yes", "no"], default="yes")

    args = parser.parse_args()
    state_path = Path(args.state)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    last_event = latest_event(Path(args.event_log)) if args.event_log else None
    runtime = state.get("runtime", {})
    payload = {
        "run_id": state.get("run_id"),
        "goal": state.get("goal"),
        "mode": state.get("mode"),
        "execution_profile": state.get("execution_profile"),
        "state_density": state.get("state_density"),
        "event_budget": state.get("event_budget"),
        "status": state.get("status"),
        "phase": state.get("phase"),
        "progress_pct": state.get("progress_pct"),
        "current_step": state.get("current_step"),
        "next_action": state.get("next_action"),
        "state_node": state.get("state_machine", {}).get("node"),
        "active_branch": state.get("state_machine", {}).get("active_branch"),
        "blocked_reason": state.get("state_machine", {}).get("blocked", {}).get("reason"),
        "selected_adapter": state.get("artifacts", {}).get("selected_adapter"),
        "selected_pattern": state.get("artifacts", {}).get("selected_pattern"),
        "lifecycle_stage": runtime.get("lifecycle_stage"),
        "started_at": runtime.get("started_at"),
        "last_heartbeat_at": runtime.get("last_heartbeat_at"),
        "completed_at": runtime.get("completed_at"),
        "surface_kind": args.surface_kind,
        "state_path": str(state_path),
        "event_log": args.event_log,
        "updated_at": state.get("updated_at"),
    }
    if args.include_last_event == "yes":
        payload["last_event"] = last_event
    if args.detail == "full":
        payload["selected_pattern"] = state.get("artifacts", {}).get("selected_pattern")
        payload["durable_status_surfaces"] = runtime.get("durable_status_surfaces", {})
        payload["history_summary"] = state.get("state_machine", {}).get("history_summary", [])
        payload["summary_outcome"] = state.get("summary_outcome")
    Path(args.status_file).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
