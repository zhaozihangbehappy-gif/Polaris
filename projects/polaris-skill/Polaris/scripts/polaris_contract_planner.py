#!/usr/bin/env python3
import argparse
import json


def choose_family(requested_kind: str, adapter: dict, applied_rules: list[dict], selected_pattern: dict | None, simulate_error: str | None) -> tuple[str, dict]:
    if requested_kind != "auto":
        return requested_kind, {"reason": "explicit-request", "requested_kind": requested_kind}
    if simulate_error:
        return "runner", {"reason": "simulate-error-forces-runner", "simulate_error": simulate_error}

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
    if "generic-runner" in capabilities:
        candidates.append(("runner", "generic-runner-capability"))

    if not candidates:
        return "runner", {"reason": "fallback-runner", "capabilities": sorted(capabilities), "tags": sorted(tags)}

    family, reason = candidates[0]
    return family, {
        "reason": reason,
        "capabilities": sorted(capabilities),
        "tags": sorted(tags),
        "candidates": [family for family, _ in candidates],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Thin scenario/contract-family planner for Polaris.")
    parser.add_argument("plan-family", nargs="?")
    parser.add_argument("--requested-kind", required=True)
    parser.add_argument("--adapter-json", required=True)
    parser.add_argument("--applied-rules-json", default="[]")
    parser.add_argument("--selected-pattern-json", default="{}")
    parser.add_argument("--simulate-error")
    args = parser.parse_args()

    adapter = json.loads(args.adapter_json)
    applied_rules = json.loads(args.applied_rules_json)
    selected_pattern = json.loads(args.selected_pattern_json) if args.selected_pattern_json else {}
    family, trace = choose_family(args.requested_kind, adapter, applied_rules, selected_pattern or None, args.simulate_error)
    print(json.dumps({"family": family, "trace": trace}, sort_keys=True))


if __name__ == "__main__":
    main()
