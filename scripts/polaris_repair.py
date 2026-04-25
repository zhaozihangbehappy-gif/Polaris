#!/usr/bin/env python3
# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

import argparse
import json
from pathlib import Path


def classify(error_text: str) -> dict:
    text = error_text.lower()

    if "approval" in text or "policy" in text or "sandbox" in text:
        return {
            "failure_type": "approval_denial",
            "repair_class": "nonrepair_stop",
            "confidence": "high",
            "candidate_fixes": [
                "reduce the task to an allowed local action",
                "stop and ask the user to change scope instead of retrying the blocked path",
            ],
            "retry_guidance": "treat this as a non-repair stop, not a repair target",
            "escalate": True,
            "suggested_rule_layer": "hard",
            "recommended_tree": "nonrepair_stop",
            "nonrepair_stop": True,
        }
    if "required env" in text:
        return {
            "failure_type": "missing_dependency",
            "repair_class": "env_probe_tree",
            "confidence": "high",
            "candidate_fixes": [
                "set the required environment variable before retrying",
            ],
            "retry_guidance": "retry after providing the missing environment variable",
            "escalate": False,
            "suggested_rule_layer": "soft",
            "recommended_tree": "dependency_probe_tree",
            "nonrepair_stop": False,
        }
    if "no module named" in text or "module not found" in text or "cannot find module" in text:
        return {
            "failure_type": "missing_dependency",
            "repair_class": "env_probe_tree",
            "confidence": "high",
            "candidate_fixes": [
                "install or enable the missing dependency in the active local environment",
                "switch to an existing local environment that already provides the dependency",
            ],
            "retry_guidance": "retry after confirming the dependency resolves in the current interpreter or PATH",
            "escalate": False,
            "suggested_rule_layer": "soft",
            "recommended_tree": "dependency_probe_tree",
            "nonrepair_stop": False,
        }
    if "command not found" in text or "not recognized as an internal or external command" in text:
        return {
            "failure_type": "missing_tool",
            "repair_class": "tool_probe_tree",
            "confidence": "high",
            "candidate_fixes": [
                "verify the command exists locally and is spelled correctly",
                "use an equivalent local tool already available in the environment",
            ],
            "retry_guidance": "retry after confirming the command resolves from the working directory or PATH",
            "escalate": False,
            "suggested_rule_layer": "soft",
            "recommended_tree": "tool_probe_tree",
            "nonrepair_stop": False,
        }
    if "permission denied" in text or "operation not permitted" in text:
        return {
            "failure_type": "permission_denial",
            "repair_class": "nonrepair_stop",
            "confidence": "medium",
            "candidate_fixes": [
                "move the operation to a writable local location",
                "reduce the action to a local alternative that fits the current environment",
            ],
            "retry_guidance": "do not retry the same blocked action until the scope is reduced or the user changes the request",
            "escalate": True,
            "suggested_rule_layer": "hard",
            "recommended_tree": "nonrepair_stop",
            "nonrepair_stop": True,
        }
    if "importerror" in text or "cannot import name" in text:
        return {
            "failure_type": "import_path_issue",
            "repair_class": "import_probe_tree",
            "confidence": "medium",
            "candidate_fixes": [
                "inspect the active interpreter search path and local package layout",
                "verify the import target exists in the current working tree",
            ],
            "retry_guidance": "retry after confirming the import path and module layout in the active interpreter",
            "escalate": False,
            "suggested_rule_layer": "soft",
            "recommended_tree": "import_probe_tree",
            "nonrepair_stop": False,
        }
    if "jsondecodeerror" in text or "toml" in text or "yaml" in text and "error" in text:
        return {
            "failure_type": "config_parse_error",
            "repair_class": "config_probe_tree",
            "confidence": "medium",
            "candidate_fixes": [
                "inspect nearby config files before editing anything",
                "validate syntax locally with read-only checks where available",
            ],
            "retry_guidance": "retry after isolating the bad local config file and syntax problem",
            "escalate": False,
            "suggested_rule_layer": "soft",
            "recommended_tree": "config_probe_tree",
            "nonrepair_stop": False,
        }
    if "assertionerror" in text or "test failed" in text or "failed:" in text:
        return {
            "failure_type": "test_failure",
            "repair_class": "test_probe_tree",
            "confidence": "medium",
            "candidate_fixes": [
                "inspect the failing test context and recent local changes",
                "collect nearby config and repository evidence before retrying",
            ],
            "retry_guidance": "retry only after narrowing the failure to a local code or fixture issue",
            "escalate": False,
            "suggested_rule_layer": "experimental",
            "recommended_tree": "test_probe_tree",
            "nonrepair_stop": False,
        }
    if "no such file or directory" in text or "cannot find the file" in text:
        return {
            "failure_type": "path_or_missing_file",
            "repair_class": "path_probe_tree",
            "confidence": "high",
            "candidate_fixes": [
                "verify the path relative to the current working directory",
                "create the required file only if the task explicitly calls for it",
            ],
            "retry_guidance": "retry after verifying the target path and the current workdir",
            "escalate": False,
            "suggested_rule_layer": "soft",
            "recommended_tree": "path_probe_tree",
            "nonrepair_stop": False,
        }

    return {
        "failure_type": "unknown",
        "repair_class": "generic_probe_tree",
        "confidence": "low",
        "candidate_fixes": [
            "capture the failing command, stderr, and current step before making changes",
            "prefer the smallest local diagnostic command that can narrow the failure",
        ],
        "retry_guidance": "retry only after collecting clearer local evidence",
        "escalate": False,
        "suggested_rule_layer": "experimental",
        "recommended_tree": "generic_probe_tree",
        "nonrepair_stop": False,
    }


