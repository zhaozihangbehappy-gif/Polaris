#!/usr/bin/env python3
# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


LAYER_ORDER = {"hard": 0, "soft": 1, "experimental": 2}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_store() -> dict:
    return {
        "schema_version": 3,
        "rules": [],
    }


def load_store(path: Path) -> dict:
    if not path.exists():
        return default_store()
    payload = json.loads(path.read_text())
    if isinstance(payload, list):
        return {
            "schema_version": 3,
            "rules": payload,
        }
    payload.setdefault("schema_version", 3)
    payload.setdefault("rules", [])
    for r in payload["rules"]:
        if "asset_version" not in r:
            r["asset_version"] = 1
            r["migrated_from"] = "pre-step4"
    return payload


def write_store(path: Path, store: dict) -> None:
    path.write_text(json.dumps(store, indent=2, sort_keys=True) + "\n")


def parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def rule_matches(rule: dict, tags: list[str], scope: str | None) -> bool:
    rule_tags = set(rule.get("tags", []))
    if tags and not rule_tags.intersection(tags):
        return False
    if scope and scope not in rule.get("scope", ""):
        return False
    return True


def evidence_count(value: str) -> int:
    return len(parse_csv(value)) or 1


def find_existing_rule(store: dict, rule_id: str | None, fingerprint: str | None) -> dict | None:
    for item in store["rules"]:
        if rule_id and item.get("rule_id") == rule_id:
            return item
    if fingerprint:
        for item in store["rules"]:
            if item.get("fingerprint") == fingerprint:
                return item
    return None


