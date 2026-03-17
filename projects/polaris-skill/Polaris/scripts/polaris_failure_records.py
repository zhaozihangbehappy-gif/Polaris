#!/usr/bin/env python3
"""Dedicated failure experience store for Polaris L2 path pruning.

Failure records are separate from success patterns. The orchestrator queries
both stores and assembles experience_hints: { prefer: [...], avoid: [...] }.

Schema v2 adds: applied_count, applied_fail_count, stale, rejected_by, source.
"""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


HINT_KINDS = {"append_flags", "set_env", "rewrite_cwd", "set_timeout"}
DEFAULT_TTL_DAYS = 30

# Query priority: higher number = higher priority
SOURCE_PRIORITY = {"prebuilt": 0, "auto": 1, "user_correction": 2}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(ts_str: str) -> datetime | None:
    """Parse an ISO timestamp string to datetime (UTC)."""
    if not ts_str:
        return None
    try:
        ts_str = ts_str.replace("Z", "+00:00")
        return datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        return None


def load_store(path: Path) -> dict:
    """Load failure store via the R0 contract layer (atomic read + corruption recovery)."""
    import polaris_experience_store as pes
    payload, _mtime = pes.safe_load(
        path, default_factory={"schema_version": 2, "records": []},
    )
    payload.setdefault("schema_version", 1)
    payload.setdefault("records", [])
    _migrate_v1_to_v2(payload)
    return payload


def _migrate_v1_to_v2(store: dict) -> None:
    """In-place migration from schema v1 to v2. Idempotent."""
    if store.get("schema_version", 1) >= 2:
        # Still backfill any records missing v2 fields (defensive)
        for rec in store.get("records", []):
            rec.setdefault("applied_count", 0)
            rec.setdefault("applied_fail_count", 0)
            rec.setdefault("stale", False)
            rec.setdefault("rejected_by", None)
            rec.setdefault("source", "auto")
        return
    store["schema_version"] = 2
    for rec in store.get("records", []):
        rec.setdefault("applied_count", 0)
        rec.setdefault("applied_fail_count", 0)
        rec.setdefault("stale", False)
        rec.setdefault("rejected_by", None)
        rec.setdefault("source", "auto")


def write_store(path: Path, payload: dict) -> None:
    """Write failure store via the R0 contract layer (atomic write)."""
    import polaris_experience_store as pes
    pes.atomic_write(path, payload)


def record(store: dict, task_fingerprint: dict, command: str, error_class: str,
           stderr_summary: str, repair_classification: str,
           avoidance_hints: list[dict] | None = None,
           source: str = "auto", ecosystem: str | None = None) -> dict:
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
        "applied_count": 0,
        "applied_fail_count": 0,
        "stale": False,
        "rejected_by": None,
        "source": source,
    }
    if ecosystem:
        entry["ecosystem"] = ecosystem
    store["records"].append(entry)
    return entry


def _is_expired(rec: dict, ttl_days: int) -> bool:
    """Check if a record has exceeded TTL based on recorded_at (UTC)."""
    ts = _parse_ts(rec.get("recorded_at", ""))
    if ts is None:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)
    return ts < cutoff


def _is_active(rec: dict, ttl_days: int) -> bool:
    """A record is active if not stale, not expired, and not rejected."""
    if rec.get("stale", False):
        return False
    if _is_expired(rec, ttl_days):
        return False
    return True


