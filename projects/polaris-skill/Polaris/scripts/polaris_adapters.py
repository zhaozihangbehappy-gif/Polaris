#!/usr/bin/env python3
import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path


TRUST_ORDER = {"sandboxed": 0, "workspace": 1, "user-approved": 2}
CACHE_SCHEMA_VERSION = 1


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def load(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": 3, "adapters": []}
    payload = json.loads(path.read_text())
    if isinstance(payload, list):
        return {"schema_version": 3, "adapters": payload}
    payload.setdefault("schema_version", 3)
    payload.setdefault("adapters", [])
    return payload


def save(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_cache(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": CACHE_SCHEMA_VERSION, "entries": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.setdefault("schema_version", CACHE_SCHEMA_VERSION)
    payload.setdefault("entries", {})
    return payload


def save_cache(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def check_prerequisites(adapter: dict) -> dict:
    results = []
    ready = True
    for prerequisite in adapter.get("prerequisites", []):
        proc = subprocess.run(["bash", "-lc", f"command -v {prerequisite} >/dev/null 2>&1"], capture_output=True, text=True)
        ok = proc.returncode == 0
        ready = ready and ok
        results.append({"name": prerequisite, "available": ok})
    return {"ready": ready, "checks": results}


def fallback_chain(adapter: dict, by_tool: dict[str, dict]) -> list[dict]:
    chain = []
    for tool in adapter.get("fallbacks", []):
        target = by_tool.get(tool)
        chain.append(
            {
                "tool": tool,
                "available": target is not None,
                "trust_level": target.get("trust_level") if target else None,
                "cost_hint": target.get("cost_hint") if target else None,
            }
        )
    return chain


def scenario_payload(
    required_capabilities: list[str],
    mode: str | None,
    execution_profile: str | None,
    max_trust: str | None,
    max_cost: int | None,
    failure_type: str | None,
    require_durable_status: bool,
) -> dict:
    return {
        "required_capabilities": sorted(required_capabilities),
        "mode": mode,
        "execution_profile": execution_profile,
        "failure_type": failure_type,
        "max_trust": max_trust,
        "max_cost": max_cost,
        "require_durable_status": require_durable_status,
    }


def scenario_fingerprint(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha1(encoded).hexdigest()[:16]


def adapter_rank(
    adapter: dict,
    registry_map: dict[str, dict],
    required_capabilities: list[str],
    mode: str | None,
    max_trust: str | None,
    max_cost: int | None,
    failure_type: str | None,
    require_durable_status: bool,
    verify_prereqs: bool,
) -> dict | None:
    capabilities = set(adapter.get("capabilities", []))
    required = set(required_capabilities)
    missing = sorted(required - capabilities)
    if missing:
        return None
    if mode and mode not in adapter.get("modes", []):
        return None

    trust_level = adapter.get("trust_level", "workspace")
    if max_trust and TRUST_ORDER.get(trust_level, 99) > TRUST_ORDER.get(max_trust, 99):
        return None
    if max_cost is not None and int(adapter.get("cost_hint", 0)) > max_cost:
        return None
    if require_durable_status and "durable-status" not in capabilities:
        return None

    prereq = check_prerequisites(adapter) if verify_prereqs else {"ready": True, "checks": []}
    if verify_prereqs and not prereq["ready"]:
        return None

    matched = len(required.intersection(capabilities))
    selector_bonus = min(len(adapter.get("selectors", [])), 3) * 2
    fallback_plan = fallback_chain(adapter, registry_map)
    fallback_bonus = sum(2 for item in fallback_plan if item["available"])
    retry_bonus = 4 if adapter.get("safe_retry") else 0
    trust_penalty = TRUST_ORDER.get(trust_level, 1) * 4
    cost_penalty = int(adapter.get("cost_hint", 0)) * 3
    latency_penalty = int(adapter.get("latency_hint", 0))
    mode_bonus = int(adapter.get("mode_preferences", {}).get(mode, 0)) if mode else 0
    durability_bonus = 8 if "durable-status" in capabilities else 0
    long_run_bonus = 6 if mode == "long" and "long-run" in capabilities else 0
    failure_bonus = 6 if failure_type and failure_type in adapter.get("preferred_failures", []) else 0
    failure_penalty = 8 if failure_type and failure_type in adapter.get("avoid_failures", []) else 0
    prereq_bonus = 4 if prereq["ready"] else -20
    score = matched * 20 + selector_bonus + fallback_bonus + retry_bonus + mode_bonus + durability_bonus + long_run_bonus + failure_bonus + prereq_bonus - trust_penalty - cost_penalty - latency_penalty - failure_penalty
    return {
        "score": score,
        "adapter": adapter,
        "reasons": {
            "matched_capabilities": matched,
            "selector_bonus": selector_bonus,
            "fallback_bonus": fallback_bonus,
            "retry_bonus": retry_bonus,
            "mode_bonus": mode_bonus,
            "durability_bonus": durability_bonus,
            "long_run_bonus": long_run_bonus,
            "failure_bonus": failure_bonus,
            "failure_penalty": failure_penalty,
            "prereq_bonus": prereq_bonus,
            "trust_penalty": trust_penalty,
            "cost_penalty": cost_penalty,
            "latency_penalty": latency_penalty,
        },
        "fallback_chain": fallback_plan,
        "prerequisites": prereq,
    }


def sticky_candidate(
    cache_path: Path | None,
    fingerprint: str,
    by_tool: dict[str, dict],
    reuse_window_seconds: int,
    verify_prereqs: bool,
) -> tuple[dict | None, dict]:
    trace = {"checked": False, "reused": False}
    if not cache_path:
        trace["reason"] = "cache_disabled"
        return None, trace

    cache = load_cache(cache_path)
    entry = cache.get("entries", {}).get(fingerprint)
    trace["checked"] = True
    trace["cache_path"] = str(cache_path)
    if not entry:
        trace["reason"] = "cache_miss"
        return None, trace

    trace["entry"] = entry
    adapter_name = entry.get("selected_adapter")
    adapter = by_tool.get(adapter_name)
    if not adapter:
        trace["reason"] = "adapter_missing"
        return None, trace

    last_success = parse_ts(entry.get("last_success_at"))
    last_failure = parse_ts(entry.get("last_failure_at"))
    if last_failure and not last_success:
        trace["reason"] = "recent_failure"
        return None, trace
    if not last_success:
        trace["reason"] = "missing_success_timestamp"
        return None, trace
    if datetime.now(timezone.utc) - last_success > timedelta(seconds=reuse_window_seconds):
        trace["reason"] = "stale_success"
        return None, trace

    if last_failure and last_failure >= last_success:
        trace["reason"] = "recent_failure"
        return None, trace

    prereq = check_prerequisites(adapter) if verify_prereqs else {"ready": True, "checks": []}
    if verify_prereqs and not prereq["ready"]:
        trace["reason"] = "prerequisites_failed"
        trace["prerequisites"] = prereq
        return None, trace

    trace["reused"] = True
    trace["reason"] = "sticky_reuse"
    trace["prerequisites"] = prereq
    return {
        "score": entry.get("last_score"),
        "adapter": adapter,
        "reasons": {"sticky_reuse": True},
        "fallback_chain": fallback_chain(adapter, by_tool),
        "prerequisites": prereq,
        "sticky_reuse": {
            "fingerprint": fingerprint,
            "last_success_at": entry.get("last_success_at"),
            "failure_count": entry.get("failure_count", 0),
        },
    }, trace


def update_cache_entry(
    cache_path: Path,
    fingerprint: str,
    payload: dict,
    adapter_name: str,
    status: str,
    score: int | None,
    prerequisite_snapshot: dict | None,
) -> dict:
    cache = load_cache(cache_path)
    entries = cache.setdefault("entries", {})
    entry = entries.get(fingerprint, {})
    entry.update(
        {
            "scenario": payload,
            "selected_adapter": adapter_name,
            "last_status": status,
            "last_score": score,
            "updated_at": now(),
        }
    )
    if prerequisite_snapshot is not None:
        entry["prerequisite_snapshot"] = prerequisite_snapshot
    if status == "success":
        entry["last_success_at"] = now()
        entry["failure_count"] = 0
    elif status == "failure":
        entry["last_failure_at"] = now()
        entry["failure_count"] = int(entry.get("failure_count", 0)) + 1
    entries[fingerprint] = entry
    save_cache(cache_path, cache)
    return entry


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage Polaris adapters.")
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add")
    add.add_argument("--registry", required=True)
    add.add_argument("--tool", required=True)
    add.add_argument("--tool-command", required=True)
    add.add_argument("--inputs", required=True)
    add.add_argument("--capabilities", default="")
    add.add_argument("--modes", default="short,long")
    add.add_argument("--prerequisites", default="")
    add.add_argument("--selectors", default="")
    add.add_argument("--failure-notes", default="")
    add.add_argument("--fallbacks", default="")
    add.add_argument("--fallback-notes", default="")
    add.add_argument("--mode-preferences", default="")
    add.add_argument("--trust-level", choices=["sandboxed", "workspace", "user-approved"], default="workspace")
    add.add_argument("--cost-hint", type=int, default=1)
    add.add_argument("--latency-hint", type=int, default=1)
    add.add_argument("--preferred-failures", default="")
    add.add_argument("--avoid-failures", default="")
    add.add_argument("--safe-retry", choices=["yes", "no"], default="yes")
    add.add_argument("--notes", default="")

    ls = sub.add_parser("list")
    ls.add_argument("--registry", required=True)

    select = sub.add_parser("select")
    select.add_argument("--registry", required=True)
    select.add_argument("--capabilities", default="")
    select.add_argument("--mode")
    select.add_argument("--execution-profile")
    select.add_argument("--max-trust")
    select.add_argument("--max-cost", type=int)
    select.add_argument("--failure-type")
    select.add_argument("--require-durable-status", choices=["yes", "no"], default="no")
    select.add_argument("--verify-prereqs", choices=["yes", "no"], default="yes")
    select.add_argument("--sticky-cache")
    select.add_argument("--reuse-window-seconds", type=int, default=3600)

    record = sub.add_parser("record")
    record.add_argument("--cache", required=True)
    record.add_argument("--capabilities", default="")
    record.add_argument("--mode")
    record.add_argument("--execution-profile")
    record.add_argument("--max-trust")
    record.add_argument("--max-cost", type=int)
    record.add_argument("--failure-type")
    record.add_argument("--require-durable-status", choices=["yes", "no"], default="no")
    record.add_argument("--adapter", required=True)
    record.add_argument("--status", choices=["success", "failure"], required=True)
    record.add_argument("--score", type=int)
    record.add_argument("--registry")

    args = parser.parse_args()

    if args.command == "record":
        required_capabilities = parse_csv(args.capabilities)
        payload = scenario_payload(
            required_capabilities,
            args.mode,
            args.execution_profile,
            args.max_trust,
            args.max_cost,
            args.failure_type,
            args.require_durable_status == "yes",
        )
        fingerprint = scenario_fingerprint(payload)
        prereq = None
        if args.registry:
            registry_payload = load(Path(args.registry))
            by_tool = {item.get("tool"): item for item in registry_payload["adapters"]}
            adapter = by_tool.get(args.adapter)
            if adapter:
                prereq = check_prerequisites(adapter)
        entry = update_cache_entry(Path(args.cache), fingerprint, payload, args.adapter, args.status, args.score, prereq)
        print(json.dumps({"fingerprint": fingerprint, "entry": entry}, sort_keys=True))
        return

    registry = Path(getattr(args, "registry"))
    payload = load(registry)
    items = payload["adapters"]

    if args.command == "add":
        mode_preferences = {}
        for item in parse_csv(args.mode_preferences):
            key, _, value = item.partition(":")
            if key and value:
                mode_preferences[key] = int(value)
        record = {
            "tool": args.tool,
            "command": args.tool_command,
            "inputs": parse_csv(args.inputs),
            "capabilities": parse_csv(args.capabilities),
            "modes": parse_csv(args.modes),
            "prerequisites": parse_csv(args.prerequisites),
            "selectors": parse_csv(args.selectors),
            "failure_notes": parse_csv(args.failure_notes),
            "fallbacks": parse_csv(args.fallbacks),
            "fallback_notes": parse_csv(args.fallback_notes),
            "mode_preferences": mode_preferences,
            "trust_level": args.trust_level,
            "cost_hint": args.cost_hint,
            "latency_hint": args.latency_hint,
            "preferred_failures": parse_csv(args.preferred_failures),
            "avoid_failures": parse_csv(args.avoid_failures),
            "safe_retry": args.safe_retry == "yes",
            "notes": args.notes,
            "updated_at": now(),
        }
        items = [item for item in items if item.get("tool") != args.tool]
        items.append(record)
        payload["adapters"] = sorted(items, key=lambda item: item["tool"])
        save(registry, payload)
        print(json.dumps(record, sort_keys=True))
        return

    if args.command == "list":
        print(json.dumps(payload, sort_keys=True))
        return

    required_capabilities = parse_csv(args.capabilities)
    by_tool = {item.get("tool"): item for item in items}
    scenario = scenario_payload(
        required_capabilities,
        args.mode,
        args.execution_profile,
        args.max_trust,
        args.max_cost,
        args.failure_type,
        args.require_durable_status == "yes",
    )
    fingerprint = scenario_fingerprint(scenario)
    cache_path = Path(args.sticky_cache) if args.sticky_cache else None

    selected = []
    sticky_trace = {}
    reused_rank, sticky_trace = sticky_candidate(
        cache_path,
        fingerprint,
        by_tool,
        args.reuse_window_seconds,
        args.verify_prereqs == "yes",
    )
    if reused_rank is not None:
        selected = [reused_rank]
        ranked = [reused_rank]
    else:
        ranked = []
        for item in items:
            rank = adapter_rank(
                item,
                by_tool,
                required_capabilities,
                args.mode,
                args.max_trust,
                args.max_cost,
                args.failure_type,
                args.require_durable_status == "yes",
                args.verify_prereqs == "yes",
            )
            if rank is not None:
                ranked.append(rank)
        ranked.sort(key=lambda item: (-item["score"], TRUST_ORDER.get(item["adapter"].get("trust_level", "workspace"), 99), item["adapter"].get("tool", "")))
        selected = ranked[:1]

    print(
        json.dumps(
            {
                "selected": selected,
                "candidates": ranked,
                "selection_trace": {
                    "required_capabilities": required_capabilities,
                    "failure_type": args.failure_type,
                    "mode": args.mode,
                    "execution_profile": args.execution_profile,
                    "require_durable_status": args.require_durable_status == "yes",
                    "scenario_fingerprint": fingerprint,
                    "sticky_reuse": sticky_trace,
                },
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
