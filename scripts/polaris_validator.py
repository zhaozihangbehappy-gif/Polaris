#!/usr/bin/env python3
# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

import argparse
import hashlib
import json
from pathlib import Path


PROFILE_SELECTION_BUDGETS = {
    "micro": 1,
    "standard": 4,
    "deep": 8,
}


def retry_budget_for(policy: str | None) -> int:
    if policy == "respect-hard-stop-rules":
        return 0
    if policy in {"bounded-repair", "bounded-repair-with-learning", "bounded-repair-with-evidence"}:
        return 1
    return 1


def validate_json_status_file(contract: dict, execution_result: dict) -> dict:
    validator = contract.get("validator", {})
    output_file = validator.get("output_file") or execution_result.get("output_file")
    if not output_file:
        return {"status": "failed", "reason": "execution produced no output file", "validator_kind": validator.get("kind")}
    path = Path(output_file)
    if not path.exists():
        return {"status": "failed", "reason": f"execution result missing: {output_file}", "validator_kind": validator.get("kind"), "output_file": output_file}
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected_status = validator.get("expected_status", "ok")
    if payload.get("status") != expected_status:
        return {
            "status": "failed",
            "reason": payload.get("error") or f"execution result status != {expected_status}",
            "validator_kind": validator.get("kind"),
            "output_file": output_file,
            "payload": payload,
        }
    missing = [field for field in validator.get("required_fields", []) if field not in payload]
    if missing:
        return {
            "status": "failed",
            "reason": f"execution result missing required fields: {', '.join(missing)}",
            "validator_kind": validator.get("kind"),
            "output_file": output_file,
            "payload": payload,
        }
    return {
        "status": "ok",
        "validator_kind": validator.get("kind"),
        "output_file": output_file,
        "payload": payload,
    }


