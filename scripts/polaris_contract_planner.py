#!/usr/bin/env python3
# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

import argparse
import json


def choose_family(requested_kind: str, adapter: dict, applied_rules: list[dict], selected_pattern: dict | None, simulate_error: str | None, plan_requires: list[str] | None = None) -> tuple[str, dict]:
    if requested_kind != "auto":
        trace = {"reason": "explicit-request", "requested_kind": requested_kind}
        _check_capability_gap(adapter, plan_requires, trace)
        return requested_kind, trace
    if simulate_error:
        trace = {"reason": "simulate-error-forces-runner", "simulate_error": simulate_error}
        _check_capability_gap(adapter, plan_requires, trace)
        return "runner", trace

    capabilities = set(adapter.get("capabilities", []))
    tags = set()
    for rule in applied_rules:
        tags.update(rule.get("tags", []))
    if selected_pattern:
        tags.update(selected_pattern.get("tags", []))

    candidates = []
    if "file-analysis" in capabilities and "file-analysis" in tags:
        candidates.append(("file_analysis", "adapter-capability+file-analysis-tag"))
    if "file-transform" in capabilities and "transform" in tags:
        candidates.append(("file_transform", "adapter-capability+transform-tag"))
    if "command-output" in capabilities and "command-output" in tags:
        candidates.append(("command_output", "adapter-capability+command-output-tag"))
    if "shell-command" in tags or requested_kind == "shell_command":
        candidates.append(("shell_command", "shell-command-explicit"))
    if "generic-runner" in capabilities:
        candidates.append(("runner", "generic-runner-capability"))

    if not candidates:
        trace = {"reason": "fallback-runner", "capabilities": sorted(capabilities), "tags": sorted(tags)}
        _check_capability_gap(adapter, plan_requires, trace)
        return "runner", trace

    family, reason = candidates[0]
    trace = {
        "reason": reason,
        "capabilities": sorted(capabilities),
        "tags": sorted(tags),
        "candidates": [family for family, _ in candidates],
    }
    _check_capability_gap(adapter, plan_requires, trace)
    return family, trace


def _check_capability_gap(adapter: dict, plan_requires: list[str] | None, trace: dict) -> None:
    """If plan_requires is given, check adapter capabilities and add warning if gap found."""
    if not plan_requires:
        return
    adapter_caps = set(adapter.get("capabilities", []))
    missing = sorted(set(plan_requires) - adapter_caps)
    if missing:
        trace["capability_warning"] = f"adapter missing: {missing}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Thin scenario/contract-family planner for Polaris.")
    parser.add_argument("plan-family", nargs="?")
    parser.add_argument("--requested-kind", required=True)
    parser.add_argument("--adapter-json", required=True)
    parser.add_argument("--applied-rules-json", default="[]")
    parser.add_argument("--selected-pattern-json", default="{}")
    parser.add_argument("--simulate-error")
    parser.add_argument("--plan-requires-json")
    args = parser.parse_args()

    adapter = json.loads(args.adapter_json)
    applied_rules = json.loads(args.applied_rules_json)
    selected_pattern = json.loads(args.selected_pattern_json) if args.selected_pattern_json else {}
    plan_requires = json.loads(args.plan_requires_json) if args.plan_requires_json else None
    family, trace = choose_family(args.requested_kind, adapter, applied_rules, selected_pattern or None, args.simulate_error, plan_requires)
    print(json.dumps({"family": family, "trace": trace}, sort_keys=True))


if __name__ == "__main__":
    main()