def query(store: dict, matching_key: str | None = None,
          command_key: str | None = None, ttl_days: int = DEFAULT_TTL_DAYS,
          ecosystem: str | None = None, error_class: str | None = None) -> dict:
    """Query failure records with three-tier matching and source priority.

    Tiers:
      1. exact: matching_key match → confidence 1.0
      2. command_only: command_key match (different cwd) → confidence 0.6
      3. ecosystem: source=prebuilt + ecosystem + error_class match → confidence 0.5
         (without error_class match: confidence 0.4, below apply threshold)

    Returns: {"avoidance_hints": [...], "match_tier": "exact"|"command_only"|"ecosystem"|"none", "matched_count": N}
    """
    if not matching_key:
        return {"avoidance_hints": [], "match_tier": "none", "matched_count": 0}

    records = store.get("records", [])

    # Tier 1: exact match on matching_key
    exact = [r for r in records
             if r.get("task_fingerprint", {}).get("matching_key") == matching_key
             and _is_active(r, ttl_days)]

    if exact:
        hints = _build_prioritized_hints(exact, confidence_discount=1.0)
        return {"avoidance_hints": hints, "match_tier": "exact", "matched_count": len(exact)}

    # Tier 2: command_key fallback (B2)
    if command_key:
        fallback = [r for r in records
                    if r.get("task_fingerprint", {}).get("command_key") == command_key
                    and _is_active(r, ttl_days)]
        if fallback:
            hints = _build_prioritized_hints(fallback, confidence_discount=0.6)
            return {"avoidance_hints": hints, "match_tier": "command_only", "matched_count": len(fallback)}

    # Tier 3: ecosystem fallback for prebuilt records (C1)
    # With error_class: only return prebuilt records whose error_class matches → discount 0.5 (at apply threshold)
    # Without error_class: return all ecosystem prebuilt → discount 0.4 (below apply threshold, informational only)
    if ecosystem:
        eco_all = [r for r in records
                   if r.get("source") == "prebuilt"
                   and r.get("ecosystem") == ecosystem
                   and _is_active(r, ttl_days)]

        if error_class and eco_all:
            eco_matched = [r for r in eco_all if r.get("error_class") == error_class]
            if eco_matched:
                hints = _build_prioritized_hints(eco_matched, confidence_discount=0.5)
                return {"avoidance_hints": hints, "match_tier": "ecosystem", "matched_count": len(eco_matched)}

        # No error_class filter or no error_class match → return all but at low confidence
        if eco_all:
            hints = _build_prioritized_hints(eco_all, confidence_discount=0.4)
            return {"avoidance_hints": hints, "match_tier": "ecosystem", "matched_count": len(eco_all)}

    return {"avoidance_hints": [], "match_tier": "none", "matched_count": 0}


def _build_prioritized_hints(records: list[dict], confidence_discount: float) -> list[dict]:
    """Build deduplicated hints sorted by source priority (C2)."""
    # Sort by source priority descending
    sorted_recs = sorted(records, key=lambda r: -SOURCE_PRIORITY.get(r.get("source", "auto"), 1))
    hints = []
    seen = set()
    for rec in sorted_recs:
        for hint in rec.get("avoidance_hints", []):
            key = json.dumps(hint, sort_keys=True)
            if key not in seen:
                seen.add(key)
                h = dict(hint)
                h["confidence_discount"] = confidence_discount
                hints.append(h)
    return hints


def build_avoidance_hints(failure_records: list[dict]) -> list[dict]:
    """Legacy: extract structured avoidance hints from failure records."""
    hints = []
    seen = set()
    for rec in failure_records:
        for hint in rec.get("avoidance_hints", []):
            key = json.dumps(hint, sort_keys=True)
            if key not in seen:
                seen.add(key)
                hints.append(hint)
    return hints


def update_applied(store: dict, matching_key: str, success: bool) -> None:
    """Update applied_count and applied_fail_count for matching records.
    If applied_fail_count >= 3, mark stale (one-way)."""
    for rec in store.get("records", []):
        if rec.get("task_fingerprint", {}).get("matching_key") == matching_key:
            if rec.get("stale", False):
                continue
            rec["applied_count"] = rec.get("applied_count", 0) + 1
            if not success:
                rec["applied_fail_count"] = rec.get("applied_fail_count", 0) + 1
                if rec["applied_fail_count"] >= 3:
                    rec["stale"] = True


def reject_record(store: dict, index: int) -> bool:
    """Mark record at index as stale + rejected_by=user. Idempotent."""
    records = store.get("records", [])
    if 0 <= index < len(records):
        records[index]["stale"] = True
        records[index]["rejected_by"] = "user"
        return True
    return False


