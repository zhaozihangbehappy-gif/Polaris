#!/usr/bin/env python3
# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

import argparse
import json
from pathlib import Path


PHASE_REQUIRES = {
    "planning": [],
    "ready": ["local-exec"],
    "executing": ["local-exec"],
    "validating": ["local-exec", "reporting"],
    "completed": ["reporting"],
}

PHASE_VALIDATES_WITH = {
    "planning": None,
    "ready": None,
    "executing": "runner_result_contract",
    "validating": "evidence_check",
    "completed": None,
}


def step_id(phase: str, index: int) -> str:
    return f"{phase}-{index}"


def build_steps(goal: str, mode: str, execution_profile: str) -> list[dict]:
    if execution_profile == "micro":
        base = [
            ("planning", "Confirm the bounded local action", "hard", "scope accepted"),
            ("executing", "Run the bounded local action", "hard,soft", "step completed"),
            ("validating", "Verify the local result", "hard,soft", "verification recorded"),
        ]
    elif execution_profile == "standard":
        base = [
            ("planning", "Clarify scope and choose a safe local path", "hard", "scope accepted"),
            ("ready", "Select the primary adapter and fallback", "hard,soft", "execution path chosen"),
            ("executing", "Run the next local step", "hard,soft", "step completed"),
            ("validating", "Verify outcomes and inspect failures", "hard,soft,experimental", "evidence captured"),
            ("completed", "Record reusable next actions", "soft,experimental", "state ready to resume"),
        ]
    else:
        goal_l = goal.lower()
        if "skill" in goal_l or "agent" in goal_l:
            base = [
                ("planning", "Clarify scope and hard constraints", "hard", "scope accepted"),
                ("planning", "Define architecture and module boundaries", "hard,soft", "module map written"),
                ("executing", "Implement scripts, references, and examples", "hard,soft", "files updated"),
                ("validating", "Run local verification and inspect outputs", "hard,soft,experimental", "verification recorded"),
                ("completed", "Capture reusable patterns and next actions", "soft,experimental", "future guidance saved"),
            ]
        else:
            base = [
                ("planning", "Clarify task scope", "hard", "scope accepted"),
                ("ready", "Choose safe local adapter and rules", "hard,soft", "execution path chosen"),
                ("executing", "Execute the next local step", "hard,soft", "step completed"),
                ("validating", "Verify outcomes and inspect failures", "hard,soft,experimental", "evidence captured"),
                ("completed", "Record reusable lessons and next actions", "soft,experimental", "state ready to resume"),
            ]
    if mode == "short":
        base = base[:4]
    plan = []
    for index, (phase, step, layers, success_signal) in enumerate(base, start=1):
        plan.append(
            {
                "index": index,
                "step_id": step_id(phase, index),
                "phase": phase,
                "step": step,
                "status": "pending",
                "rule_layers": layers.split(","),
                "success_signal": success_signal,
                "requires": PHASE_REQUIRES.get(phase, []),
                "validates_with": PHASE_VALIDATES_WITH.get(phase),
            }
        )
    return plan


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or update a Polaris execution plan.")
    parser.add_argument("--state", required=True)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--mode", choices=["short", "long"], default="long")
    parser.add_argument("--execution-profile", choices=["micro", "standard", "deep"], default="deep")
    args = parser.parse_args()

    state_path = Path(args.state)
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    plan = build_steps(args.goal, args.mode, args.execution_profile)
    state["goal"] = args.goal
    state["mode"] = args.mode
    state["execution_profile"] = args.execution_profile
    state["plan"] = plan
    if plan:
        plan[0]["status"] = "in_progress"
    state["current_step"] = plan[0]["step"] if plan else None
    state["next_action"] = plan[1]["step"] if len(plan) > 1 else None
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"goal": args.goal, "mode": args.mode, "execution_profile": args.execution_profile, "plan": plan}, sort_keys=True))


if __name__ == "__main__":
    main()
