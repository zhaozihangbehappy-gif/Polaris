#!/usr/bin/env python3
# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_stage(step: str, args: argparse.Namespace, contract: dict, applied_rules: list[dict], selected_pattern: dict) -> dict:
    state_path = Path(args.state)
    output_path = Path(args.output)
    strategy = contract.get("strategy", {})
    if step == "precheck":
        return {"step": step, "status": "ok", "details": {"state_exists": state_path.exists(), "output_parent_exists": output_path.parent.exists(), "fallback_choice": strategy.get("fallback_choice")}}
    if step == "diagnose":
        return {"step": step, "status": "ok", "details": {"goal": args.goal, "adapter": args.adapter, "rule_count": len(applied_rules), "retry_policy": strategy.get("retry_policy"), "max_retry_actions": contract.get("validator", {}).get("max_retry_actions")}}
    if step in {"generic-probes", "record-evidence"}:
        return {"step": step, "status": "ok", "details": {"cwd": str(Path.cwd()), "state_file": args.state, "selected_pattern": selected_pattern.get("pattern_id"), "validation_strategy": strategy.get("validation_strategy")}}
    if step == "recover":
        return {"step": step, "status": "ok", "details": {"recovery_ready": True, "retry_policy": strategy.get("retry_policy"), "max_retry_actions": contract.get("validator", {}).get("max_retry_actions")}}
    if step == "select-adapter":
        return {"step": step, "status": "ok", "details": {"mode": args.mode, "execution_profile": args.execution_profile, "adapter_selection_mode": "reuse-last-good-adapter" if strategy.get("fallback_choice") == "sticky-adapter-first" else "select-current-only", "observed_selection_inputs": contract.get("validator", {}).get("observed_selection_inputs"), "max_selection_inputs": contract.get("validator", {}).get("max_selection_inputs")}}
    if step in {"init", "plan", "execute", "validate"}:
        return {"step": step, "status": "ok", "details": {"mode": args.mode, "execution_profile": args.execution_profile, "validation_strategy": strategy.get("validation_strategy")}}
    return {"step": step, "status": "ok", "details": {"handled": "generic-stage", "retry_policy": strategy.get("retry_policy")}}


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute a concrete Polaris local task contract.")
    parser.add_argument("--goal", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--execution-profile", required=True)
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--applied-rules-json", default="[]")
    parser.add_argument("--selected-pattern-json", default="{}")
    parser.add_argument("--execution-contract-json", default="{}")
    parser.add_argument("--simulate-error")
    args = parser.parse_args()

    applied_rules = json.loads(args.applied_rules_json)
    selected_pattern = json.loads(args.selected_pattern_json) if args.selected_pattern_json else {}
    contract = json.loads(args.execution_contract_json) if args.execution_contract_json else {}

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    strategy = contract.get("strategy", {})
    executed_ordering = strategy.get("execution_ordering", [])
    stage_results = [run_stage(step, args, contract, applied_rules, selected_pattern) for step in executed_ordering]
    payload = {
        "ts": now(),
        "goal": args.goal,
        "state": args.state,
        "mode": args.mode,
        "execution_profile": args.execution_profile,
        "adapter": args.adapter,
        "applied_rule_ids": [rule.get("rule_id") for rule in applied_rules],
        "applied_rule_layers": [rule.get("layer") for rule in applied_rules],
        "selected_pattern": selected_pattern.get("pattern_id"),
        "selected_pattern_sequence": selected_pattern.get("sequence", []),
        "execution_contract": contract,
        "strategy": strategy,
        "executed_ordering": executed_ordering,
        "stage_results": stage_results,
        "status": "ok",
        "notes": [
            "task executed through adapter contract",
            "selected rules and pattern were supplied to the runner",
        ],
    }

    if args.simulate_error:
        payload["status"] = "failed"
        payload["error"] = args.simulate_error
        output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        raise SystemExit(args.simulate_error)

    payload["result"] = {
        "summary": f"Executed local task for goal: {args.goal}",
        "used_pattern_guidance": bool(selected_pattern),
        "used_rule_guidance": bool(applied_rules),
        "stage_count": len(stage_results),
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "output": str(output_path), "adapter": args.adapter}, sort_keys=True))


if __name__ == "__main__":
    main()
