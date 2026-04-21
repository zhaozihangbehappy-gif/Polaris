#!/usr/bin/env python3
import argparse
import json
import shlex
import subprocess
from pathlib import Path


def render_script_command(adapter: dict, contract: dict) -> str:
    template = adapter.get("command", "")
    script_path = shlex.quote(contract["script_path"])
    rendered = template.replace("<script>.py", script_path).replace("<script>", script_path)
    return rendered + " " + " ".join(shlex.quote(arg) for arg in contract.get("args", []))


def render_command_contract(adapter: dict, contract: dict) -> str:
    template = adapter.get("command", "")
    command = contract.get("command", "")
    if "<command>" in template:
        return template.replace("<command>", shlex.quote(command))
    return command


def render_adapter_command(adapter: dict, contract: dict) -> str:
    kind = contract.get("kind")
    if kind == "script":
        return render_script_command(adapter, contract)
    if kind == "file_transform":
        return render_script_command(adapter, contract)
    if kind == "file_analysis":
        return render_script_command(adapter, contract)
    if kind == "command_output":
        return render_command_contract(adapter, contract)
    return render_command_contract(adapter, contract)


def write_contract_output(contract: dict, proc: subprocess.CompletedProcess[str]) -> None:
    output_file = contract.get("output_file")
    if not output_file:
        return
    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    if contract.get("kind") == "command_output":
        path.write_text(proc.stdout, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute a Polaris execution contract through a selected adapter.")
    parser.add_argument("execute", nargs="?")
    parser.add_argument("--adapter-json", required=True)
    parser.add_argument("--contract-json", required=True)
    parser.add_argument("--write-result")
    args = parser.parse_args()

    adapter = json.loads(args.adapter_json)
    contract = json.loads(args.contract_json)
    rendered_command = render_adapter_command(adapter, contract)
    proc = subprocess.run(["bash", "-lc", rendered_command], capture_output=True, text=True)
    write_contract_output(contract, proc)
    payload = {
        "status": "ok" if proc.returncode == 0 else "failed",
        "adapter": adapter.get("tool"),
        "contract_kind": contract.get("kind"),
        "rendered_command": rendered_command,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "output_file": contract.get("output_file"),
    }
    if args.write_result:
        path = Path(args.write_result)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