def validate_runner_result_contract(contract: dict, execution_result: dict) -> dict:
    validator = contract.get("validator", {})
    output_file = validator.get("output_file") or execution_result.get("output_file")
    if not output_file:
        return {"status": "failed", "reason": "runner produced no output file", "validator_kind": validator.get("kind")}
    path = Path(output_file)
    if not path.exists():
        return {"status": "failed", "reason": f"runner output missing: {output_file}", "validator_kind": validator.get("kind"), "output_file": output_file}
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected_status = validator.get("expected_status", "ok")
    if payload.get("status") != expected_status:
        return {"status": "failed", "reason": payload.get("error") or f"runner output status != {expected_status}", "validator_kind": validator.get("kind"), "output_file": output_file, "payload": payload}
    missing = [field for field in validator.get("required_fields", []) if field not in payload]
    if missing:
        return {"status": "failed", "reason": f"runner output missing required fields: {', '.join(missing)}", "validator_kind": validator.get("kind"), "output_file": output_file, "payload": payload}
    if payload.get("goal") != validator.get("expected_goal"):
        return {"status": "failed", "reason": "runner output goal does not match contract goal", "validator_kind": validator.get("kind"), "output_file": output_file, "payload": payload}
    if payload.get("adapter") != validator.get("expected_adapter"):
        return {"status": "failed", "reason": "runner output adapter does not match contract adapter", "validator_kind": validator.get("kind"), "output_file": output_file, "payload": payload}
    if payload.get("applied_rule_ids", []) != validator.get("expected_rule_ids", []):
        return {"status": "failed", "reason": "runner output applied rules do not match contract rules", "validator_kind": validator.get("kind"), "output_file": output_file, "payload": payload}
    if payload.get("selected_pattern") != validator.get("expected_pattern"):
        return {"status": "failed", "reason": "runner output selected pattern does not match contract pattern", "validator_kind": validator.get("kind"), "output_file": output_file, "payload": payload}
    if validator.get("expected_strategy") is not None and payload.get("strategy") != validator.get("expected_strategy"):
        return {"status": "failed", "reason": "runner output strategy does not match contract strategy", "validator_kind": validator.get("kind"), "output_file": output_file, "payload": payload}
    if validator.get("expected_execution_ordering") and payload.get("executed_ordering", []) != validator.get("expected_execution_ordering", []):
        return {"status": "failed", "reason": "runner executed ordering does not match expected ordering", "validator_kind": validator.get("kind"), "output_file": output_file, "payload": payload}
    if validator.get("expected_stage_order"):
        stage_results = payload.get("stage_results", [])
        stage_order = [item.get("step") for item in stage_results]
        if stage_order != validator.get("expected_stage_order", []):
            return {"status": "failed", "reason": "runner stage results do not match expected stage order", "validator_kind": validator.get("kind"), "output_file": output_file, "payload": payload}
        if any(item.get("status") != "ok" for item in stage_results):
            return {"status": "failed", "reason": "runner stage results contain a non-ok stage", "validator_kind": validator.get("kind"), "output_file": output_file, "payload": payload}
        if len(stage_results) > int(validator.get("max_stage_count", len(stage_results))):
            return {"status": "failed", "reason": "runner stage count exceeded hot-path budget", "validator_kind": validator.get("kind"), "output_file": output_file, "payload": payload}
        baseline_stage_count = int(validator.get("baseline_stage_count", len(stage_results)))
        max_stage_growth = int(validator.get("max_stage_growth", max(0, len(stage_results) - baseline_stage_count)))
        if len(stage_results) - baseline_stage_count > max_stage_growth:
            return {"status": "failed", "reason": "runner stage growth exceeded hot-path budget", "validator_kind": validator.get("kind"), "output_file": output_file, "payload": payload}
        observed_selection_inputs = int(validator.get("observed_selection_inputs", 0))
        max_selection_inputs = int(validator.get("max_selection_inputs", max(1, observed_selection_inputs)))
        if observed_selection_inputs > max_selection_inputs:
            return {"status": "failed", "reason": "runner selection inputs exceeded budget", "validator_kind": validator.get("kind"), "output_file": output_file, "payload": payload}
        expected_strategy = validator.get("expected_strategy") or {}
        fallback_choice = expected_strategy.get("fallback_choice")
        retry_policy = expected_strategy.get("retry_policy")
        budget_profile = validator.get("budget_profile", "standard")
        profile_selection_budget = PROFILE_SELECTION_BUDGETS.get(budget_profile, PROFILE_SELECTION_BUDGETS["standard"])
        if max_selection_inputs != profile_selection_budget:
            return {"status": "failed", "reason": "validator max_selection_inputs does not match profile-derived selection budget", "validator_kind": validator.get("kind"), "output_file": output_file, "payload": payload}
        max_retry_actions = int(validator.get("max_retry_actions", 0))
        if max_retry_actions != retry_budget_for(retry_policy):
            return {"status": "failed", "reason": "validator max_retry_actions does not match retry-policy-derived budget", "validator_kind": validator.get("kind"), "output_file": output_file, "payload": payload}
        budget_source = validator.get("hot_path_budget_source", "baseline")
        expected_pattern = validator.get("expected_pattern")
        derived_stage_count = baseline_stage_count if budget_source == "baseline" else max(baseline_stage_count, len(validator.get("expected_stage_order", [])))
        derived_stage_growth = derived_stage_count - baseline_stage_count
        if budget_source == "baseline" and expected_pattern is not None:
            return {"status": "failed", "reason": "validator hot_path_budget_source baseline is inconsistent with learned pattern replay", "validator_kind": validator.get("kind"), "output_file": output_file, "payload": payload}
        if budget_source != "baseline" and expected_pattern and budget_source != expected_pattern:
            return {"status": "failed", "reason": "validator hot_path_budget_source does not match expected pattern source", "validator_kind": validator.get("kind"), "output_file": output_file, "payload": payload}
        if int(validator.get("max_stage_count", len(stage_results))) != derived_stage_count:
            return {"status": "failed", "reason": "validator max_stage_count does not match source-derived stage budget", "validator_kind": validator.get("kind"), "output_file": output_file, "payload": payload}
        if int(validator.get("max_stage_growth", max_stage_growth)) != derived_stage_growth:
            return {"status": "failed", "reason": "validator max_stage_growth does not match source-derived stage budget", "validator_kind": validator.get("kind"), "output_file": output_file, "payload": payload}
        by_step = {item.get("step"): item.get("details", {}) for item in stage_results}
        if "precheck" in by_step and by_step["precheck"].get("fallback_choice") != fallback_choice:
            return {"status": "failed", "reason": "runner precheck did not apply expected fallback choice", "validator_kind": validator.get("kind"), "output_file": output_file, "payload": payload}
        if "select-adapter" in by_step:
            expected_mode = "reuse-last-good-adapter" if fallback_choice == "sticky-adapter-first" else "select-current-only"
            if by_step["select-adapter"].get("adapter_selection_mode") != expected_mode:
                return {"status": "failed", "reason": "runner select-adapter stage did not apply expected fallback mode", "validator_kind": validator.get("kind"), "output_file": output_file, "payload": payload}
            if by_step["select-adapter"].get("observed_selection_inputs") != observed_selection_inputs:
                return {"status": "failed", "reason": "runner select-adapter stage did not report expected selection inputs", "validator_kind": validator.get("kind"), "output_file": output_file, "payload": payload}
            if by_step["select-adapter"].get("max_selection_inputs") != max_selection_inputs:
                return {"status": "failed", "reason": "runner select-adapter stage did not report expected selection budget", "validator_kind": validator.get("kind"), "output_file": output_file, "payload": payload}
        if "diagnose" in by_step and by_step["diagnose"].get("retry_policy") != retry_policy:
            return {"status": "failed", "reason": "runner diagnose stage did not apply expected retry policy", "validator_kind": validator.get("kind"), "output_file": output_file, "payload": payload}
        if "diagnose" in by_step and by_step["diagnose"].get("max_retry_actions") != max_retry_actions:
            return {"status": "failed", "reason": "runner diagnose stage did not report expected retry budget", "validator_kind": validator.get("kind"), "output_file": output_file, "payload": payload}
        if "recover" in by_step and by_step["recover"].get("retry_policy") != retry_policy:
            return {"status": "failed", "reason": "runner recover stage did not apply expected retry policy", "validator_kind": validator.get("kind"), "output_file": output_file, "payload": payload}
        if "recover" in by_step and by_step["recover"].get("max_retry_actions") != max_retry_actions:
            return {"status": "failed", "reason": "runner recover stage did not report expected retry budget", "validator_kind": validator.get("kind"), "output_file": output_file, "payload": payload}
    return {
        "status": "ok",
        "validator_kind": validator.get("kind"),
        "output_file": output_file,
        "payload": payload,
    }


