#!/usr/bin/env python3
"""Dedicated failure experience store for Polaris L2 path pruning.

Failure records are separate from success patterns. The orchestrator queries
both stores and assembles experience_hints: { prefer: [...], avoid: [...] }.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


HINT_KINDS = {"append_flags", "set_env", "rewrite_cwd", "set_timeout"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_store(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": 1, "records": []}
    payload = json.loads(path.read_text())
    payload.setdefault("schema_version", 1)
    payload.setdefault("records", [])
    return payload


def write_store(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def record(store: dict, task_fingerprint: dict, command: str, error_class: str,
           stderr_summary: str, repair_classification: str,
           avoidance_hints: list[dict] | None = None) -> dict:
    """Add a failure record to the store. Returns the new record."""
    validated_hints = []
    for hint in (avoidance_hints or []):
        if hint.get("kind") in HINT_KINDS:
            validated_hints.append(hint)
    entry = {
        "task_fingerprint": task_fingerprint,
        "command": command,
        "error_class": error_class,
        "stderr_summary": stderr_summary[:500],
        "repair_classification": repair_classification,
        "avoidance_hints": validated_hints,
        "recorded_at": now(),
        "asset_version": 2,
    }
    store["records"].append(entry)
    return entry


def query(store: dict, task_fingerprint: dict) -> list[dict]:
    """Return all failure records matching the given fingerprint."""
    key = task_fingerprint.get("matching_key")
    if not key:
        return []
    return [
        r for r in store.get("records", [])
        if r.get("task_fingerprint", {}).get("matching_key") == key
    ]


def build_avoidance_hints(failure_records: list[dict]) -> list[dict]:
    """Extract structured avoidance hints from failure records."""
    hints = []
    seen = set()
    for rec in failure_records:
        for hint in rec.get("avoidance_hints", []):
            key = json.dumps(hint, sort_keys=True)
            if key not in seen:
                seen.add(key)
                hints.append(hint)
    return hints


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage Polaris failure records.")
    sub = parser.add_subparsers(dest="command", required=True)

    rec = sub.add_parser("record")
    rec.add_argument("--store", required=True)
    rec.add_argument("--fingerprint-json", required=True)
    rec.add_argument("--command", required=True)
    rec.add_argument("--error-class", required=True)
    rec.add_argument("--stderr-summary", default="")
    rec.add_argument("--repair-classification", default="unknown")
    rec.add_argument("--avoidance-hints-json", default="[]")

    q = sub.add_parser("query")
    q.add_argument("--store", required=True)
    q.add_argument("--fingerprint-json", required=True)

    args = parser.parse_args()
    store_path = Path(args.store)

    if args.command == "record":
        store = load_store(store_path)
        fp = json.loads(args.fingerprint_json)
        hints = json.loads(args.avoidance_hints_json)
        entry = record(store, fp, args.command, args.error_class,
                       args.stderr_summary, args.repair_classification, hints)
        write_store(store_path, store)
        print(json.dumps(entry, sort_keys=True))

    elif args.command == "query":
        store = load_store(store_path)
        fp = json.loads(args.fingerprint_json)
        results = query(store, fp)
        avoidance = build_avoidance_hints(results)
        print(json.dumps({"records": results, "avoidance_hints": avoidance}, sort_keys=True))


if __name__ == "__main__":
    main()
