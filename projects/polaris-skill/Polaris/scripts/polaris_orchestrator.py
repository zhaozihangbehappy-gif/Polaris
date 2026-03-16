#!/usr/bin/env python3
import argparse
import hashlib
import json
import shlex
import subprocess
import sys
from pathlib import Path

# Ensure sibling modules (polaris_task_fingerprint, polaris_failure_records) are importable
sys.path.insert(0, str(Path(__file__).resolve().parent))


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


def require_ok(result: dict, label: str, require_json: bool = False) -> dict:
    if result.get("returncode") != 0:
        raise SystemExit(f"{label} failed: {result.get('stderr') or result.get('stdout') or result.get('returncode')}")
    if require_json and "parsed" not in result:
        raise SystemExit(f"{label} produced no JSON payload")
    return result


def run_checked(cmd: list[str], label: str) -> dict:
    return require_ok(run(cmd), label)


def run_json_checked(cmd: list[str], label: str) -> dict:
    return require_ok(run_json(cmd), label, require_json=True)


HOT_PATH_BUDGET_WARN = 8192
HOT_PATH_BUDGET_HARD = 16384


def hot_path_budget_check(
    selected_pattern_json: str,
    execution_contract_json: str,
    applied_rules_json: str,
    experience_hints_json: str,
) -> dict:
    """Measure total decision-bearing JSON bytes passed to the adapter.

    Returns a budget report with warn/exceeded flags.  Both thresholds
    are advisory (warn-only) — the caller logs diagnostics but does not
    modify the execution contract or adapter inputs.
    """
    fields = {
        "selected_pattern_json": len(selected_pattern_json.encode("utf-8")),
        "execution_contract_json": len(execution_contract_json.encode("utf-8")),
        "applied_rules_json": len(applied_rules_json.encode("utf-8")),
        "experience_hints_json": len(experience_hints_json.encode("utf-8")),
    }
    total = sum(fields.values())
    return {
        "total_bytes": total,
        "fields": fields,
        "warn": total > HOT_PATH_BUDGET_WARN,
        "exceeded": total > HOT_PATH_BUDGET_HARD,
        "budget_warn": HOT_PATH_BUDGET_WARN,
        "budget_hard": HOT_PATH_BUDGET_HARD,
    }


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
    output_mode: str = "diagnostic_detail",
) -> dict | None:
    if key not in policy["event_keys"]:
        return None
    runtime_dir = Path(state_file).resolve().parent if state_file else base.parent
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
            str(runtime_dir / "runtime-events.jsonl"),
            "--status-file",
            str(runtime_dir / "runtime-status.json"),
            "--detail",
            policy["report_detail"],
            "--output-mode",
            output_mode,
        ]
    )