def build_expected_transform_output(input_text: str, marker: str, mode: str) -> str:
    if mode == "append-marker":
        return input_text + ("\n" if input_text and not input_text.endswith("\n") else "") + marker + "\n"
    raise ValueError(f"unsupported transform mode: {mode}")


def validate_file_transform_result(contract: dict, execution_result: dict) -> dict:
    validator = contract.get("validator", {})
    output_file = validator.get("output_file") or execution_result.get("output_file")
    input_file = validator.get("input_file")
    marker = validator.get("marker")
    mode = validator.get("mode", "append-marker")
    if not output_file:
        return {"status": "failed", "reason": "transform produced no output file", "validator_kind": validator.get("kind")}
    out_path = Path(output_file)
    if not out_path.exists():
        return {"status": "failed", "reason": f"transform output missing: {output_file}", "validator_kind": validator.get("kind"), "output_file": output_file}
    output_text = out_path.read_text(encoding="utf-8")
    input_text = ""
    if input_file:
        in_path = Path(input_file)
        input_text = in_path.read_text(encoding="utf-8") if in_path.exists() else ""
        if validator.get("require_changed", True) and input_text == output_text:
            return {"status": "failed", "reason": "transform output did not change from input", "validator_kind": validator.get("kind"), "output_file": output_file, "input_file": input_file}
    if validator.get("require_exact_output", True):
        expected_output = build_expected_transform_output(input_text, marker or "", mode)
        if output_text != expected_output:
            return {
                "status": "failed",
                "reason": "transform output does not match exact contract-derived output",
                "validator_kind": validator.get("kind"),
                "output_file": output_file,
                "input_file": input_file,
                "payload": {
                    "expected_output": expected_output,
                    "actual_output": output_text,
                },
            }
    elif marker and marker not in output_text:
        return {"status": "failed", "reason": f"transform output missing expected marker: {marker}", "validator_kind": validator.get("kind"), "output_file": output_file}
    return {
        "status": "ok",
        "validator_kind": validator.get("kind"),
        "output_file": output_file,
        "payload": {
            "output_file": output_file,
            "input_file": input_file,
            "mode": mode,
            "exact_output_verified": bool(validator.get("require_exact_output", True)),
        },
    }