def maybe_promote(rule: dict) -> tuple[bool, str | None]:
    if rule.get("layer") != "experimental":
        return False, None
    if int(rule.get("evidence_count", 0)) >= 2 and int(rule.get("validation_count", 0)) >= 1:
        rule["layer"] = "soft"
        rule.setdefault("history", []).append(
            {"ts": now(), "event": "auto_promoted", "to": "soft", "reason": "evidence_threshold_met"}
        )
        return True, "soft"
    return False, None


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage Polaris layered rules.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add")
    add_parser.add_argument("--rules", required=True)
    add_parser.add_argument("--rule-id", required=True)
    add_parser.add_argument("--layer", choices=["hard", "soft", "experimental"], required=True)
    add_parser.add_argument("--trigger", required=True)
    add_parser.add_argument("--action", required=True)
    add_parser.add_argument("--evidence", required=True)
    add_parser.add_argument("--scope", required=True)
    add_parser.add_argument("--tags", default="")
    add_parser.add_argument("--validation", default="observed local evidence")
    add_parser.add_argument("--priority", type=int, default=50)

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--rules", required=True)
    list_parser.add_argument("--layer")

    select_parser = subparsers.add_parser("select")
    select_parser.add_argument("--rules", required=True)
    select_parser.add_argument("--tags", default="")
    select_parser.add_argument("--scope")
    select_parser.add_argument("--layers", default="hard,soft")

    promote_parser = subparsers.add_parser("promote-auto")
    promote_parser.add_argument("--rules", required=True)
    promote_parser.add_argument("--rule-id", required=True)

    consolidate_parser = subparsers.add_parser("consolidate-candidate")
    consolidate_parser.add_argument("--rules", required=True)
    consolidate_parser.add_argument("--candidate", required=True)
    consolidate_parser.add_argument("--promote-auto", choices=["yes", "no"], default="yes")

    args = parser.parse_args()
    rules_path = Path(args.rules)
    store = load_store(rules_path)

    if args.command == "add":
        rule = {
            "rule_id": args.rule_id,
            "layer": args.layer,
            "trigger": args.trigger,
            "action": args.action,
            "evidence": args.evidence,
            "scope": args.scope,
            "fingerprint": args.rule_id,
            "tags": parse_csv(args.tags),
            "validation": args.validation,
            "priority": args.priority,
            "strategy_overrides": {},
            "evidence_count": evidence_count(args.evidence),
            "validation_count": 1,
            "last_validated_at": now(),
            "created_at": now(),
            "asset_version": 2,
        }
        existing = find_existing_rule(store, args.rule_id, None)
        if existing:
            rule["created_at"] = existing.get("created_at", rule["created_at"])
            rule["evidence_count"] += int(existing.get("evidence_count", 0))
            rule["validation_count"] += int(existing.get("validation_count", 0))
            rule["history"] = existing.get("history", [])
        store["rules"] = [existing for existing in store["rules"] if existing.get("rule_id") != args.rule_id]
        store["rules"].append(rule)
        store["rules"].sort(key=lambda item: (LAYER_ORDER.get(item.get("layer"), 9), -item.get("priority", 0), item.get("rule_id", "")))
        write_store(rules_path, store)
        print(json.dumps(rule, sort_keys=True))
        return

    if args.command == "promote-auto":
        for rule in store["rules"]:
            if rule.get("rule_id") != args.rule_id:
                continue
            promoted, new_layer = maybe_promote(rule)
            write_store(rules_path, store)
            print(json.dumps({"rule": rule, "promoted": promoted, "new_layer": new_layer}, sort_keys=True))
            return
        raise SystemExit(f"rule not found: {args.rule_id}")

    if args.command == "consolidate-candidate":
        candidate = json.loads(args.candidate)
        existing = find_existing_rule(store, candidate.get("rule_id"), candidate.get("fingerprint"))
        rule = {
            "rule_id": candidate["rule_id"],
            "layer": candidate.get("layer", "experimental"),
            "trigger": candidate["trigger"],
            "action": candidate["action"],
            "evidence": ",".join(candidate.get("evidence", [])),
            "scope": candidate["scope"],
            "fingerprint": candidate.get("fingerprint") or candidate.get("rule_id"),
            "tags": candidate.get("tags", []),
            "validation": candidate.get("validation", "observed local evidence"),
            "priority": int(candidate.get("priority", 50)),
            "strategy_overrides": candidate.get("strategy_overrides", {}),
            "evidence_count": len(candidate.get("evidence", [])) or 1,
            "validation_count": 1,
            "last_validated_at": now(),
            "created_at": now(),
            "asset_version": candidate.get("asset_version", 2),
        }
        if existing:
            rule["created_at"] = existing.get("created_at", rule["created_at"])
            rule["evidence_count"] += int(existing.get("evidence_count", 0))
            rule["validation_count"] += int(existing.get("validation_count", 0))
            rule["history"] = existing.get("history", [])
        store["rules"] = [
            item for item in store["rules"]
            if item is not existing and item.get("rule_id") != candidate.get("rule_id") and item.get("fingerprint") != candidate.get("fingerprint")
        ]
        store["rules"].append(rule)
        promoted = False
        new_layer = None
        if args.promote_auto == "yes":
            promoted, new_layer = maybe_promote(rule)
        store["rules"].sort(key=lambda item: (LAYER_ORDER.get(item.get("layer"), 9), -item.get("priority", 0), item.get("rule_id", "")))
        write_store(rules_path, store)
        print(json.dumps({"rule": rule, "promoted": promoted, "new_layer": new_layer}, sort_keys=True))
        return

    if args.command == "list":
        rules = store["rules"]
        if args.layer:
            rules = [rule for rule in rules if rule.get("layer") == args.layer]
        print(json.dumps({"rules": rules}, sort_keys=True))
        return

    layers = set(parse_csv(args.layers))
    tags = parse_csv(args.tags)
    selected = [
        rule for rule in store["rules"]
        if rule.get("layer") in layers and rule_matches(rule, tags, args.scope)
    ]
    selected.sort(key=lambda item: (LAYER_ORDER.get(item.get("layer"), 9), -item.get("priority", 0), item.get("rule_id", "")))
    print(json.dumps({"rules": selected}, sort_keys=True))


if __name__ == "__main__":
    main()
