#!/usr/bin/env python3
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def parse_csv(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Emit a Polaris progress event.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--progress-pct", type=int)
    parser.add_argument("--current-step")
    parser.add_argument("--next-action")
    parser.add_argument("--state-node")
    parser.add_argument("--active-rule-layers")
    parser.add_argument("--selected-adapter")
    parser.add_argument("--active-branch")
    parser.add_argument("--blocked-reason")
    parser.add_argument("--authoritative-state")
    parser.add_argument("--event-log")
    parser.add_argument("--status-file")
    parser.add_argument("--detail", choices=["minimal", "full"], default="full")
    args = parser.parse_args()

    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "run_id": args.run_id,
        "phase": args.phase,
        "status": args.status,
        "summary": args.summary,
        "progress_pct": args.progress_pct,
        "current_step": args.current_step,
        "next_action": args.next_action,
        "state_node": args.state_node,
        "active_rule_layers": parse_csv(args.active_rule_layers),
        "selected_adapter": args.selected_adapter,
        "active_branch": args.active_branch,
        "blocked_reason": args.blocked_reason,
    }

    if args.authoritative_state:
        state = json.loads(Path(args.authoritative_state).read_text(encoding="utf-8"))
        runtime = state.get("runtime", {})
        summary = {
            "status": state.get("status", event["status"]),
            "phase": state.get("phase", event["phase"]),
            "progress_pct": state.get("progress_pct", event["progress_pct"]),
            "current_step": state.get("current_step", event["current_step"]),
            "next_action": state.get("next_action", event["next_action"]),
            "state_node": state.get("state_machine", {}).get("node", event["state_node"]),
            "selected_adapter": state.get("artifacts", {}).get("selected_adapter", event["selected_adapter"]),
            "active_branch": state.get("state_machine", {}).get("active_branch"),
            "blocked_reason": state.get("state_machine", {}).get("blocked", {}).get("reason"),
            "lifecycle_stage": runtime.get("lifecycle_stage"),
            "started_at": runtime.get("started_at"),
            "last_heartbeat_at": runtime.get("last_heartbeat_at"),
            "completed_at": runtime.get("completed_at"),
            "execution_profile": state.get("execution_profile"),
            "state_density": state.get("state_density"),
            "event_budget": state.get("event_budget"),
        }
        event.update(summary)
        if args.detail == "full":
            event.update(
                {
                    "active_rule_layers": state.get("rule_context", {}).get("active_layers", event["active_rule_layers"]),
                    "selected_pattern": state.get("artifacts", {}).get("selected_pattern"),
                    "summary_outcome": state.get("summary_outcome"),
                    "references": state.get("references", []),
                }
            )

    if args.event_log:
        path = Path(args.event_log)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")

    if args.status_file:
        Path(args.status_file).write_text(json.dumps(event, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(event, sort_keys=True))


if __name__ == "__main__":
    main()
