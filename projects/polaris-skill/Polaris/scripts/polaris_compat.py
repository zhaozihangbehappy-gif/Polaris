#!/usr/bin/env python3
"""Polaris compatibility gate — checks schema and runtime-format versions before any writes."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

CURRENT_SCHEMA_VERSION = 6
READABLE_SCHEMA_VERSIONS = {5, 6}
CURRENT_RUNTIME_FORMAT = 1
COMPATIBLE_RUNTIME_FORMATS = {1}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def check_schema_version(state: dict) -> dict:
    version = state.get("schema_version")
    if version == CURRENT_SCHEMA_VERSION:
        return {"compatible": True, "reason": "current schema", "action": "proceed"}
    if version in READABLE_SCHEMA_VERSIONS:
        return {"compatible": True, "reason": f"upgradeable from v{version}", "action": "upgrade"}
    return {
        "compatible": False,
        "reason": f"schema version {version} is not compatible with this Polaris version (supports: {sorted(READABLE_SCHEMA_VERSIONS)})",
        "action": "refuse",
    }


def check_runtime_format(runtime_dir: Path) -> dict:
    marker = runtime_dir / "runtime-format.json"
    state_file = runtime_dir / "execution-state.json"
    if not marker.exists():
        if state_file.exists():
            return {"compatible": True, "reason": "legacy directory (no marker, state exists)", "action": "upgrade"}
        return {"compatible": True, "reason": "fresh directory", "action": "proceed"}
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"compatible": False, "reason": f"cannot read runtime-format.json: {exc}", "action": "refuse"}
    fmt = data.get("runtime_format")
    if fmt in COMPATIBLE_RUNTIME_FORMATS:
        return {"compatible": True, "reason": f"runtime format {fmt} is compatible", "action": "proceed"}
    return {
        "compatible": False,
        "reason": f"Runtime directory format {fmt} is not compatible with this Polaris version (supports: {sorted(COMPATIBLE_RUNTIME_FORMATS)})",
        "action": "refuse",
    }


def write_runtime_format(runtime_dir: Path) -> dict:
    marker = runtime_dir / "runtime-format.json"
    data = {
        "runtime_format": CURRENT_RUNTIME_FORMAT,
        "created_by": "polaris",
        "schema_version": CURRENT_SCHEMA_VERSION,
        "created_at": now(),
        "min_compatible_schema": min(READABLE_SCHEMA_VERSIONS),
    }
    marker.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Polaris compatibility gate.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_rt = subparsers.add_parser("check-runtime-format")
    check_rt.add_argument("--runtime-dir", required=True)

    check_sc = subparsers.add_parser("check-schema")
    check_sc.add_argument("--state", required=True)

    write_rt = subparsers.add_parser("write-runtime-format")
    write_rt.add_argument("--runtime-dir", required=True)

    args = parser.parse_args()

    if args.command == "check-runtime-format":
        result = check_runtime_format(Path(args.runtime_dir))
        print(json.dumps(result, sort_keys=True))
        if not result["compatible"]:
            print(result["reason"], file=sys.stderr)
            raise SystemExit(1)

    elif args.command == "check-schema":
        state_path = Path(args.state)
        if not state_path.exists():
            print(json.dumps({"compatible": True, "reason": "no state file yet", "action": "proceed"}, sort_keys=True))
            raise SystemExit(0)
        state = json.loads(state_path.read_text(encoding="utf-8"))
        result = check_schema_version(state)
        print(json.dumps(result, sort_keys=True))
        if not result["compatible"]:
            print(result["reason"], file=sys.stderr)
            raise SystemExit(1)

    elif args.command == "write-runtime-format":
        runtime_dir = Path(args.runtime_dir)
        runtime_dir.mkdir(parents=True, exist_ok=True)
        data = write_runtime_format(runtime_dir)
        print(json.dumps(data, sort_keys=True))


if __name__ == "__main__":
    main()