def emit_runtime_surface(base: Path, policy: dict, key: str, state_file: str, kind: str) -> dict | None:
    if key not in policy["surface_keys"]:
        return None
    runtime_dir = Path(state_file).resolve().parent
    return run(
        [
            sys.executable,
            str(base / "polaris_runtime.py"),
            "surface",
            "--state",
            state_file,
            "--status-file",
            str(runtime_dir / "runtime-live-status.json"),
            "--event-log",
            str(runtime_dir / "runtime-events.jsonl"),
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


def unique(values: list[str]) -> list[str]:
    seen = set()
    ordered = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


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
            policy.get("effective_adapter_capabilities", policy["adapter_capabilities"]),
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


def queue_learning_item(base: Path, state_file: str, kind: str, payload: dict) -> dict:
    return run(
        [
            sys.executable,
            str(base / "polaris_state.py"),
            "backlog-add",
            "--state",
            state_file,
            "--kind",
            kind,
            "--payload",
            json.dumps(payload, sort_keys=True),
        ]
    )


def consolidate_learning_item(base: Path, patterns_file: str, rules_file: str, item: dict) -> dict | None:
    kind = item.get("kind")
    payload = item.get("payload", {})
    if kind == "success_marker":
        return run(
            [
                sys.executable,
                str(base / "polaris_success_patterns.py"),
                "consolidate-marker",
                "--patterns",
                patterns_file,
                "--marker",
                json.dumps(payload, sort_keys=True),
                "--promote-auto",
                "yes",
            ]
        )
    if kind == "rule_candidate":
        return run(
            [
                sys.executable,
                str(base / "polaris_rules.py"),
                "consolidate-candidate",
                "--rules",
                rules_file,
                "--candidate",
                json.dumps(payload, sort_keys=True),
                "--promote-auto",
                "yes",
            ]
        )
    return None


def make_fingerprint(kind: str, payload: dict) -> str:
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]
    return f"{kind}-{digest}"


REPAIR_LEARNING_PROFILES = {
    "missing_dependency": {
        "action": "Verify interpreter, pip visibility, and dependency availability before retrying the same local runtime path",
        "scope": "repair-python-env",
        "summary": "Dependency failures improved after a bounded local environment probe tree captured actionable evidence",
        "outcome": "dependency repair path documented with local environment evidence",
        "tags": ["python", "dependency"],
        "sequence": ["diagnose", "dependency-probes", "record-evidence", "recover"],
        "priority": 70,
        "confidence": 78,
    },
    "missing_tool": {
        "action": "Verify PATH, command resolution, and nearby executable alternatives before retrying the same local tool step",
        "scope": "repair-tool-resolution",
        "summary": "Missing-tool failures improved after bounded PATH and command-resolution probes captured local evidence",
        "outcome": "tool-resolution repair path documented with local command evidence",
        "tags": ["tooling", "path"],
        "sequence": ["diagnose", "tool-probes", "record-evidence", "recover"],
        "priority": 68,
        "confidence": 76,
    },
    "import_path_issue": {
        "action": "Inspect interpreter search paths and local package layout before retrying the same import path",
        "scope": "repair-import-layout",
        "summary": "Import-path failures improved after bounded interpreter-path and package-layout probes captured local evidence",
        "outcome": "import-layout repair path documented with local module evidence",
        "tags": ["python", "imports"],
        "sequence": ["diagnose", "import-probes", "record-evidence", "recover"],
        "priority": 66,
        "confidence": 74,
    },
    "config_parse_error": {
        "action": "Inspect nearby config files and local syntax validation results before retrying the same configuration step",
        "scope": "repair-config-parse",
        "summary": "Config-parse failures improved after bounded local config probes captured syntax and file context",
        "outcome": "config repair path documented with local syntax evidence",
        "tags": ["config", "syntax"],
        "sequence": ["diagnose", "config-probes", "record-evidence", "recover"],
        "priority": 64,
        "confidence": 74,
    },
    "test_failure": {
        "action": "Inspect failing test context, repository state, and nearby test configuration before retrying the same validation step",
        "scope": "repair-test-context",
        "summary": "Test failures improved after bounded local test-context probes captured reproducible repository evidence",
        "outcome": "test-failure repair path documented with local validation evidence",
        "tags": ["tests", "validation"],
        "sequence": ["diagnose", "test-probes", "record-evidence", "recover"],
        "priority": 62,
        "confidence": 72,
    },
    "path_or_missing_file": {
        "action": "Verify working directory, nearby files, and target path assumptions before retrying the same file operation",
        "scope": "repair-path-resolution",
        "summary": "Path failures improved after bounded working-directory and nearby-file probes captured local filesystem evidence",
        "outcome": "path-resolution repair path documented with local filesystem evidence",
        "tags": ["filesystem", "paths"],
        "sequence": ["diagnose", "path-probes", "record-evidence", "recover"],
        "priority": 65,
        "confidence": 75,
    },
    "unknown": {
        "action": "Collect the smallest local evidence set that narrows the failure before retrying the same step",
        "scope": "repair-generic-local",
        "summary": "Unknown failures improved after bounded generic local probes captured enough evidence to guide the next retry",
        "outcome": "generic repair path documented with bounded local evidence",
        "tags": ["generic", "triage"],
        "sequence": ["diagnose", "generic-probes", "record-evidence", "recover"],
        "priority": 55,
        "confidence": 68,
    },
}


def build_repair_learning_items(repair_report: dict, resolved_repair_depth: str, execution_profile: str, mode: str, adapter_name: str | None) -> tuple[dict, dict] | None:
    parsed = repair_report.get("parsed", {})
    failure_type = parsed.get("failure_type", "unknown")
    if parsed.get("nonrepair_stop"):
        return None
    profile = REPAIR_LEARNING_PROFILES.get(failure_type, REPAIR_LEARNING_PROFILES["unknown"])
    repair_context = {
        "failure_type": failure_type,
        "recommended_tree": parsed.get("recommended_tree", "generic_probe_tree"),
        "execution_profile": execution_profile,
        "mode": mode,
        "adapter": adapter_name or "none",
    }
    rule_fp = make_fingerprint("repair-rule", repair_context)
    pattern_fp = make_fingerprint("repair-pattern", {**repair_context, "sequence": profile["sequence"]})
    extra_tags = unique(["repair", "local", failure_type, parsed.get("repair_class", "generic_probe_tree"), resolved_repair_depth] + profile["tags"])
    rule_candidate = {
        "rule_id": rule_fp,
        "fingerprint": rule_fp,
        "layer": "experimental",
        "trigger": failure_type,
        "action": profile["action"],
        "evidence": ["runtime-repair-results.json", "runtime-repair-plan.json", "runtime-repair-report.json"],
        "scope": profile["scope"],
        "tags": unique(extra_tags + ["orchestration"]),
        "validation": "repair action tree probes completed locally",
        "priority": profile["priority"],
        "strategy_overrides": {"retry_policy": "bounded-repair-with-evidence"},
    }
    repair_marker = {
        "pattern_id": pattern_fp,
        "fingerprint": pattern_fp,
        "summary": profile["summary"],
        "trigger": failure_type,
        "sequence": profile["sequence"],
        "outcome": profile["outcome"],
        "evidence": ["runtime-repair-results.json", "runtime-repair-plan.json", "runtime-repair-report.json"],
        "adapter": adapter_name,
        "tags": unique(extra_tags + ["orchestration"]),
        "modes": [mode],
        "confidence": profile["confidence"],
        "lifecycle_state": "experimental",
        "reusable": True,
        "strategy_hints": {
            "fallback_choice": "sticky-adapter-first",
            "validation_strategy": "runner-contract-strict",
            "execution_ordering": profile["sequence"],
            "hot_path_budget": len(profile["sequence"]),
        },
    }
    return rule_candidate, repair_marker


def consolidate_backlog(base: Path, state_file: str, patterns_file: str, rules_file: str, backlog_items: list[dict]) -> tuple[list[dict], list[dict], dict]:
    consolidation_results = []
    retained_items = []
    for item in backlog_items:
        result = consolidate_learning_item(base, patterns_file, rules_file, item)
        if result is not None:
            consolidation_results.append(result)
        if result is None or result.get("returncode") != 0:
            retained_items.append(item)
    summary = build_consolidation_summary(backlog_items, consolidation_results, retained_items)
    if backlog_items:
        run_checked(
            [
                sys.executable,
                str(base / "polaris_state.py"),
                "artifact",
                "--state",
                state_file,
                "--key",
                "learning_summary",
                "--value",
                json.dumps(summary, sort_keys=True),
            ],
            "write learning summary",
        )
        run_checked(
            [
                sys.executable,
                str(base / "polaris_state.py"),
                "backlog-replace",
                "--state",
                state_file,
                "--payload",
                json.dumps(retained_items, sort_keys=True),
            ],
            "replace learning backlog",
        )
    return consolidation_results, retained_items, summary


def build_consolidation_summary(backlog_items: list[dict], consolidation_results: list[dict], retained_items: list[dict]) -> dict:
    summary = {
        "queued_items": len(backlog_items),
        "processed_items": 0,
        "retained_items": len(retained_items),
        "rule_candidates": 0,
        "success_markers": 0,
        "promoted_rules": [],
        "promoted_patterns": [],
        "merged_rules": [],
        "merged_patterns": [],
        "failed_rules": [],
        "failed_patterns": [],
    }
    for item in backlog_items:
        if item.get("kind") == "rule_candidate":
            summary["rule_candidates"] += 1
        elif item.get("kind") == "success_marker":
            summary["success_markers"] += 1
    for result in consolidation_results:
        if not result or result.get("returncode") != 0:
            continue
        summary["processed_items"] += 1
        parsed = result.get("parsed")
        if not parsed and result.get("stdout"):
            try:
                parsed = json.loads(result["stdout"])
            except json.JSONDecodeError:
                parsed = None
        if not parsed:
            continue
        if "rule" in parsed:
            rule = parsed["rule"]
            if parsed.get("promoted"):
                summary["promoted_rules"].append(rule.get("rule_id"))
            else:
                summary["merged_rules"].append(rule.get("rule_id"))
        if "pattern" in parsed:
            pattern = parsed["pattern"]
            if parsed.get("promoted"):
                summary["promoted_patterns"].append(pattern.get("pattern_id"))
            else:
                summary["merged_patterns"].append(pattern.get("pattern_id"))
    for item in retained_items:
        payload = item.get("payload", {})
        if item.get("kind") == "rule_candidate":
            summary["failed_rules"].append(payload.get("rule_id") or payload.get("fingerprint"))
        elif item.get("kind") == "success_marker":
            summary["failed_patterns"].append(payload.get("pattern_id") or payload.get("fingerprint"))
    return summary


def applied_rules_payload(selected_rules: dict) -> list[dict]:
    rules = selected_rules.get("parsed", {}).get("rules", [])
    return [
        {
            "rule_id": item.get("rule_id"),
            "layer": item.get("layer"),
            "trigger": item.get("trigger"),
            "action": item.get("action"),
            "scope": item.get("scope"),
            "tags": item.get("tags", []),
            "priority": item.get("priority"),
        }
        for item in rules
    ]


def stop_action(applied_rules: list[dict], repair_report: dict | None = None) -> str:
    parsed = repair_report.get("parsed", {}) if repair_report else {}
    if parsed.get("nonrepair_stop"):
        stop_rule = next((rule for rule in applied_rules if "stop" in rule.get("tags", [])), None)
        return stop_rule.get("action") if stop_rule else parsed.get("retry_guidance", "Stop and reduce scope")
    next_depth = parsed.get("next_depth") or "deep"
    return f"Retry or escalate to {next_depth} if the same failure repeats"


def _build_failure_avoidance_hints(error_text: str, error_class: str, command: str) -> list[dict]:
    """Map error_class + error_text → structured avoidance hint primitives.

    Hints must be actionable: the adapter applies them before execution,
    so each hint should change the command, env, cwd, or timeout in a way
    that has a realistic chance of avoiding the same failure on retry.
    """
    hints = []
    text = error_text.lower()
    if error_class == "missing_dependency" and "no module named" in text:
        parts = text.split("no module named")
        if len(parts) > 1:
            module = parts[1].strip().strip("'\"").split()[0]
            hints.append({"kind": "set_env", "vars": {"POLARIS_HINT_INSTALL": module}})
    if error_class == "missing_dependency" and "required env" in text:
        # Extract env var name from original error text to preserve case
        import re
        m = re.search(r"required env (\w+)", error_text, re.IGNORECASE)
        if m:
            hints.append({"kind": "set_env", "vars": {m.group(1): "polaris-provided"}})
    if error_class == "permission_denial":
        hints.append({"kind": "set_env", "vars": {"POLARIS_HINT_PERMISSION_ERROR": "true"}})
    if error_class == "path_or_missing_file":
        # Rewrite cwd to /tmp as a safe fallback for path-dependent failures
        hints.append({"kind": "rewrite_cwd", "cwd": "/tmp"})
    if "timeout" in text:
        hints.append({"kind": "set_timeout", "timeout_ms": 120000})
    if not hints:
        hints.append({"kind": "set_timeout", "timeout_ms": 120000})
    return hints


def choose_execution_kind(base: Path, requested_kind: str, adapter: dict, applied_rules: list[dict], selected_pattern: dict | None, simulate_error: str | None, plan_requires: list[str] | None = None) -> dict:
    return run_json_checked(
        [
            sys.executable,
            str(base / "polaris_contract_planner.py"),
            "plan-family",
            "--requested-kind",
            requested_kind,
            "--adapter-json",
            json.dumps(adapter, sort_keys=True),
            "--applied-rules-json",
            json.dumps(applied_rules, sort_keys=True),
            "--selected-pattern-json",
            json.dumps(selected_pattern or {}, sort_keys=True),
            *( ["--simulate-error", simulate_error] if simulate_error else []),
            *( ["--plan-requires-json", json.dumps(plan_requires)] if plan_requires else []),
        ],
        "plan execution family",
    )


LAYER_PRECEDENCE = {"hard": 300, "soft": 200, "pattern": 150, "experimental": 100}
SLOT_PERMISSIONS = {
    "hard": {"retry_policy"},
    "soft": {"fallback_choice", "retry_policy", "validation_strategy", "execution_ordering"},
    "pattern": {"fallback_choice", "validation_strategy", "execution_ordering"},
    "experimental": {"fallback_choice", "validation_strategy"},
}


def default_validation_strategy(execution_kind: str) -> str:
    return {
        "runner": "runner-contract-match",
        "file_transform": "exact-output-match",
        "command_output": "stdout-exact-match",
    }.get(execution_kind, "family-default")


def default_execution_strategy(execution_kind: str) -> dict:
    return {
        "fallback_choice": "selected-adapter-only",
        "retry_policy": "bounded-repair",
        "validation_strategy": default_validation_strategy(execution_kind),
        "execution_ordering": ["execute", "validate"],
    }


def normalized_pattern_ordering(selected_pattern: dict | None) -> list[str]:
    if not selected_pattern:
        return []
    hints = selected_pattern.get("strategy_hints", {})
    if hints.get("execution_ordering"):
        return hints["execution_ordering"]
    pattern_id = selected_pattern.get("pattern_id", "")
    tags = set(selected_pattern.get("tags", []))
    sequence = selected_pattern.get("sequence", [])
    if "deferred-learning" in tags or "success-marker" in pattern_id:
        return ["precheck", "execute", "validate"]
    return sequence


def retry_budget_for(retry_policy: str) -> int:
    if retry_policy == "respect-hard-stop-rules":
        return 0
    if retry_policy in {"bounded-repair", "bounded-repair-with-learning", "bounded-repair-with-evidence"}:
        return 1
    return 1


def profile_budget_defaults(execution_profile: str) -> dict:
    return {
        "micro": {
            "max_selection_inputs": 1,
            "max_state_writes": 48,
            "max_retry_actions": 0,
            "max_repair_probe_steps": 0,
            "max_learning_hot_path_ops": 1,
        },
        "standard": {
            "max_selection_inputs": 4,
            "max_state_writes": 56,
            "max_retry_actions": 1,
            "max_repair_probe_steps": 4,
            "max_learning_hot_path_ops": 1,
        },
        "deep": {
            "max_selection_inputs": 8,
            "max_state_writes": 72,
            "max_retry_actions": 1,
            "max_repair_probe_steps": 6,
            "max_learning_hot_path_ops": 2,
        },
    }.get(execution_profile, {
        "max_selection_inputs": 4,
        "max_state_writes": 56,
        "max_retry_actions": 1,
        "max_repair_probe_steps": 4,
        "max_learning_hot_path_ops": 1,
    })


def build_efficiency_budget(selected_pattern: dict | None, execution_kind: str, execution_profile: str, applied_rules: list[dict], strategy: dict) -> dict:
    baseline_stage_count = len(default_execution_strategy(execution_kind).get("execution_ordering", []))
    if execution_kind == "runner" and execution_profile == "standard":
        baseline_stage_count = 3
    observed_selection_inputs = len(applied_rules) + (1 if selected_pattern else 0)
    defaults = profile_budget_defaults(execution_profile)
    max_retry_actions = min(defaults["max_retry_actions"], retry_budget_for(strategy.get("retry_policy", "bounded-repair")))
    if not selected_pattern:
        return {
            "baseline_stage_count": baseline_stage_count,
            "max_stage_count": baseline_stage_count,
            "max_stage_growth": 0,
            "max_retry_actions": max_retry_actions,
            "observed_selection_inputs": observed_selection_inputs,
            "max_selection_inputs": defaults["max_selection_inputs"],
            "max_state_writes": defaults["max_state_writes"],
            "max_repair_probe_steps": defaults["max_repair_probe_steps"],
            "max_learning_hot_path_ops": defaults["max_learning_hot_path_ops"],
            "profile": execution_profile,
            "source": "baseline",
        }
    hints = selected_pattern.get("strategy_hints", {})
    ordering = normalized_pattern_ordering(selected_pattern)
    hinted_budget = hints.get("hot_path_budget")
    max_stage_count = int(hinted_budget) if hinted_budget is not None else len(ordering)
    max_stage_count = max(baseline_stage_count, max_stage_count)
    return {
        "baseline_stage_count": baseline_stage_count,
        "max_stage_count": max_stage_count,
        "max_stage_growth": max_stage_count - baseline_stage_count,
        "max_retry_actions": max_retry_actions,
        "observed_selection_inputs": observed_selection_inputs,
        "max_selection_inputs": defaults["max_selection_inputs"],
        "max_state_writes": defaults["max_state_writes"],
        "max_repair_probe_steps": defaults["max_repair_probe_steps"],
        "max_learning_hot_path_ops": defaults["max_learning_hot_path_ops"],
        "profile": execution_profile,
        "source": selected_pattern.get("pattern_id") or "selected-pattern",
    }


def candidate_sort_key(candidate: dict) -> tuple:
    return (
        -int(candidate.get("precedence", 0)),
        -int(candidate.get("priority", 0)),
        -int(candidate.get("confidence", 0)),
        -(1 if candidate.get("last_validated_at") else 0),
        str(candidate.get("last_validated_at") or ""),
        str(candidate.get("source_id") or ""),
    )


def resolve_strategy_slot(slot: str, default_value, candidates: list[dict]) -> tuple[object, dict]:
    allowed = [candidate for candidate in candidates if slot in SLOT_PERMISSIONS.get(candidate.get("layer", "experimental"), set())]
    ignored = [candidate for candidate in candidates if slot not in SLOT_PERMISSIONS.get(candidate.get("layer", "experimental"), set())]
    ordered = sorted(allowed, key=candidate_sort_key)
    winner = ordered[0] if ordered else None
    return (winner.get("value") if winner else default_value), {
        "default": default_value,
        "winner": {
            "source_id": winner.get("source_id"),
            "layer": winner.get("layer"),
            "value": winner.get("value"),
            "reason": winner.get("reason"),
        } if winner else None,
        "candidates": [
            {
                "source_id": item.get("source_id"),
                "layer": item.get("layer"),
                "value": item.get("value"),
                "reason": item.get("reason"),
                "priority": item.get("priority"),
                "confidence": item.get("confidence"),
            }
            for item in ordered
        ],
        "ignored": [
            {
                "source_id": item.get("source_id"),
                "layer": item.get("layer"),
                "value": item.get("value"),
                "reason": item.get("reason"),
            }
            for item in ignored
        ],
    }


def build_execution_strategy(applied_rules: list[dict], selected_pattern: dict | None, execution_profile: str, execution_kind: str) -> dict:
    defaults = default_execution_strategy(execution_kind)
    if execution_kind == "runner" and execution_profile == "standard" and not selected_pattern:
        defaults["execution_ordering"] = ["select-adapter", "execute", "validate"]
    hard_rules = [rule.get("rule_id") for rule in applied_rules if rule.get("layer") == "hard"]
    soft_rules = [rule.get("rule_id") for rule in applied_rules if rule.get("layer") == "soft"]
    experimental_rules = [rule.get("rule_id") for rule in applied_rules if rule.get("layer") == "experimental"]
    candidates = []
    for rule in applied_rules:
        layer = rule.get("layer", "experimental")
        rule_overrides = dict(rule.get("strategy_overrides", {}))
        tags = set(rule.get("tags", []))
        if layer == "hard" and not rule_overrides:
            rule_overrides["retry_policy"] = "respect-hard-stop-rules"
        if layer == "soft" and "repair" in tags and "retry_policy" not in rule_overrides:
            rule_overrides["retry_policy"] = "bounded-repair-with-evidence"
        for slot, value in rule_overrides.items():
            candidates.append(
                {
                    "slot": slot,
                    "value": value,
                    "layer": layer,
                    "source_id": rule.get("rule_id"),
                    "priority": int(rule.get("priority", 0)),
                    "confidence": int(rule.get("validation_count", 0)),
                    "last_validated_at": rule.get("last_validated_at"),
                    "precedence": LAYER_PRECEDENCE.get(layer, 0),
                    "reason": f"rule:{rule.get('rule_id')}",
                }
            )
    if selected_pattern:
        pattern_hints = dict(selected_pattern.get("strategy_hints", {}))
        if not pattern_hints.get("execution_ordering"):
            pattern_hints["execution_ordering"] = normalized_pattern_ordering(selected_pattern)
        if execution_kind == "runner" and not pattern_hints.get("validation_strategy"):
            pattern_hints["validation_strategy"] = "runner-contract-strict"
        if not pattern_hints.get("fallback_choice"):
            pattern_hints["fallback_choice"] = "sticky-adapter-first"
        for slot, value in pattern_hints.items():
            if slot == "hot_path_budget":
                continue
            candidates.append(
                {
                    "slot": slot,
                    "value": value,
                    "layer": "pattern",
                    "source_id": selected_pattern.get("pattern_id"),
                    "priority": int(selected_pattern.get("selection_count", 0)),
                    "confidence": int(selected_pattern.get("confidence", 0)),
                    "last_validated_at": selected_pattern.get("last_validated_at"),
                    "precedence": LAYER_PRECEDENCE["pattern"],
                    "reason": f"pattern:{selected_pattern.get('pattern_id')}",
                }
            )

    strategy = {}
    slot_resolution = {}
    for slot, default_value in defaults.items():
        slot_value, resolution = resolve_strategy_slot(slot, default_value, [candidate for candidate in candidates if candidate.get("slot") == slot])
        strategy[slot] = slot_value
        slot_resolution[slot] = resolution

    strategy["strategy_trace"] = {
        "hard_rules": hard_rules,
        "soft_rules": soft_rules,
        "experimental_rules": experimental_rules,
        "selected_pattern": selected_pattern.get("pattern_id") if selected_pattern else None,
        "execution_profile": execution_profile,
        "execution_kind": execution_kind,
        "slot_permissions": {key: sorted(value) for key, value in SLOT_PERMISSIONS.items()},
        "slot_resolution": slot_resolution,
    }
    return strategy


def summarize_contract_for_diff(contract: dict) -> dict:
    return {
        "kind": contract.get("kind"),
        "adapter": contract.get("adapter"),
        "selected_pattern": contract.get("selected_pattern"),
        "applied_rule_ids": contract.get("applied_rule_ids", []),
        "strategy": contract.get("strategy", {}),
        "validator_kind": contract.get("validator", {}).get("kind"),
        "validator_shape": {k: v for k, v in contract.get("validator", {}).items() if k != "output_file"},
    }


def build_contract_diff(before: dict, after: dict) -> dict:
    diff = {}
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            diff[key] = {"before": before.get(key), "after": after.get(key)}
    return diff


def validation_directness_rank(validation_strategy: str | None) -> int:
    return {
        "family-default": 0,
        "runner-contract-match": 1,
        "runner-contract-strict": 2,
        "exact-output-match": 3,
        "stdout-exact-match": 3,
    }.get(validation_strategy or "family-default", 0)


def extract_stage_metrics(payload: dict | None) -> dict:
    stage_results = (payload or {}).get("stage_results", [])
    stage_map = {item.get("step"): item.get("details", {}) for item in stage_results}
    return {
        "stage_count": len(stage_results),
        "adapter_selection_cost": 0 if "select-adapter" not in stage_map else (1 if stage_map["select-adapter"].get("adapter_selection_mode") == "reuse-last-good-adapter" else 2),
        "repair_probe_steps": len([item for item in stage_results if item.get("step") in {"diagnose", "generic-probes", "record-evidence", "recover"}]),
    }


def build_runtime_efficiency_metrics(state_payload: dict, contract: dict, validation_payload: dict | None, resumed_after_repair: bool, repair_probe_steps: int, family_transfer_applied: bool) -> dict:
    runtime_metrics = state_payload.get("runtime", {}).get("metrics", {})
    validator = contract.get("validator", {})
    strategy = contract.get("strategy", {})
    stage_metrics = extract_stage_metrics(validation_payload)
    return {
        "budget_profile": validator.get("budget_profile"),
        "hot_path_budget_source": validator.get("hot_path_budget_source"),
        "selection_inputs": validator.get("observed_selection_inputs", 0),
        "max_selection_inputs": validator.get("max_selection_inputs", 0),
        # The efficiency artifact itself is recorded through a final state write.
        "state_write_count": int(runtime_metrics.get("state_write_count", 0)) + 1,
        "max_state_writes": validator.get("max_state_writes", 0),
        "retry_actions": 1 if resumed_after_repair else 0,
        "max_retry_actions": validator.get("max_retry_actions", 0),
        "repair_probe_steps": repair_probe_steps if repair_probe_steps else stage_metrics.get("repair_probe_steps", 0),
        "max_repair_probe_steps": validator.get("max_repair_probe_steps", 0),
        "learning_hot_path_ops": runtime_metrics.get("learning_hot_path_ops", 0),
        "max_learning_hot_path_ops": validator.get("max_learning_hot_path_ops", 0),
        "stage_count": stage_metrics.get("stage_count", 0),
        "max_stage_count": validator.get("max_stage_count", 0),
        "validator_directness_rank": validation_directness_rank(strategy.get("validation_strategy")),
        "adapter_selection_cost": stage_metrics.get("adapter_selection_cost", 0),
        "family_transfer_applied": family_transfer_applied,
        "cold_path_cost": len(state_payload.get("learning_backlog", [])),
        "expected_benefit": "lower hot-path cost with stricter validation replay" if family_transfer_applied or strategy.get("validation_strategy") == "runner-contract-strict" else "bounded local execution",
    }


def persist_efficiency_metrics(base: Path, state_file: str, runtime_dir: Path, metrics: dict) -> dict:
    (runtime_dir / "runtime-efficiency-metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return run_checked([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", state_file, "--key", "efficiency_metrics", "--value", json.dumps(metrics, sort_keys=True)], "record efficiency metrics")