def route_depth(base: dict, requested_depth: str | None, execution_profile: str | None, attempt_count: int, blocked_progress: bool) -> dict:
    if base.get("nonrepair_stop"):
        return {
            "repair_depth": "shallow",
            "depth_reason": "nonrepair_stop",
            "should_deepen": False,
            "next_depth": None,
            "probe_budget": 0,
        }

    if requested_depth == "deep" or execution_profile == "deep":
        depth = "deep"
        reason = "deep_profile"
    elif requested_depth == "medium" or blocked_progress or attempt_count >= 2:
        depth = "medium"
        reason = "repeated_failure" if attempt_count >= 2 else "blocked_progress"
    else:
        depth = "shallow"
        reason = "first_failure"

    next_depth = None
    if depth == "shallow":
        next_depth = "medium"
    elif depth == "medium":
        next_depth = "deep"

    probe_budget = {"shallow": 2, "medium": 4, "deep": 999}[depth]
    return {
        "repair_depth": depth,
        "depth_reason": reason,
        "should_deepen": depth != "deep",
        "next_depth": next_depth,
        "probe_budget": probe_budget,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose a Polaris failure.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    diagnose = subparsers.add_parser("diagnose")
    diagnose.add_argument("--error", required=True)
    diagnose.add_argument("--write-report")
    diagnose.add_argument("--repair-depth", choices=["shallow", "medium", "deep"])
    diagnose.add_argument("--execution-profile", choices=["micro", "standard", "deep"])
    diagnose.add_argument("--attempt-count", type=int, default=1)
    diagnose.add_argument("--blocked-progress", choices=["yes", "no"], default="no")

    args = parser.parse_args()
    report = classify(args.error)
    route = route_depth(
        report,
        args.repair_depth,
        args.execution_profile,
        max(args.attempt_count, 1),
        args.blocked_progress == "yes",
    )
    report.update(route)
    report["evidence"] = [args.error]
    report["references"] = ["Polaris/references/repair-actions.md", "Polaris/references/stop-classifications.md"]
    if args.write_report:
        Path(args.write_report).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