def validate_command_output_result(contract: dict, execution_result: dict) -> dict:
    validator = contract.get("validator", {})
    expected_stdout = validator.get("expected_stdout", "")
    actual_stdout = execution_result.get("stdout", "")
    returncode = execution_result.get("returncode")
    output_file = contract.get("output_file")
    if returncode != 0:
        return {
            "status": "failed",
            "reason": f"command output execution returncode != 0 ({returncode})",
            "validator_kind": validator.get("kind"),
            "payload": execution_result,
        }
    if actual_stdout != expected_stdout:
        return {
            "status": "failed",
            "reason": "command output does not match expected stdout exactly",
            "validator_kind": validator.get("kind"),
            "payload": {
                "expected_stdout": expected_stdout,
                "actual_stdout": actual_stdout,
            },
        }
    if output_file:
        path = Path(output_file)
        if not path.exists():
            return {
                "status": "failed",
                "reason": f"command output artifact missing: {output_file}",
                "validator_kind": validator.get("kind"),
            }
        artifact_stdout = path.read_text(encoding="utf-8").rstrip("\n")
        if artifact_stdout != expected_stdout:
            return {
                "status": "failed",
                "reason": "command output artifact does not match expected stdout exactly",
                "validator_kind": validator.get("kind"),
                "payload": {
                    "expected_stdout": expected_stdout,
                    "artifact_stdout": artifact_stdout,
                },
            }
    return {
        "status": "ok",
        "validator_kind": validator.get("kind"),
        "payload": {
            "expected_stdout": expected_stdout,
            "actual_stdout": actual_stdout,
            "artifact_output_file": output_file,
        },
    }


def validate_independent_file_analysis(contract: dict, execution_result: dict) -> dict:
    validator = contract.get("validator", {})
    output_file = validator.get("output_file") or execution_result.get("output_file")
    target = validator.get("target")
    if not output_file:
        return {"status": "failed", "reason": "analysis produced no output file", "validator_kind": validator.get("kind")}
    out_path = Path(output_file)
    if not out_path.exists():
        return {"status": "failed", "reason": f"analysis output missing: {output_file}", "validator_kind": validator.get("kind"), "output_file": output_file}
    adapter_report = json.loads(out_path.read_text(encoding="utf-8"))
    if not target:
        return {"status": "failed", "reason": "validator contract missing target path", "validator_kind": validator.get("kind"), "output_file": output_file}
    target_path = Path(target)
    if not target_path.exists():
        return {"status": "failed", "reason": f"target file does not exist for independent verification: {target}", "validator_kind": validator.get("kind"), "output_file": output_file}
    if not target_path.is_file():
        return {"status": "failed", "reason": f"target is not a regular file: {target}", "validator_kind": validator.get("kind"), "output_file": output_file}
    raw_bytes = target_path.read_bytes()
    content = raw_bytes.decode("utf-8")
    lines = content.splitlines()
    words = content.split()
    independent = {
        "size_bytes": len(raw_bytes),
        "line_count": len(lines),
        "word_count": len(words),
        "char_count": len(content),
        "sha256_bytes": hashlib.sha256(raw_bytes).hexdigest(),
    }
    mismatches = []
    for key, expected in independent.items():
        actual = adapter_report.get(key)
        if actual != expected:
            mismatches.append({"field": key, "adapter_value": actual, "independent_value": expected})
    if mismatches:
        return {
            "status": "failed",
            "reason": "independent re-computation does not match adapter output",
            "validator_kind": validator.get("kind"),
            "mismatches": mismatches,
            "output_file": output_file,
        }
    return {
        "status": "ok",
        "validator_kind": validator.get("kind"),
        "output_file": output_file,
        "verified_fields": list(independent.keys()),
        "payload": adapter_report,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a Polaris execution result independently from the executor.")
    parser.add_argument("validate", nargs="?")
    parser.add_argument("--contract-json", required=True)
    parser.add_argument("--execution-result-json", required=True)
    parser.add_argument("--write-result")
    args = parser.parse_args()

    contract = json.loads(args.contract_json)
    execution_result = json.loads(args.execution_result_json)
    validator = contract.get("validator", {})
    kind = validator.get("kind", "json_status_file")

    if kind == "json_status_file":
        payload = validate_json_status_file(contract, execution_result)
    elif kind == "runner_result_contract":
        payload = validate_runner_result_contract(contract, execution_result)
    elif kind == "file_transform_result":
        payload = validate_file_transform_result(contract, execution_result)
    elif kind == "command_output_result":
        payload = validate_command_output_result(contract, execution_result)
    elif kind == "independent_file_analysis":
        payload = validate_independent_file_analysis(contract, execution_result)
    else:
        payload = {"status": "failed", "reason": f"unknown validator kind: {kind}", "validator_kind": kind}

    if args.write_result:
        path = Path(args.write_result)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