def build_execution_contract(base: Path, goal: str, state_file: str, adapter: dict, execution_profile: str, mode: str, applied_rules: list[dict], selected_pattern: dict | None, simulate_error: str | None, execution_kind: str, analysis_target: str | None = None, shell_command: str | None = None, shell_cwd: str | None = None, shell_timeout_ms: int = 60000, experience_hints: dict | None = None) -> dict:
    runtime_dir = Path(state_file).resolve().parent
    default_output_file = str(runtime_dir / "runtime-execution-result.json")
    strategy = build_execution_strategy(applied_rules, selected_pattern, execution_profile, execution_kind)
    contract = {
        "adapter": adapter.get("tool"),
        "goal": goal,
        "mode": mode,
        "execution_profile": execution_profile,
        "output_file": default_output_file,
        "applied_rule_ids": [item.get("rule_id") for item in applied_rules],
        "selected_pattern": selected_pattern.get("pattern_id") if selected_pattern else None,
        "selected_pattern_sequence": selected_pattern.get("sequence", []) if selected_pattern else [],
        "strategy": strategy,
        "simulate_error": simulate_error,
    }
    if execution_kind == "shell_command":
        shell_output = str(runtime_dir / "runtime-execution-result.json")
        contract.update({
            "kind": "shell_command",
            "shell_command": shell_command or goal,
            "shell_cwd": shell_cwd or str(runtime_dir),
            "shell_timeout_ms": shell_timeout_ms,
            "output_file": shell_output,
            "experience_hints": experience_hints or {},
            "validator": {
                "kind": "json_status_file",
                "output_file": shell_output,
                "expected_status": "ok",
                "required_fields": ["status", "command", "exit_code", "duration_ms"],
            },
        })
        return contract
    if execution_kind == "file_analysis":
        target = analysis_target or str(base / "polaris_planner.py")
        analysis_output = str(runtime_dir / "runtime-analysis-result.json")
        contract.update(
            {
                "kind": "file_analysis",
                "script_path": str(base / "polaris_file_analysis.py"),
                "output_file": analysis_output,
                "args": [
                    "--target", target,
                    "--output-file", analysis_output,
                ],
                "validator": {
                    "kind": "independent_file_analysis",
                    "output_file": analysis_output,
                    "target": target,
                },
            }
        )
        return contract
    if execution_kind == "file_transform":
        input_file = runtime_dir / "runtime-transform-input.txt"
        input_file.write_text(f"Polaris input for goal: {goal}\n", encoding="utf-8")
        transform_output = str(runtime_dir / "runtime-transform-output.txt")
        marker = f"POLARIS_TRANSFORM::{execution_profile.upper()}::{adapter.get('tool', 'unknown')}"
        contract.update(
            {
                "kind": "file_transform",
                "script_path": str(base / "polaris_file_transform.py"),
                "input_file": str(input_file),
                "output_file": transform_output,
                "args": [
                    "--input-file", str(input_file),
                    "--output-file", transform_output,
                    "--marker", marker,
                    "--mode", "append-marker",
                ],
                "validator": {
                    "kind": "file_transform_result",
                    "input_file": str(input_file),
                    "output_file": transform_output,
                    "marker": marker,
                    "mode": "append-marker",
                    "require_changed": True,
                    "require_exact_output": True,
                },
            }
        )
        return contract
    if execution_kind == "command_output":
        expected_stdout = f"POLARIS_COMMAND_OUTPUT::{execution_profile.upper()}::{adapter.get('tool', 'unknown')}"
        command_output_file = str(runtime_dir / "runtime-command-output.txt")
        command = "python3 " + shlex.quote(str(base / "polaris_emit_text.py")) + " --text " + shlex.quote(expected_stdout)
        if simulate_error:
            command += " && exit 1"
        contract.update(
            {
                "kind": "command_output",
                "command": command,
                "output_file": command_output_file,
                "validator": {
                    "kind": "command_output_result",
                    "expected_stdout": expected_stdout,
                },
            }
        )
        return contract
    strict_runner_validation = strategy.get("validation_strategy") == "runner-contract-strict"
    hot_path_budget = build_efficiency_budget(selected_pattern, contract.get("kind", "runner"), execution_profile, applied_rules, strategy)
    contract["validator"] = {
        "kind": "runner_result_contract",
        "output_file": default_output_file,
        "expected_status": "ok",
        "required_fields": ["status", "adapter", "goal", "result"] + (["strategy", "executed_ordering", "stage_results"] if strict_runner_validation else []),
        "expected_goal": goal,
        "expected_adapter": adapter.get("tool"),
        "expected_rule_ids": [item.get("rule_id") for item in applied_rules],
        "expected_pattern": selected_pattern.get("pattern_id") if selected_pattern else None,
        "expected_strategy": strategy if strict_runner_validation else None,
        "expected_execution_ordering": strategy.get("execution_ordering", []) if strict_runner_validation else [],
        "expected_stage_order": strategy.get("execution_ordering", []) if strict_runner_validation else [],
        "baseline_stage_count": hot_path_budget["baseline_stage_count"],
        "max_stage_count": hot_path_budget["max_stage_count"],
        "max_stage_growth": hot_path_budget["max_stage_growth"],
        "max_retry_actions": hot_path_budget["max_retry_actions"],
        "observed_selection_inputs": hot_path_budget["observed_selection_inputs"],
        "max_selection_inputs": hot_path_budget["max_selection_inputs"],
        "max_state_writes": hot_path_budget["max_state_writes"],
        "max_repair_probe_steps": hot_path_budget["max_repair_probe_steps"],
        "max_learning_hot_path_ops": hot_path_budget["max_learning_hot_path_ops"],
        "budget_profile": hot_path_budget["profile"],
        "hot_path_budget_source": hot_path_budget["source"],
    }
    if "script_path" in adapter.get("inputs", []):
        contract["kind"] = "script"
        contract["script_path"] = str(base / "polaris_task_runner.py")
        contract["args"] = [
            "--goal", goal,
            "--state", state_file,
            "--output", default_output_file,
            "--mode", mode,
            "--execution-profile", execution_profile,
            "--adapter", adapter.get("tool", "unknown"),
            "--applied-rules-json", json.dumps(applied_rules, sort_keys=True),
            "--selected-pattern-json", json.dumps(selected_pattern or {}, sort_keys=True),
            "--execution-contract-json", json.dumps({"rule_count": len(applied_rules), "pattern": selected_pattern.get("pattern_id") if selected_pattern else None, "strategy": strategy, "kind": contract.get("kind", "runner"), "validator": contract.get("validator", {})}, sort_keys=True),
        ]
        if simulate_error:
            contract["args"].extend(["--simulate-error", simulate_error])
        return contract

    command = " ".join(
        [
            "python3",
            shlex.quote(str(base / "polaris_task_runner.py")),
            "--goal", shlex.quote(goal),
            "--state", shlex.quote(state_file),
            "--output", shlex.quote(default_output_file),
            "--mode", shlex.quote(mode),
            "--execution-profile", shlex.quote(execution_profile),
            "--adapter", shlex.quote(adapter.get("tool", "unknown")),
            "--applied-rules-json", shlex.quote(json.dumps(applied_rules, sort_keys=True)),
            "--selected-pattern-json", shlex.quote(json.dumps(selected_pattern or {}, sort_keys=True)),
            "--execution-contract-json", shlex.quote(json.dumps({"rule_count": len(applied_rules), "pattern": selected_pattern.get("pattern_id") if selected_pattern else None, "strategy": strategy, "kind": contract.get("kind", "runner"), "validator": contract.get("validator", {})}, sort_keys=True)),
        ]
    )
    if simulate_error:
        command += " --simulate-error " + shlex.quote(simulate_error)
    contract["kind"] = "command"
    contract["command"] = command
    return contract