def correct_record(store: dict, index: int, hint_kind: str, hint_value: dict) -> dict | None:
    """Create a user_correction record based on original at index."""
    records = store.get("records", [])
    if index < 0 or index >= len(records):
        return None
    if hint_kind not in HINT_KINDS:
        return None
    original = records[index]
    new_hint = {"kind": hint_kind}
    new_hint.update(hint_value)
    entry = {
        "task_fingerprint": dict(original.get("task_fingerprint", {})),
        "command": original.get("command", ""),
        "error_class": original.get("error_class", "unknown"),
        "stderr_summary": original.get("stderr_summary", ""),
        "repair_classification": original.get("repair_classification", "unknown"),
        "avoidance_hints": [new_hint],
        "recorded_at": now(),
        "asset_version": 2,
        "applied_count": 0,
        "applied_fail_count": 0,
        "stale": False,
        "rejected_by": None,
        "source": "user_correction",
    }
    if "ecosystem" in original:
        entry["ecosystem"] = original["ecosystem"]
    store["records"].append(entry)
    return entry


def list_feedback(store: dict) -> list[dict]:
    """List all rejected and user_correction records."""
    return [
        {"index": i, "source": r.get("source", "auto"),
         "rejected_by": r.get("rejected_by"), "stale": r.get("stale", False),
         "command": r.get("command", ""), "error_class": r.get("error_class", "")}
        for i, r in enumerate(store.get("records", []))
        if r.get("rejected_by") or r.get("source") == "user_correction"
    ]


def reset_prebuilt(store: dict, ecosystem: str | None = None) -> int:
    """Remove all source=prebuilt records. Returns count removed."""
    records = store.get("records", [])
    before = len(records)
    if ecosystem:
        store["records"] = [r for r in records
                            if not (r.get("source") == "prebuilt" and r.get("ecosystem") == ecosystem)]
    else:
        store["records"] = [r for r in records if r.get("source") != "prebuilt"]
    return before - len(store["records"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage Polaris failure records.")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    rec = sub.add_parser("record")
    rec.add_argument("--store", required=True)
    rec.add_argument("--fingerprint-json", required=True)
    rec.add_argument("--command-str", required=True, dest="command_str",
                     help="The shell command that failed")
    rec.add_argument("--error-class", required=True)
    rec.add_argument("--stderr-summary", default="")
    rec.add_argument("--repair-classification", default="unknown")
    rec.add_argument("--avoidance-hints-json", default="[]")
    rec.add_argument("--source", default="auto")
    rec.add_argument("--ecosystem", default=None)

    q = sub.add_parser("query")
    q.add_argument("--store", required=True)
    q.add_argument("--matching-key", required=True)
    q.add_argument("--command-key", default=None)
    q.add_argument("--ttl-days", type=int, default=DEFAULT_TTL_DAYS)
    q.add_argument("--ecosystem", default=None)
    q.add_argument("--error-class", default=None)

    ua = sub.add_parser("update-applied")
    ua.add_argument("--store", required=True)
    ua.add_argument("--matching-key", required=True)
    ua.add_argument("--success", required=True, choices=["true", "false"])

    args = parser.parse_args()
    store_path = Path(args.store)

    if args.subcommand == "record":
        store = load_store(store_path)
        fp = json.loads(args.fingerprint_json)
        hints = json.loads(args.avoidance_hints_json)
        entry = record(store, fp, args.command_str, args.error_class,
                       args.stderr_summary, args.repair_classification, hints,
                       source=args.source, ecosystem=args.ecosystem)
        write_store(store_path, store)
        print(json.dumps(entry, sort_keys=True))

    elif args.subcommand == "query":
        store = load_store(store_path)
        result = query(store, matching_key=args.matching_key,
                       command_key=args.command_key, ttl_days=args.ttl_days,
                       ecosystem=args.ecosystem, error_class=args.error_class)
        # Write back in case migration happened
        write_store(store_path, store)
        print(json.dumps(result, sort_keys=True))

    elif args.subcommand == "update-applied":
        store = load_store(store_path)
        update_applied(store, args.matching_key, args.success == "true")
        write_store(store_path, store)
        print(json.dumps({"ok": True}))


if __name__ == "__main__":
    main()
