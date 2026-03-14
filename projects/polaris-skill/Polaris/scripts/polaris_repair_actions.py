#!/usr/bin/env python3
import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_shell(command: str) -> dict:
    proc = subprocess.run(command, shell=True, capture_output=True, text=True)
    return {
        "command": command,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def leaf(node_id: str, label: str, command: str) -> dict:
    return {
        "node_id": node_id,
        "kind": "shell",
        "label": label,
        "command": command,
        "reversible": True,
    }


def trim_tree(root: dict, allowed_ids: set[str]) -> dict:
    trimmed = {key: value for key, value in root.items() if key != "children"}
    children = []
    for child in root.get("children", []):
        if child.get("node_id") in allowed_ids:
            children.append(trim_tree(child, allowed_ids))
    if children or "children" in root:
        trimmed["children"] = children
    return trimmed


def action_tree_for(failure_type: str) -> dict:
    if failure_type in {"approval_denial", "permission_denial"}:
        return {
            "root": {
                "node_id": "nonrepair-stop",
                "kind": "stop",
                "label": "Stop at non-repair denial",
                "reason": "This denial is an explicit nonrepair stop, not a repair target.",
                "children": [],
            },
            "execution_order": [],
            "safe_to_execute": False,
        }
    if failure_type == "missing_dependency":
        return {
            "root": {
                "node_id": "dependency-root",
                "kind": "decision",
                "label": "Probe local Python environment before any fix",
                "children": [
                    leaf("python-version", "Capture interpreter version", "python3 --version"),
                    leaf("python-exec", "Capture interpreter path", "python3 -c 'import sys; print(sys.executable)'"),
                    leaf("sys-path", "Capture sys.path head", "python3 -c 'import sys, json; print(json.dumps(sys.path[:6]))'"),
                    leaf("pip-version", "Capture pip presence", "python3 -m pip --version"),
                    leaf("pip-list-head", "Sample installed packages", "python3 -m pip list --format=columns | sed -n '1,8p'"),
                    leaf("venv-detect", "Detect local virtualenv markers", "find . -maxdepth 2 \\( -name pyvenv.cfg -o -name '.venv' -o -name 'venv' \\) | sed -n '1,8p'"),
                ],
            },
            "execution_order": ["python-version", "python-exec", "sys-path", "pip-version", "pip-list-head", "venv-detect"],
            "safe_to_execute": True,
        }
    if failure_type == "missing_tool":
        return {
            "root": {
                "node_id": "tool-root",
                "kind": "decision",
                "label": "Probe PATH and tool resolution",
                "children": [
                    leaf("path-value", "Capture PATH", 'printf "%s\n" "$PATH"'),
                    leaf("python-resolution", "Resolve likely substitute tool", "command -v python3 || which python3 || true"),
                    leaf("shell-resolution", "Resolve shell", "command -v bash || true"),
                    leaf("tool-candidates", "List nearby executable files", "find . -maxdepth 2 -type f -perm -111 | sed -n '1,12p'"),
                ],
            },
            "execution_order": ["path-value", "python-resolution", "shell-resolution", "tool-candidates"],
            "safe_to_execute": True,
        }
    if failure_type == "import_path_issue":
        return {
            "root": {
                "node_id": "import-root",
                "kind": "decision",
                "label": "Inspect interpreter import path and local package layout",
                "children": [
                    leaf("pwd", "Capture working directory", "pwd"),
                    leaf("sys-path", "Capture sys.path head", "python3 -c 'import sys, json; print(json.dumps(sys.path[:8]))'"),
                    leaf("py-files", "List nearby Python packages", "find . -maxdepth 3 \\( -name '__init__.py' -o -name '*.py' \\) | sed -n '1,16p'"),
                ],
            },
            "execution_order": ["pwd", "sys-path", "py-files"],
            "safe_to_execute": True,
        }
    if failure_type == "config_parse_error":
        return {
            "root": {
                "node_id": "config-root",
                "kind": "decision",
                "label": "Inspect local config candidates before editing",
                "children": [
                    leaf("config-files", "List nearby config files", "find . -maxdepth 3 \\( -name '*.json' -o -name '*.toml' -o -name '*.yaml' -o -name '*.yml' -o -name '*.ini' \\) | sed -n '1,16p'"),
                    leaf("package-config", "Inspect package/project config", "find . -maxdepth 2 \\( -name 'pyproject.toml' -o -name 'package.json' -o -name 'setup.cfg' \\) | sed -n '1,8p'"),
                    leaf("json-validate", "Validate JSON files locally", "find . -maxdepth 2 -name '*.json' -print0 | xargs -0 -r -n1 python3 -m json.tool >/dev/null"),
                ],
            },
            "execution_order": ["config-files", "package-config", "json-validate"],
            "safe_to_execute": True,
        }
    if failure_type == "test_failure":
        return {
            "root": {
                "node_id": "test-root",
                "kind": "decision",
                "label": "Collect local test and repository evidence",
                "children": [
                    leaf("pwd", "Capture working directory", "pwd"),
                    leaf("tests", "List nearby test files", "find . -maxdepth 3 \\( -name 'test_*.py' -o -name '*_test.py' -o -path './tests/*' \\) | sed -n '1,16p'"),
                    leaf("git-status", "Inspect local modifications", "git status --short || true"),
                    leaf("test-config", "Inspect test config files", "find . -maxdepth 2 \\( -name 'pytest.ini' -o -name 'tox.ini' -o -name 'conftest.py' \\) | sed -n '1,12p'"),
                ],
            },
            "execution_order": ["pwd", "tests", "git-status", "test-config"],
            "safe_to_execute": True,
        }
    if failure_type == "path_or_missing_file":
        return {
            "root": {
                "node_id": "path-root",
                "kind": "decision",
                "label": "Verify local working directory and nearby files",
                "children": [
                    leaf("pwd", "Capture working directory", "pwd"),
                    leaf("ls-root", "List current directory", "ls -la"),
                    leaf("ls-parent", "List parent directory", "ls -la .."),
                    leaf("find-targets", "List nearby candidate files", "find . -maxdepth 3 -type f | sed -n '1,20p'"),
                ],
            },
            "execution_order": ["pwd", "ls-root", "ls-parent", "find-targets"],
            "safe_to_execute": True,
        }
    return {
        "root": {
            "node_id": "generic-root",
            "kind": "decision",
            "label": "Collect minimal local evidence",
            "children": [
                leaf("pwd", "Capture working directory", "pwd"),
                leaf("ls-root", "List current directory", "ls -la"),
                leaf("python-version", "Capture interpreter version", "python3 --version || true"),
                leaf("git-status", "Inspect local repo status", "git status --short || true"),
            ],
        },
        "execution_order": ["pwd", "ls-root", "python-version", "git-status"],
        "safe_to_execute": True,
    }


def build_plan(error_text: str, repair_depth: str = "deep") -> dict:
    text = error_text.lower()
    if "approval" in text or "policy" in text or "sandbox" in text:
        failure_type = "approval_denial"
        notes = "Stop. This is an explicit nonrepair stop, not a repair target."
        nonrepair_stop = True
        recommended_tree = "nonrepair_stop"
    elif "no module named" in text or "module not found" in text:
        failure_type = "missing_dependency"
        notes = "Local-only probes first; installation stays outside automatic repair."
        nonrepair_stop = False
        recommended_tree = "dependency_probe_tree"
    elif "command not found" in text:
        failure_type = "missing_tool"
        notes = "Probe resolution and PATH before suggesting substitution."
        nonrepair_stop = False
        recommended_tree = "tool_probe_tree"
    elif "permission denied" in text or "operation not permitted" in text:
        failure_type = "permission_denial"
        notes = "Stop. This is an explicit nonrepair stop, not a repair target."
        nonrepair_stop = True
        recommended_tree = "nonrepair_stop"
    elif "no such file or directory" in text or "cannot find the file" in text:
        failure_type = "path_or_missing_file"
        notes = "Verify workdir and nearby files before creating or changing anything."
        nonrepair_stop = False
        recommended_tree = "path_probe_tree"
    else:
        failure_type = "unknown"
        notes = "Collect bounded local evidence before retrying."
        nonrepair_stop = False
        recommended_tree = "generic_probe_tree"
    diagnosis = {
        "failure_type": failure_type,
        "repair_depth": repair_depth,
        "retry_guidance": notes,
        "recommended_tree": recommended_tree,
        "nonrepair_stop": nonrepair_stop,
    }
    return build_plan_from_diagnosis(diagnosis)


def build_plan_from_diagnosis(diagnosis: dict) -> dict:
    failure_type = diagnosis.get("failure_type", "unknown")
    repair_depth = diagnosis.get("repair_depth", "deep")
    tree = action_tree_for(failure_type)
    if diagnosis.get("nonrepair_stop"):
        tree = {
            "root": {
                "node_id": "nonrepair-stop",
                "kind": "stop",
                "label": "Stop at nonrepair stop",
                "reason": diagnosis.get("retry_guidance") or "This failure is not a repair target.",
                "children": [],
            },
            "execution_order": [],
            "safe_to_execute": False,
        }
    if tree["safe_to_execute"]:
        budget = {"shallow": 2, "medium": 4, "deep": len(tree["execution_order"])}[repair_depth]
        execution_order = tree["execution_order"][:budget]
        action_tree = trim_tree(tree["root"], set(execution_order))
    else:
        execution_order = []
        action_tree = tree["root"]
    return {
        "failure_type": failure_type,
        "repair_depth": repair_depth,
        "notes": diagnosis.get("retry_guidance") or "Collect bounded local evidence before retrying.",
        "safe_to_execute": tree["safe_to_execute"],
        "action_tree": action_tree,
        "execution_order": execution_order,
        "probe_budget": len(execution_order),
        "policy": "local-only reversible probes or explicit stop",
        "recommended_tree": diagnosis.get("recommended_tree"),
        "nonrepair_stop": diagnosis.get("nonrepair_stop", False),
    }


def flatten_nodes(node: dict) -> dict:
    mapping = {node["node_id"]: node}
    for child in node.get("children", []):
        mapping.update(flatten_nodes(child))
    return mapping


def main() -> None:
    parser = argparse.ArgumentParser(description="Create and optionally execute Polaris repair actions.")
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan")
    plan.add_argument("--error")
    plan.add_argument("--diagnosis-json")
    plan.add_argument("--write-plan")
    plan.add_argument("--repair-depth", choices=["shallow", "medium", "deep"], default="deep")

    execute = sub.add_parser("execute")
    execute.add_argument("--plan", required=True)
    execute.add_argument("--write-results")

    args = parser.parse_args()

    if args.command == "plan":
        if args.diagnosis_json:
            diagnosis = json.loads(args.diagnosis_json)
            payload = build_plan_from_diagnosis(diagnosis)
            payload["error"] = diagnosis.get("evidence", [None])[0]
        else:
            payload = build_plan(args.error or "", args.repair_depth)
            payload["error"] = args.error
        payload["created_at"] = now()
        if args.write_plan:
            Path(args.write_plan).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(payload, sort_keys=True))
        return

    plan_data = json.loads(Path(args.plan).read_text())
    results = {
        "executed_at": now(),
        "failure_type": plan_data.get("failure_type"),
        "safe_to_execute": plan_data.get("safe_to_execute", False),
        "results": [],
    }
    if not plan_data.get("safe_to_execute", False):
        results["results"].append(
            {
                "action": None,
                "outcome": {
                    "returncode": None,
                    "stdout": "",
                    "stderr": "",
                    "note": "Execution skipped because the plan is not safe to run automatically.",
                },
            }
        )
    else:
        nodes = flatten_nodes(plan_data["action_tree"])
        for node_id in plan_data.get("execution_order", []):
            node = nodes[node_id]
            outcome = run_shell(node["command"]) if node.get("kind") == "shell" else {"note": "non-executable node"}
            results["results"].append({"action": node, "outcome": outcome})
    if args.write_results:
        Path(args.write_results).write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(results, sort_keys=True))


if __name__ == "__main__":
    main()