def execute_contract(base: Path, adapter: dict, contract: dict, artifact_name: str = "runtime-executor-result.json") -> dict:
    runtime_dir = Path(contract["output_file"]).resolve().parent
    if contract.get("kind") == "shell_command":
        cmd = [
            sys.executable,
            str(base / "polaris_adapter_shell.py"),
            "--command", contract["shell_command"],
            "--cwd", contract.get("shell_cwd", "."),
            "--timeout-ms", str(contract.get("shell_timeout_ms", 60000)),
            "--output", contract["output_file"],
            "--goal", contract.get("goal", ""),
            "--adapter", contract.get("adapter", "shell-command"),
            "--experience-hints-json", json.dumps(contract.get("experience_hints", {}), sort_keys=True),
            "--applied-rules-json", json.dumps([{"rule_id": rid} for rid in contract.get("applied_rule_ids", [])], sort_keys=True),
            "--selected-pattern-json", json.dumps({"pattern_id": contract.get("selected_pattern")} if contract.get("selected_pattern") else {}, sort_keys=True),
            "--execution-contract-json", json.dumps({"strategy": contract.get("strategy", {}), "kind": "shell_command"}, sort_keys=True),
        ]
        result = run(cmd)
        # Also write executor result for consistency
        executor_path = runtime_dir / artifact_name
        executor_path.parent.mkdir(parents=True, exist_ok=True)
        executor_payload = {
            "status": "ok" if result["returncode"] == 0 else "failed",
            "adapter": contract.get("adapter", "shell-command"),
            "contract_kind": "shell_command",
            "rendered_command": contract["shell_command"],
            "returncode": result["returncode"],
            "stdout": result.get("stdout", "").strip(),
            "stderr": result.get("stderr", "").strip(),
            "output_file": contract["output_file"],
        }
        executor_path.write_text(json.dumps(executor_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if result["returncode"] == 0 and result.get("stdout"):
            try:
                result["parsed"] = json.loads(result["stdout"])
            except json.JSONDecodeError:
                pass
        return result
    return run_json_checked(
        [
            sys.executable,
            str(base / "polaris_executor.py"),
            "execute",
            "--adapter-json",
            json.dumps(adapter, sort_keys=True),
            "--contract-json",
            json.dumps(contract, sort_keys=True),
            "--write-result",
            str(runtime_dir / artifact_name),
        ],
        "execute contract",
    )


def validate_contract(base: Path, contract: dict, execution_result: dict, artifact_name: str = "runtime-validation-result.json") -> dict:
    runtime_dir = Path(contract["output_file"]).resolve().parent
    return run_json_checked(
        [
            sys.executable,
            str(base / "polaris_validator.py"),
            "validate",
            "--contract-json",
            json.dumps(contract, sort_keys=True),
            "--execution-result-json",
            json.dumps(execution_result, sort_keys=True),
            "--write-result",
            str(runtime_dir / artifact_name),
        ],
        "validate execution result",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Polaris local orchestration flow.")
    parser.add_argument("--state", required=True)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--simulate-error")
    parser.add_argument("--resumed-simulate-error")
    parser.add_argument("--adapters", required=True)
    parser.add_argument("--rules", required=True)
    parser.add_argument("--patterns", required=True)
    parser.add_argument("--mode", choices=["short", "long"], default="long")
    parser.add_argument("--execution-profile", choices=["auto", "micro", "standard", "deep"], default="auto")
    parser.add_argument("--state-density", choices=["auto", "minimal", "full"], default="auto")
    parser.add_argument("--execution-kind", choices=["auto", "runner", "file_transform", "command_output", "file_analysis", "shell_command"], default="auto")
    parser.add_argument("--shell-command")
    parser.add_argument("--shell-cwd")
    parser.add_argument("--shell-timeout-ms", type=int, default=60000)
    parser.add_argument("--analysis-target")
    parser.add_argument("--resume", action="store_true", default=False)
    args = parser.parse_args()

    base = Path(__file__).resolve().parent
    runtime_dir_for_gate = Path(args.state).resolve().parent
    # ── Defense-in-depth compatibility gate (primary gate is in wrapper) ──
    gate_result = subprocess.run(
        [sys.executable, str(base / "polaris_compat.py"), "check-runtime-format", "--runtime-dir", str(runtime_dir_for_gate)],
        capture_output=True, text=True,
    )
    if gate_result.returncode != 0:
        print(gate_result.stderr.strip(), file=sys.stderr)
        raise SystemExit(1)
    schema_gate = subprocess.run(
        [sys.executable, str(base / "polaris_compat.py"), "check-schema", "--state", args.state],
        capture_output=True, text=True,
    )
    if schema_gate.returncode != 0:
        print(schema_gate.stderr.strip(), file=sys.stderr)
        raise SystemExit(1)
    state_path = Path(args.state)
    resuming = False
    fresh_state = not state_path.exists()
    if not fresh_state:
        prior_state = json.loads(state_path.read_text())
        prior_status = prior_state.get("status")
        if prior_status == "in_progress":
            print("Refusing to run: existing state has status 'in_progress' (possible concurrent run)", file=sys.stderr)
            raise SystemExit(1)
        if args.resume and prior_status == "blocked" and prior_state.get("state_machine", {}).get("node") == "blocked":
            resuming = True
    run_id = "polaris-orchestrated-run"
    layers = "hard,soft,experimental"
    history = []
    execution_branch = "execution-main"
    repair_branch = "repair-local"
    execution_profile = infer_profile(args.goal, args.mode, args.simulate_error) if args.execution_profile == "auto" else args.execution_profile
    execution_kind = args.execution_kind
    policy = PROFILE_POLICIES[execution_profile]
    if args.execution_kind == "file_analysis":
        effective_capabilities = policy["adapter_capabilities"] + ",file-analysis"
    elif args.execution_kind == "file_transform":
        effective_capabilities = policy["adapter_capabilities"] + ",file-transform"
    elif args.execution_kind == "command_output":
        effective_capabilities = policy["adapter_capabilities"] + ",command-output"
    elif args.execution_kind == "shell_command":
        effective_capabilities = policy["adapter_capabilities"] + ",shell-command"
    elif args.execution_kind == "runner":
        effective_capabilities = policy["adapter_capabilities"] + ",generic-runner"
    else:
        effective_capabilities = policy["adapter_capabilities"] + ",generic-runner"
    policy = {**policy, "mode": args.mode, "adapter_registry": args.adapters, "execution_kind": args.execution_kind, "effective_adapter_capabilities": effective_capabilities}
    state_density = policy["state_density"] if args.state_density == "auto" else args.state_density
    runtime_dir = Path(args.state).resolve().parent
    sticky_cache = str(Path(args.adapters).with_name("adapter-selection-cache.json"))

    # ── Platform 1: blocked fallback state ──
    # Restore attempted_adapters from prior state on resume; empty list for fresh runs.
    fallback_attempted_adapters: list[str] = []
    fallback_hard_stop = False
    if resuming:
        # Resume from blocked: preserve run_id, attempts, artifacts, learning_backlog, compat
        # Use canonical writer (polaris_state.py set) to ensure state_write_count, updated_at, and history compaction are tracked
        new_resumed_count = prior_state.get("compat", {}).get("resumed_count", 0) + 1
        history.append(
            run_checked(
                [
                    sys.executable,
                    str(base / "polaris_state.py"),
                    "set",
                    "--state",
                    args.state,
                    "--status",
                    "in_progress",
                    "--resumed-count",
                    str(new_resumed_count),
                ],
                "resume: set status and increment resumed_count",
            )
        )
        run_id = prior_state.get("run_id", run_id)
        # ── Platform 1: restore fallback state from persisted state ──
        prior_fallback = prior_state.get("fallback_state", {})
        fallback_attempted_adapters = list(prior_fallback.get("attempted_adapters", []))
        # Record the adapter that was blocked (from prior artifacts)
        prior_blocked_adapter = prior_state.get("artifacts", {}).get("selected_adapter")
        if prior_blocked_adapter and prior_blocked_adapter != "none" and prior_blocked_adapter not in fallback_attempted_adapters:
            fallback_attempted_adapters.append(prior_blocked_adapter)
        # Persist the updated attempted_adapters list
        # Loop breaker: use persisted max_fallback_attempts (frozen at first block time)
        persisted_max = int(prior_fallback.get("max_fallback_attempts", 0))
        if persisted_max > 0:
            total_adapter_count = persisted_max
        else:
            # First resume — freeze from registry (will be persisted by fallback-record)
            _registry_for_count = json.loads(Path(args.adapters).read_text())
            total_adapter_count = len(_registry_for_count.get("adapters", []))
        history.append(
            run_checked(
                [
                    sys.executable,
                    str(base / "polaris_state.py"),
                    "fallback-record",
                    "--state",
                    args.state,
                    "--adapter",
                    prior_blocked_adapter or "unknown",
                    "--max-fallback-attempts",
                    str(total_adapter_count),
                ],
                "record blocked adapter in fallback state",
            )
        )
        # Invalidate sticky cache for the blocked adapter
        if prior_blocked_adapter and prior_blocked_adapter != "none":
            append(history, record_adapter_outcome(base, sticky_cache, policy, execution_profile, prior_blocked_adapter, "failure", None))
        # Loop breaker: if attempted >= total adapters, hard stop
        if len(fallback_attempted_adapters) >= total_adapter_count:
            fallback_hard_stop = True
    else:
        history.append(
            run_checked(
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
                ],
                "state init",
            )
        )
    if policy["write_references"]:
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "reference", "--state", args.state, "--kind", "rules", "--value", args.rules, "--label", "layered rules store"], "record rules reference"))
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "reference", "--state", args.state, "--kind", "patterns", "--value", args.patterns, "--label", "success pattern store"], "record patterns reference"))
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "reference", "--state", args.state, "--kind", "adapters", "--value", args.adapters, "--label", "adapter registry"], "record adapters reference"))
    history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "transition", "--state", args.state, "--to", "planning", "--summary", f"Run initialized and routed to the {execution_profile} profile"], "transition to planning"))
    history.append(
        run_checked(
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
            ],
            "planner",
        )
    )

    selected_rules = run_json_checked(
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
        ],
        "select rules",
    )
    # ── Platform 1: hard-stop rule check before fallback attempt ──
    # Only block fallback when the prior block was caused by a hard-stop condition
    # (nonrepair denial), not merely because a stop rule exists in the store.
    if resuming and fallback_attempted_adapters:
        _prior_block_info = prior_state.get("state_machine", {}).get("blocked", {})
        # Platform 1: read explicit nonrepair_stop boolean — no keyword heuristics
        _nonrepair_blocked = _prior_block_info.get("nonrepair_stop", False)
        _hard_stop_triggered = _nonrepair_blocked
        if _hard_stop_triggered or fallback_hard_stop:
            _stop_reason = "hard-stop rule matched (nonrepair denial)" if _hard_stop_triggered else f"all {len(fallback_attempted_adapters)} adapters exhausted"
            _block_reason = f"Fallback blocked: {_stop_reason}"
            history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "block", "--state", args.state, "--reason", _block_reason, "--references", "", "--nonrepair-stop", "true" if _hard_stop_triggered else "false"], "hard stop block state"))
            history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "set", "--state", args.state, "--status", "blocked", "--progress-pct", "0", "--current-step", "Hard stop", "--next-action", "Manual intervention required", "--phase", "blocked", "--summary-outcome", _block_reason], "hard stop on fallback"))
            append(history, emit_progress(base, policy, "complete", run_id, "blocked", "blocked", _block_reason, 0, "Hard stop", "Manual intervention required", "blocked", layers, None, None, _block_reason, args.state, output_mode="operator_summary"))
            append(history, emit_runtime_surface(base, policy, "complete", args.state, "blocked"))
            print(json.dumps({"status": "blocked", "fallback_hard_stop": True, "reason": _stop_reason, "attempted_adapters": fallback_attempted_adapters, "history": history}, indent=2, sort_keys=True))
            return
    adapter_select_cmd = [
        sys.executable,
        str(base / "polaris_adapters.py"),
        "select",
        "--registry",
        args.adapters,
        "--capabilities",
        policy["effective_adapter_capabilities"],
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
    # Platform 1: exclude already-attempted adapters on fallback resume
    if fallback_attempted_adapters:
        adapter_select_cmd.extend(["--exclude-adapters", ",".join(fallback_attempted_adapters)])
    selected_adapter = run_json_checked(adapter_select_cmd, "select adapter")
    adapter_name = None
    adapter_score = None
    adapter_attempt_count = 1
    adapter_selection = selected_adapter.get("parsed", {}).get("selected", [])
    if adapter_selection:
        adapter_name = adapter_selection[0]["adapter"]["tool"]
        adapter_score = adapter_selection[0].get("score")
    elif fallback_attempted_adapters:
        # Platform 1: all adapters exhausted during fallback — hard stop
        _exhaust_reason = f"All adapters exhausted after {len(fallback_attempted_adapters)} attempts"
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "block", "--state", args.state, "--reason", _exhaust_reason, "--references", "", "--nonrepair-stop", "false"], "adapter exhaustion block state"))
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "set", "--state", args.state, "--status", "blocked", "--progress-pct", "0", "--current-step", "Hard stop", "--next-action", "Manual intervention required", "--phase", "blocked", "--summary-outcome", _exhaust_reason], "adapter exhaustion hard stop"))
        append(history, emit_progress(base, policy, "complete", run_id, "blocked", "blocked", _exhaust_reason, 0, "Hard stop", "Manual intervention required", "blocked", layers, None, None, _exhaust_reason, args.state, output_mode="operator_summary"))
        append(history, emit_runtime_surface(base, policy, "complete", args.state, "blocked"))
        print(json.dumps({"status": "blocked", "fallback_hard_stop": True, "reason": "adapter_exhaustion", "attempted_adapters": fallback_attempted_adapters, "history": history}, indent=2, sort_keys=True))
        return
    else:
        raise SystemExit("no eligible adapter selected")
    sticky_entry = selected_adapter.get("parsed", {}).get("selection_trace", {}).get("sticky_reuse", {}).get("entry", {})
    if sticky_entry:
        adapter_attempt_count = int(sticky_entry.get("failure_count", 0)) + 1

    selected_patterns = {"selected": [], "selection_trace": {"skipped": True}}
    pattern_name = None
    selected_pattern_record = None
    family_transfer_applied = False
    transfer_key = f"{execution_profile}:{args.mode}:{adapter_name or 'none'}:{execution_kind}"
    transfer_source_pattern = None
    transfer_reason = None
    if policy["select_patterns"]:
        # ── Platform 1: fingerprint-aware two-level pattern selection ──
        # Build a task_fingerprint early for the selector even for non-shell tasks
        selector_fp_json = ""
        shell_cmd_early = getattr(args, "shell_command", None)
        shell_cwd_early = getattr(args, "shell_cwd", None) or str(runtime_dir)
        if shell_cmd_early:
            import polaris_task_fingerprint as ptf
            selector_fp = ptf.compute(shell_cmd_early, shell_cwd_early)
            selector_fp_json = json.dumps(selector_fp, sort_keys=True)
        select_cmd = [
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
        if selector_fp_json:
            select_cmd.extend(["--task-fingerprint-json", selector_fp_json])
        selected_patterns = run_json_checked(select_cmd, "select patterns")
        match_resolution = selected_patterns.get("parsed", {}).get("match_resolution", "no_hit")
        top_pattern = selected_patterns.get("parsed", {}).get("selected", [])
        selected_pattern_record = top_pattern[0]["pattern"] if top_pattern else None
        pattern_name = selected_pattern_record["pattern_id"] if selected_pattern_record else None
        # family_transfer_applied only when actual family fallback was used
        if fresh_state and selected_pattern_record is not None and match_resolution == "family_fallback":
            family_transfer_applied = True
            transfer_source_pattern = selected_pattern_record.get("pattern_id")
            transfer_reason = f"fresh task used family-fallback pattern {transfer_source_pattern} (no strict fingerprint hit)"

    applied_rules = applied_rules_payload(selected_rules)
    history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "apply-rules", "--state", args.state, "--rules-json", json.dumps(applied_rules, sort_keys=True)], "apply rules to state"))
    history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "selected_adapter", "--value", adapter_name or "none"], "record selected adapter"))
    if pattern_name:
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "selected_pattern", "--value", pattern_name], "record selected pattern"))
    history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "family_transfer_applied", "--value", json.dumps(family_transfer_applied)], "record family transfer applied flag"))
    history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "transfer_key", "--value", transfer_key], "record transfer key"))
    if transfer_source_pattern:
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "transfer_source_pattern", "--value", transfer_source_pattern], "record transfer source pattern"))
    if transfer_reason:
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "transfer_reason", "--value", transfer_reason], "record transfer reason"))
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
    history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "heartbeat", "--state", args.state, "--summary", "planning surfaces updated"], "planning heartbeat"))
    if policy["surface_keys"]:
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "surface", "--state", args.state, "--kind", "live_status", "--value", str(runtime_dir / "runtime-live-status.json")], "register live status surface"))
    append(history, emit_runtime_surface(base, policy, "planning", args.state, "planning"))
    history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "plan-step", "--state", args.state, "--phase", "planning", "--status", "completed"], "complete planning step"))

    if execution_profile == "micro":
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "branch", "--state", args.state, "--branch-id", execution_branch, "--label", "Primary execution path", "--kind", "primary", "--summary", "Bounded local execution branch opened", "--references", args.adapters], "open micro execution branch"))
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "transition", "--state", args.state, "--to", "executing", "--summary", "Micro profile moved directly into execution", "--branch-id", execution_branch], "transition micro execute"))
    else:
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "transition", "--state", args.state, "--to", "ready", "--summary", "Plan and adapter routing completed"], "transition ready"))
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "plan-step", "--state", args.state, "--phase", "ready", "--status", "in_progress"], "start ready step"))
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "branch", "--state", args.state, "--branch-id", execution_branch, "--label", "Primary execution path", "--kind", "primary", "--summary", "Main local execution branch opened", "--references", args.adapters + "," + args.rules], "open execution branch"))
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "plan-step", "--state", args.state, "--phase", "ready", "--status", "completed"], "complete ready step"))
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "transition", "--state", args.state, "--to", "executing", "--summary", "Execution branch started", "--branch-id", execution_branch], "transition execute"))

    history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "plan-step", "--state", args.state, "--phase", "executing", "--status", "in_progress"], "start executing step"))
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
    history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "heartbeat", "--state", args.state, "--summary", "execution surfaces updated"], "execution heartbeat"))
    append(history, emit_runtime_surface(base, policy, "execution", args.state, "execution"))

    adapter_record = adapter_selection[0]["adapter"] if adapter_selection else {"tool": adapter_name or "none", "command": "bash -lc <command>", "inputs": ["command"]}
    # Read plan step requires for capability check
    current_state = json.loads(Path(args.state).read_text()) if Path(args.state).exists() else {}
    executing_step = next((s for s in current_state.get("plan", []) if s.get("phase") == "executing" and s.get("status") in ("in_progress", "pending")), None)
    plan_requires = executing_step.get("requires") if executing_step else None
    execution_plan = choose_execution_kind(base, args.execution_kind, adapter_record, applied_rules, selected_pattern_record, args.simulate_error, plan_requires)
    history.append(execution_plan)
    execution_kind = execution_plan.get("parsed", {}).get("family", "runner")
    history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "execution_kind", "--value", execution_kind], "record execution kind"))
    history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "execution_family_trace", "--value", json.dumps(execution_plan.get("parsed", {}).get("trace", {}), sort_keys=True)], "record execution family trace"))
    # ── Experience hints assembly (Phase 1: L2 path pruning) ──
    experience_hints = {"prefer": [], "avoid": []}
    task_fingerprint = None
    shell_cmd = getattr(args, "shell_command", None)
    shell_cwd = getattr(args, "shell_cwd", None) or str(runtime_dir)
    shell_timeout_ms = getattr(args, "shell_timeout_ms", 60000)
    if execution_kind == "shell_command" and shell_cmd:
        import polaris_task_fingerprint as ptf
        import polaris_failure_records as pfr
        task_fingerprint = ptf.compute(shell_cmd, shell_cwd)
        # Query failure records for avoidance hints
        failure_store_path = Path(args.patterns).parent / "failure-records.json"
        failure_store = pfr.load_store(failure_store_path)
        failure_matches = pfr.query(failure_store, task_fingerprint)
        avoid_hints = pfr.build_avoidance_hints(failure_matches)
        experience_hints["avoid"] = avoid_hints
        # Query success patterns for prefer hints
        if selected_pattern_record:
            strategy_hints = selected_pattern_record.get("strategy_hints", {})
            for hint in strategy_hints.get("experience_hints_prefer", []):
                if hint.get("kind") in {"append_flags", "set_env", "rewrite_cwd", "set_timeout"}:
                    experience_hints["prefer"].append(hint)
        # Filter hints to adapter's supported kinds
        adapter_supported = set(adapter_record.get("supported_hint_kinds", ["append_flags", "set_env", "rewrite_cwd", "set_timeout"]))
        experience_hints["prefer"] = [h for h in experience_hints["prefer"] if h.get("kind") in adapter_supported]
        experience_hints["avoid"] = [h for h in experience_hints["avoid"] if h.get("kind") in adapter_supported]
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "task_fingerprint", "--value", json.dumps(task_fingerprint, sort_keys=True)], "record task fingerprint"))
        if experience_hints["prefer"] or experience_hints["avoid"]:
            history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "experience_hints", "--value", json.dumps(experience_hints, sort_keys=True)], "record experience hints"))

    extra_contract_args = {}
    if execution_kind == "shell_command":
        extra_contract_args = {
            "shell_command": shell_cmd or args.goal,
            "shell_cwd": shell_cwd,
            "shell_timeout_ms": shell_timeout_ms,
            "experience_hints": experience_hints,
        }
    baseline_contract = build_execution_contract(base, args.goal, args.state, adapter_record, execution_profile, args.mode, [rule for rule in applied_rules if rule.get("layer") == "hard"], None, args.simulate_error, execution_kind, analysis_target=getattr(args, "analysis_target", None), **extra_contract_args)
    execution_contract = build_execution_contract(base, args.goal, args.state, adapter_record, execution_profile, args.mode, applied_rules, selected_pattern_record, args.simulate_error, execution_kind, analysis_target=getattr(args, "analysis_target", None), **extra_contract_args)
    contract_diff = build_contract_diff(summarize_contract_for_diff(baseline_contract), summarize_contract_for_diff(execution_contract))
    validator_diff = build_contract_diff(baseline_contract.get("validator", {}), execution_contract.get("validator", {}))
    transfer_contract_diff = contract_diff if family_transfer_applied else {}
    resumed_after_repair = False
    repair_probe_steps = 0
    history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "baseline_execution_contract", "--value", json.dumps(baseline_contract, sort_keys=True)], "record baseline execution contract"))
    history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "execution_contract_diff", "--value", json.dumps(contract_diff, sort_keys=True)], "record execution contract diff"))
    history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "transfer_contract_diff", "--value", json.dumps(transfer_contract_diff, sort_keys=True)], "record transfer contract diff"))
    history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "baseline_validator", "--value", json.dumps(baseline_contract.get("validator", {}), sort_keys=True)], "record baseline validator"))
    history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "validator_diff", "--value", json.dumps(validator_diff, sort_keys=True)], "record validator diff"))
    history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "execution_contract", "--value", json.dumps(execution_contract, sort_keys=True)], "record execution contract"))
    # ── Platform 1: Hot path budget check before adapter invocation ──
    _budget_pattern_json = json.dumps(selected_pattern_record or {}, sort_keys=True)
    _budget_contract_json = json.dumps(execution_contract, sort_keys=True)
    _budget_rules_json = json.dumps(applied_rules, sort_keys=True)
    _budget_hints_json = json.dumps(experience_hints, sort_keys=True)
    budget_report = hot_path_budget_check(_budget_pattern_json, _budget_contract_json, _budget_rules_json, _budget_hints_json)
    if budget_report["warn"] or budget_report["exceeded"]:
        import sys as _sys
        _budget_level = "EXCEEDED" if budget_report["exceeded"] else "WARNING"
        print(f"[polaris] hot-path budget {_budget_level}: {budget_report['total_bytes']} bytes (warn={HOT_PATH_BUDGET_WARN}, hard={HOT_PATH_BUDGET_HARD})", file=_sys.stderr)
    history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "hot_path_budget", "--value", json.dumps(budget_report, sort_keys=True)], "record hot path budget"))
    execution_result = execute_contract(base, adapter_record, execution_contract)
    history.append(execution_result)
    history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "execution_result", "--value", execution_contract.get("output_file", "")], "record execution result artifact"))
    history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "executor_result", "--value", "runtime-executor-result.json"], "record executor result artifact"))

    validation_result = validate_contract(base, execution_contract, execution_result.get("parsed", execution_result))
    history.append(validation_result)
    history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "validation_result", "--value", "runtime-validation-result.json"], "record validation result artifact"))
    execution_ok = validation_result.get("parsed", {}).get("status") == "ok"
    execution_validation_error = validation_result.get("parsed", {}).get("reason")
    execution_payload = validation_result.get("parsed", {}).get("payload")
    execution_error = None
    # For shell_command, the adapter process returncode is at top level, not in parsed;
    # for other kinds, the executor embeds returncode in parsed output.
    exec_rc = execution_result.get("returncode", 0) if execution_kind == "shell_command" else execution_result.get("parsed", {}).get("returncode", 0)
    if exec_rc != 0 or not execution_ok:
        execution_error = execution_result.get("parsed", {}).get("stderr") or execution_result.get("stderr") or execution_result.get("parsed", {}).get("stdout") or execution_validation_error or args.simulate_error or "execution failed"
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "attempt", "--state", args.state, "--step", "execute_adapter_contract", "--status", "failed", "--summary", execution_error, "--evidence", execution_contract.get("output_file", ""), "--branch-id", execution_branch], "record execution failure attempt"))
        # ── Record failure to failure store (Phase 1: L2 experience) ──
        if execution_kind == "shell_command" and task_fingerprint:
            import polaris_failure_records as pfr
            import polaris_repair as pr
            failure_classification = pr.classify(execution_error)
            error_class = failure_classification.get("failure_type", "unknown")
            repair_class = failure_classification.get("repair_class", "unknown")
            # Build avoidance hints from the failure
            avoidance_hints = _build_failure_avoidance_hints(execution_error, error_class, shell_cmd or args.goal)
            failure_store_path = Path(args.patterns).parent / "failure-records.json"
            failure_store = pfr.load_store(failure_store_path)
            pfr.record(failure_store, task_fingerprint, shell_cmd or args.goal, error_class, execution_error[:500], repair_class, avoidance_hints)
            pfr.write_store(failure_store_path, failure_store)
            history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "failure_record_written", "--value", "true"], "record failure record written"))
        repair_report = run_json_checked(
            [
                sys.executable,
                str(base / "polaris_repair.py"),
                "diagnose",
                "--error",
                execution_error,
                "--write-report",
                str(runtime_dir / "runtime-repair-report.json"),
                "--repair-depth",
                policy["repair_depth"],
                "--execution-profile",
                execution_profile,
                "--attempt-count",
                str(adapter_attempt_count),
            ],
            "repair diagnose",
        )
        resolved_repair_depth = repair_report.get("parsed", {}).get("repair_depth", policy["repair_depth"])
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "set", "--state", args.state, "--repair-depth", resolved_repair_depth], "record repair depth"))
        repair_plan = run_json_checked(
            [
                sys.executable,
                str(base / "polaris_repair_actions.py"),
                "plan",
                "--diagnosis-json",
                json.dumps(repair_report.get("parsed", {}), sort_keys=True),
                "--repair-depth",
                resolved_repair_depth,
                "--write-plan",
                str(runtime_dir / "runtime-repair-plan.json"),
            ],
            "repair plan",
        )
        repair_results = run_json_checked([sys.executable, str(base / "polaris_repair_actions.py"), "execute", "--plan", str(runtime_dir / "runtime-repair-plan.json"), "--write-results", str(runtime_dir / "runtime-repair-results.json")], "repair execute")
        repair_probe_steps = len(repair_plan.get("parsed", {}).get("execution_order", []))
        history.extend([repair_report, repair_plan, repair_results])
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "repair_report", "--value", "runtime-repair-report.json"], "record repair report artifact"))
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "repair_plan", "--value", "runtime-repair-plan.json"], "record repair plan artifact"))
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "repair_results", "--value", "runtime-repair-results.json"], "record repair results artifact"))

        if execution_profile != "deep":
            repair_learning = build_repair_learning_items(repair_report, resolved_repair_depth, execution_profile, args.mode, adapter_name)
            if repair_learning is not None:
                rule_candidate, repair_marker = repair_learning
                history.append(queue_learning_item(base, args.state, "rule_candidate", rule_candidate))
                history.append(queue_learning_item(base, args.state, "success_marker", repair_marker))
            next_action = stop_action(applied_rules, repair_report)
            blocked_reason = repair_report.get("parsed", {}).get("retry_guidance") if repair_report.get("parsed", {}).get("nonrepair_stop") else f"{execution_profile.title()} profile stopped after {resolved_repair_depth} repair; escalate to {repair_report.get('parsed', {}).get('next_depth') or 'deep'} only if failure repeats"
            history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "transition", "--state", args.state, "--to", "repairing", "--summary", f"{execution_profile.title()} profile opened a {resolved_repair_depth} repair pass", "--branch-id", execution_branch], "transition to repairing"))
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
                    next_action,
                    "repairing",
                    layers,
                    adapter_name,
                    execution_branch,
                    execution_error,
                    args.state,
                    output_mode="operator_summary",
                ),
            )
            _is_nonrepair_stop = "true" if repair_report.get("parsed", {}).get("nonrepair_stop") else "false"
            history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "block", "--state", args.state, "--reason", blocked_reason, "--references", "runtime-repair-report.json,runtime-repair-plan.json,runtime-repair-results.json", "--nonrepair-stop", _is_nonrepair_stop], "record blocked state"))
            history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "set", "--state", args.state, "--status", "blocked", "--progress-pct", "60", "--current-step", "Blocked after bounded repair", "--next-action", next_action, "--phase", "blocked", "--summary-outcome", blocked_reason], "set blocked summary"))
            blocked_backlog_state = json.loads(Path(args.state).read_text())
            blocked_backlog_items = blocked_backlog_state.get("learning_backlog", [])
            blocked_summary = None
            if blocked_backlog_items:
                blocked_results, retained_items, blocked_summary = consolidate_backlog(base, args.state, args.patterns, args.rules, blocked_backlog_items)
                for result in blocked_results:
                    append(history, result)
                history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "heartbeat", "--state", args.state, "--summary", f"deferred repair learning consolidated: {blocked_summary['processed_items']}/{blocked_summary['queued_items']} item(s); retained={blocked_summary['retained_items']}; pattern promotions={len(blocked_summary['promoted_patterns'])}; rule promotions={len(blocked_summary['promoted_rules'])}"], "blocked learning heartbeat"))
            blocked_state = json.loads(Path(args.state).read_text())
            history.append(persist_efficiency_metrics(base, args.state, runtime_dir, build_runtime_efficiency_metrics(blocked_state, execution_contract, execution_payload, False, repair_probe_steps, family_transfer_applied)))
            append(history, record_adapter_outcome(base, sticky_cache, policy, execution_profile, adapter_name, "failure", adapter_score))
            # ── Platform 1: record blocked adapter in fallback state for future resume ──
            # Freeze max_fallback_attempts from registry at first block; reuse persisted value on subsequent blocks
            _existing_fb = blocked_state.get("fallback_state", {})
            _persisted_max_fb = int(_existing_fb.get("max_fallback_attempts", 0))
            if _persisted_max_fb > 0:
                _total_adapters_fb = _persisted_max_fb
            else:
                _registry_for_fb = json.loads(Path(args.adapters).read_text())
                _total_adapters_fb = len(_registry_for_fb.get("adapters", []))
            history.append(
                run_checked(
                    [
                        sys.executable,
                        str(base / "polaris_state.py"),
                        "fallback-record",
                        "--state",
                        args.state,
                        "--adapter",
                        adapter_name or "unknown",
                        "--max-fallback-attempts",
                        str(_total_adapters_fb),
                    ],
                    "record blocked adapter for fallback",
                )
            )
            append(history, emit_runtime_surface(base, policy, "complete", args.state, "blocked"))
            print(
                json.dumps(
                    {
                        "status": "blocked",
                        "execution_profile": execution_profile,
                        "selected_rules": selected_rules.get("parsed", {}),
                        "selected_adapter": selected_adapter.get("parsed", {}),
                        "selected_patterns": selected_patterns.get("parsed", selected_patterns),
                        "attempted_adapters": fallback_attempted_adapters + ([adapter_name] if adapter_name and adapter_name not in fallback_attempted_adapters else []),
                        "history": history,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return

        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "branch", "--state", args.state, "--branch-id", repair_branch, "--label", "Local repair branch", "--kind", "repair", "--summary", "Execution failure triggered repair branch", "--references", "runtime-repair-report.json,runtime-repair-plan.json,runtime-repair-results.json"], "open repair branch"))
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "transition", "--state", args.state, "--to", "repairing", "--summary", "Execution failure triggered repair branch", "--branch-id", repair_branch], "transition deep repair"))
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
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "heartbeat", "--state", args.state, "--summary", "repair surfaces updated"], "repair heartbeat"))
        append(history, emit_runtime_surface(base, policy, "repair", args.state, "repair"))
        repair_learning = build_repair_learning_items(repair_report, resolved_repair_depth, execution_profile, args.mode, adapter_name)
        if repair_learning is not None:
            rule_candidate, repair_marker = repair_learning
            history.append(queue_learning_item(base, args.state, "rule_candidate", rule_candidate))
            history.append(queue_learning_item(base, args.state, "success_marker", repair_marker))
            history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "success", "--state", args.state, "--pattern-id", repair_marker["pattern_id"], "--summary", "Repair branch queued deferred local recovery learning", "--evidence", "runtime-repair-results.json,runtime-repair-plan.json", "--confidence", str(repair_marker["confidence"])], "record repair learning success"))
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "recover", "--state", args.state, "--branch-id", repair_branch, "--to", "ready", "--summary", "Repair branch completed and run is ready to continue", "--references", "runtime-repair-results.json,runtime-repair-report.json"], "recover from repair"))
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "attempt", "--state", args.state, "--step", "repair_guidance_recorded", "--status", "passed", "--summary", "Repair guidance captured and rule stored", "--evidence", "runtime-repair-results.json", "--branch-id", repair_branch], "record repair attempt"))
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "branch", "--state", args.state, "--branch-id", execution_branch, "--label", "Primary execution path", "--kind", "primary", "--summary", "Execution resumed after repair branch", "--references", args.state], "reopen execution branch"))
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "transition", "--state", args.state, "--to", "executing", "--summary", "Execution resumed after repair branch", "--branch-id", execution_branch], "transition resumed execute"))
        append(history, record_adapter_outcome(base, sticky_cache, policy, execution_profile, adapter_name, "failure", adapter_score))
        resumed_contract = build_execution_contract(base, args.goal, args.state, adapter_record, execution_profile, args.mode, applied_rules, selected_pattern_record, args.resumed_simulate_error, execution_kind, analysis_target=getattr(args, "analysis_target", None))
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "resumed_execution_contract", "--value", json.dumps(resumed_contract, sort_keys=True)], "record resumed execution contract"))
        resumed_result = execute_contract(base, adapter_record, resumed_contract, "runtime-resumed-executor-result.json")
        history.append(resumed_result)
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "execution_result", "--value", resumed_contract.get("output_file", "")], "record resumed execution result artifact"))
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "resumed_executor_result", "--value", "runtime-resumed-executor-result.json"], "record resumed executor result artifact"))
        resumed_validation = validate_contract(base, resumed_contract, resumed_result.get("parsed", resumed_result), "runtime-resumed-validation-result.json")
        history.append(resumed_validation)
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "artifact", "--state", args.state, "--key", "resumed_validation_result", "--value", "runtime-resumed-validation-result.json"], "record resumed validation result artifact"))
        resumed_ok = resumed_validation.get("parsed", {}).get("status") == "ok"
        resumed_validation_error = resumed_validation.get("parsed", {}).get("reason")
        resumed_payload = resumed_validation.get("parsed", {}).get("payload")
        if resumed_result.get("parsed", {}).get("returncode") != 0 or not resumed_ok:
            resumed_error = resumed_result.get("parsed", {}).get("stderr") or resumed_result.get("parsed", {}).get("stdout") or resumed_validation_error or "execution failed after repair"
            history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "attempt", "--state", args.state, "--step", "execute_after_repair", "--status", "failed", "--summary", resumed_error, "--evidence", resumed_contract.get("output_file", ""), "--branch-id", execution_branch], "record resumed execution failure"))
            history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "block", "--state", args.state, "--reason", resumed_error, "--references", "runtime-repair-report.json,runtime-repair-plan.json,runtime-repair-results.json"], "block after failed resumed execution"))
            history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "set", "--state", args.state, "--status", "blocked", "--progress-pct", "70", "--current-step", "Execution failed after repair", "--next-action", "Inspect repaired environment and retry with fresh evidence", "--phase", "blocked", "--summary-outcome", resumed_error], "set resumed blocked summary"))
            resumed_blocked_state = json.loads(Path(args.state).read_text())
            history.append(persist_efficiency_metrics(base, args.state, runtime_dir, build_runtime_efficiency_metrics(resumed_blocked_state, resumed_contract, resumed_payload, True, repair_probe_steps, family_transfer_applied)))
            append(history, emit_runtime_surface(base, policy, "complete", args.state, "blocked"))
            print(json.dumps({"status": "blocked", "execution_profile": execution_profile, "selected_rules": selected_rules.get("parsed", {}), "selected_adapter": selected_adapter.get("parsed", {}), "selected_patterns": selected_patterns.get("parsed", selected_patterns), "history": history}, indent=2, sort_keys=True))
            return
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "attempt", "--state", args.state, "--step", "execute_after_repair", "--status", "passed", "--summary", "Adapter contract executed successfully after repair", "--evidence", resumed_contract.get("output_file", ""), "--branch-id", execution_branch], "record resumed execution success"))
        execution_contract = resumed_contract
        execution_result = resumed_result
        execution_payload = resumed_payload
        execution_error = None
        resumed_after_repair = True

    if execution_error is None and not resumed_after_repair:
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "attempt", "--state", args.state, "--step", "execute_adapter_contract", "--status", "passed", "--summary", "Adapter contract executed successfully", "--evidence", execution_contract.get("output_file", ""), "--branch-id", execution_branch], "record execution success attempt"))
    history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "plan-step", "--state", args.state, "--phase", "executing", "--status", "completed"], "complete executing plan step"))
    history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "transition", "--state", args.state, "--to", "validating", "--summary", "Execution outputs ready for validation", "--branch-id", execution_branch], "transition validating"))
    history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "plan-step", "--state", args.state, "--phase", "validating", "--status", "in_progress"], "start validating step"))
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
    history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "heartbeat", "--state", args.state, "--summary", "validation surfaces updated"], "validation heartbeat"))
    append(history, emit_runtime_surface(base, policy, "validate", args.state, "validating"))
    if execution_profile == "deep":
        deep_success_context = {
            "execution_profile": execution_profile,
            "mode": args.mode,
            "adapter": adapter_name or "none",
            "kind": "foreground-success",
            "durable_status": policy.get("require_durable_status"),
        }
        deep_success_fp = make_fingerprint("deep-success", deep_success_context)
        deep_success_marker = {
            "pattern_id": "layered-local-orchestration",
            "fingerprint": deep_success_fp,
            "summary": "Layered rules plus ranked adapter selection keep runs local, resumable, and auditable",
            "trigger": "long local task",
            "sequence": ["init", "plan", "select-rules", "rank-adapters", "select-patterns", "execute", "validate"],
            "outcome": "resumable orchestration with reviewable state and references",
            "evidence": [args.state, "runtime-status.json", "runtime-events.jsonl"],
            "adapter": adapter_name,
            "tags": ["orchestration", "local", "success"],
            "modes": [args.mode],
            "confidence": 88,
            "lifecycle_state": "experimental",
            "reusable": True,
            "strategy_hints": {
                "fallback_choice": "sticky-adapter-first",
                "validation_strategy": "runner-contract-strict",
                "execution_ordering": ["precheck", "execute", "validate"],
                "hot_path_budget": 3,
            },
        }
        if task_fingerprint:
            deep_success_marker["task_fingerprint"] = task_fingerprint
        history.append(queue_learning_item(base, args.state, "success_marker", deep_success_marker))
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "success", "--state", args.state, "--pattern-id", "layered-local-orchestration", "--summary", "Full run queued a reusable orchestration pattern for deferred consolidation", "--evidence", args.state + ",runtime-status.json", "--confidence", "90"], "record deep success marker"))
    else:
        success_context = {
            "execution_profile": execution_profile,
            "mode": args.mode,
            "adapter": adapter_name or "none",
            "kind": "foreground-success",
        }
        if task_fingerprint:
            success_context["task_fingerprint"] = task_fingerprint
        success_fp = make_fingerprint("success", success_context)
        success_marker = {
            "pattern_id": f"{execution_profile}-local-success-marker-{success_fp}",
            "fingerprint": success_fp,
            "summary": f"{execution_profile.title()} profile finished with light foreground orchestration and deferred learning consolidation",
            "trigger": f"{execution_profile} local task",
            "sequence": ["execute", "validate"],
            "outcome": "task completed locally while keeping heavier learning work off the hot path",
            "evidence": [args.state, "runtime-status.json"],
            "adapter": adapter_name,
            "tags": ["orchestration", "local", execution_profile, "deferred-learning"],
            "modes": [args.mode],
            "confidence": 76 if execution_profile == "standard" else 72,
            "lifecycle_state": "experimental",
            "reusable": True,
            "strategy_hints": {
                "fallback_choice": "sticky-adapter-first",
                "validation_strategy": "runner-contract-strict",
                "execution_ordering": ["execute", "validate"],
                "hot_path_budget": 2,
            },
        }
        if task_fingerprint:
            success_marker["task_fingerprint"] = task_fingerprint
        history.append(queue_learning_item(base, args.state, "success_marker", success_marker))
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "set", "--state", args.state, "--summary-outcome", f"{execution_profile.title()} run validated locally and queued deferred learning capture"], "record deferred success summary"))
    history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "plan-step", "--state", args.state, "--phase", "validating", "--status", "completed"], "complete validating step"))
    if execution_profile != "micro":
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "plan-step", "--state", args.state, "--phase", "completed", "--status", "in_progress"], "start completed step"))
    history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "set", "--state", args.state, "--status", "completed", "--progress-pct", "100", "--current-step", "Completed", "--next-action", "Review outputs", "--phase", "completed", "--active-layers", layers, "--summary-outcome", "Run finished cleanly"], "mark completed state"))
    append(history, record_adapter_outcome(base, sticky_cache, policy, execution_profile, adapter_name, "success", adapter_score))
    if execution_profile != "micro":
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "plan-step", "--state", args.state, "--phase", "completed", "--status", "completed"], "complete final plan step"))
    history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "transition", "--state", args.state, "--to", "completed", "--summary", "Run finished cleanly", "--branch-id", execution_branch], "transition completed"))
    backlog_state = json.loads(Path(args.state).read_text())
    backlog_items = backlog_state.get("learning_backlog", [])
    if backlog_items:
        consolidation_results, retained_items, summary = consolidate_backlog(base, args.state, args.patterns, args.rules, backlog_items)
        for result in consolidation_results:
            append(history, result)
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "heartbeat", "--state", args.state, "--summary", f"deferred learning consolidated: {summary['processed_items']}/{summary['queued_items']} item(s); retained={summary['retained_items']}; pattern promotions={len(summary['promoted_patterns'])}; rule promotions={len(summary['promoted_rules'])}"], "final learning heartbeat"))
    if execution_profile == "deep":
        history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "compact-history", "--state", args.state], "compact history"))
    history.append(run_checked([sys.executable, str(base / "polaris_state.py"), "heartbeat", "--state", args.state, "--summary", "run completed"], "completion heartbeat"))
    completed_state = json.loads(Path(args.state).read_text())
    history.append(persist_efficiency_metrics(base, args.state, runtime_dir, build_runtime_efficiency_metrics(completed_state, execution_contract, execution_payload, resumed_after_repair, repair_probe_steps, family_transfer_applied)))
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
            output_mode="operator_summary",
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
