#!/usr/bin/env python3
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


LIFECYCLE_ORDER = {
    "experimental": 0,
    "validated": 1,
    "preferred": 2,
    "retired": 3,
    "expired": 4,
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def load_store(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": 1, "patterns": []}
    payload = json.loads(path.read_text())
    if isinstance(payload, list):
        return {"schema_version": 1, "patterns": payload}
    payload.setdefault("schema_version", 1)
    payload.setdefault("patterns", [])
    return payload


def write_store(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def is_active(pattern: dict) -> bool:
    return pattern.get("lifecycle_state") not in {"retired", "expired"}


def stronger_lifecycle(left: str, right: str) -> str:
    return left if LIFECYCLE_ORDER.get(left, -1) >= LIFECYCLE_ORDER.get(right, -1) else right


def unique(values: list[str]) -> list[str]:
    seen = set()
    ordered = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def infer_best_lifecycle(pattern: dict) -> str:
    best = pattern.get("best_lifecycle_state", pattern.get("lifecycle_state", "experimental"))
    for item in pattern.get("history", []):
        target = item.get("to")
        if target:
            best = stronger_lifecycle(best, target)
    return best


def matches(pattern: dict, tags: list[str], trigger: str | None, mode: str | None, adapter: str | None) -> bool:
    if not is_active(pattern):
        return False
    if tags and not set(pattern.get("tags", [])).intersection(tags):
        return False
    if trigger and trigger.lower() not in pattern.get("trigger", "").lower():
        return False
    if mode and mode not in pattern.get("modes", []):
        return False
    if adapter and pattern.get("adapter") not in {None, "", adapter}:
        return False
    expires_at = pattern.get("expires_at")
    if expires_at and expires_at <= now():
        return False
    return True


def rank_pattern(pattern: dict, tags: list[str], adapter: str | None) -> dict:
    tag_hits = len(set(tags).intersection(pattern.get("tags", [])))
    adapter_bonus = 8 if adapter and pattern.get("adapter") == adapter else 0
    lifecycle_bonus = {
        "experimental": 0,
        "validated": 10,
        "preferred": 20,
        "retired": -50,
        "expired": -100,
    }.get(pattern.get("lifecycle_state", "experimental"), 0)
    confidence = int(pattern.get("confidence", 0))
    freshness_bonus = 2 if pattern.get("last_validated_at") else 0
    score = confidence + lifecycle_bonus + adapter_bonus + tag_hits * 5 + freshness_bonus
    return {
        "score": score,
        "pattern": pattern,
        "reasons": {
            "confidence": confidence,
            "lifecycle_bonus": lifecycle_bonus,
            "adapter_bonus": adapter_bonus,
            "tag_hits": tag_hits,
            "freshness_bonus": freshness_bonus,
        },
    }


def evidence_count(values: str) -> int:
    return len(parse_csv(values)) or 1


def merge_confidence(existing: dict | None, new_confidence: int, validation_delta: int, evidence_total: int) -> int:
    base = max(int(existing.get("confidence", 0)) if existing else 0, new_confidence)
    bounded_gain = min(6, max(0, validation_delta) * 2 + min(3, max(0, evidence_total - 1)))
    return min(95, max(base, base + bounded_gain))


def merge_pattern(existing: dict | None, incoming: dict) -> dict:
    if not existing:
        incoming["evidence"] = unique(incoming.get("evidence", []))
        incoming["evidence_count"] = len(incoming["evidence"])
        incoming["validation_count"] = 1
        incoming["confidence"] = min(95, max(0, int(incoming.get("confidence", 0))))
        incoming["best_lifecycle_state"] = infer_best_lifecycle(incoming)
        incoming.setdefault("history", []).append({"ts": now(), "event": "captured", "reason": "new_pattern"})
        return incoming

    merged = dict(existing)
    merged["summary"] = incoming["summary"]
    merged["trigger"] = incoming["trigger"]
    merged["sequence"] = incoming["sequence"]
    merged["outcome"] = incoming["outcome"]
    merged["adapter"] = incoming["adapter"] or existing.get("adapter")
    merged["tags"] = unique(existing.get("tags", []) + incoming.get("tags", []))
    merged["modes"] = unique(existing.get("modes", []) + incoming.get("modes", []))
    merged["evidence"] = unique(existing.get("evidence", []) + incoming.get("evidence", []))
    merged["evidence_count"] = len(merged["evidence"])
    merged["validation_count"] = int(existing.get("validation_count", 0)) + 1
    merged["confidence"] = merge_confidence(existing, int(incoming.get("confidence", 0)), 1, merged["evidence_count"])
    prior_best = infer_best_lifecycle(existing)
    merged["best_lifecycle_state"] = stronger_lifecycle(prior_best, incoming.get("lifecycle_state", "experimental"))
    if existing.get("lifecycle_state") in {"retired", "expired"}:
        merged["lifecycle_state"] = existing["lifecycle_state"]
    else:
        merged["lifecycle_state"] = merged["best_lifecycle_state"]
    merged["reusable"] = incoming["reusable"]
    merged["expires_at"] = incoming.get("expires_at") or existing.get("expires_at")
    merged["updated_at"] = now()
    merged["last_validated_at"] = now()
    merged.setdefault("history", []).append(
        {
            "ts": now(),
            "event": "merged_validation",
            "reason": "rerun_capture",
            "retained_lifecycle": merged["lifecycle_state"],
            "best_lifecycle_state": merged["best_lifecycle_state"],
            "evidence_count": merged["evidence_count"],
            "validation_count": merged["validation_count"],
            "confidence": merged["confidence"],
        }
    )
    return merged


def maybe_promote(pattern: dict) -> tuple[bool, str | None]:
    pattern["best_lifecycle_state"] = infer_best_lifecycle(pattern)
    current = stronger_lifecycle(pattern.get("lifecycle_state", "experimental"), pattern["best_lifecycle_state"])
    pattern["lifecycle_state"] = current
    validations = int(pattern.get("validation_count", 0))
    evidence = int(pattern.get("evidence_count", 0))
    confidence = int(pattern.get("confidence", 0))
    selections = int(pattern.get("selection_count", 0))
    target = None
    if current == "experimental" and validations >= 1 and evidence >= 2 and confidence >= 75:
        target = "validated"
    elif current in {"experimental", "validated"} and validations >= 2 and evidence >= 3 and confidence >= 85 and selections >= 1:
        target = "preferred"
    if not target or LIFECYCLE_ORDER.get(current, -1) >= LIFECYCLE_ORDER.get(target, -1):
        return False, None
    pattern["lifecycle_state"] = target
    pattern["best_lifecycle_state"] = stronger_lifecycle(pattern.get("best_lifecycle_state", current), target)
    pattern["promotion_count"] = pattern.get("promotion_count", 0) + 1
    pattern.setdefault("history", []).append({"ts": now(), "event": "auto_promoted", "to": target, "reason": "evidence_threshold_met"})
    pattern["last_validated_at"] = now()
    return True, target


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage dedicated Polaris success patterns.")
    sub = parser.add_subparsers(dest="command", required=True)

    capture = sub.add_parser("capture")
    capture.add_argument("--patterns", required=True)
    capture.add_argument("--pattern-id", required=True)
    capture.add_argument("--summary", required=True)
    capture.add_argument("--trigger", required=True)
    capture.add_argument("--sequence", required=True)
    capture.add_argument("--outcome", required=True)
    capture.add_argument("--evidence", required=True)
    capture.add_argument("--adapter", default="")
    capture.add_argument("--tags", default="")
    capture.add_argument("--modes", default="long")
    capture.add_argument("--confidence", type=int, default=60)
    capture.add_argument("--lifecycle-state", choices=sorted(LIFECYCLE_ORDER), default="experimental")
    capture.add_argument("--expires-at")
    capture.add_argument("--reusable", choices=["yes", "no"], default="yes")

    list_cmd = sub.add_parser("list")
    list_cmd.add_argument("--patterns", required=True)
    list_cmd.add_argument("--active-only", choices=["yes", "no"], default="no")

    summary_cmd = sub.add_parser("summary")
    summary_cmd.add_argument("--patterns", required=True)

    select = sub.add_parser("select")
    select.add_argument("--patterns", required=True)
    select.add_argument("--tags", default="")
    select.add_argument("--trigger")
    select.add_argument("--mode")
    select.add_argument("--adapter")
    select.add_argument("--min-confidence", type=int, default=0)

    promote = sub.add_parser("promote")
    promote.add_argument("--patterns", required=True)
    promote.add_argument("--pattern-id", required=True)
    promote.add_argument("--to", choices=["validated", "preferred"], required=True)
    promote.add_argument("--reason", required=True)
    promote.add_argument("--confidence", type=int)

    demote = sub.add_parser("demote")
    demote.add_argument("--patterns", required=True)
    demote.add_argument("--pattern-id", required=True)
    demote.add_argument("--to", choices=["experimental", "retired"], required=True)
    demote.add_argument("--reason", required=True)
    demote.add_argument("--confidence", type=int)

    expire = sub.add_parser("expire")
    expire.add_argument("--patterns", required=True)
    expire.add_argument("--pattern-id", required=True)
    expire.add_argument("--reason", required=True)

    promote_auto = sub.add_parser("promote-auto")
    promote_auto.add_argument("--patterns", required=True)
    promote_auto.add_argument("--pattern-id", required=True)

    args = parser.parse_args()
    path = Path(getattr(args, "patterns"))
    store = load_store(path)

    if args.command == "capture":
        existing = next((item for item in store["patterns"] if item.get("pattern_id") == args.pattern_id), None)
        incoming = {
            "pattern_id": args.pattern_id,
            "summary": args.summary,
            "trigger": args.trigger,
            "sequence": parse_csv(args.sequence),
            "outcome": args.outcome,
            "evidence": parse_csv(args.evidence),
            "adapter": args.adapter or None,
            "tags": parse_csv(args.tags),
            "modes": parse_csv(args.modes),
            "confidence": args.confidence,
            "lifecycle_state": args.lifecycle_state,
            "promotion_count": 0,
            "demotion_count": 0,
            "selection_count": 0,
            "reusable": args.reusable == "yes",
            "expires_at": args.expires_at,
            "created_at": now(),
            "updated_at": now(),
            "last_validated_at": now(),
        }
        pattern = merge_pattern(existing, incoming)
        store["patterns"] = [item for item in store["patterns"] if item.get("pattern_id") != args.pattern_id]
        store["patterns"].append(pattern)
        store["patterns"].sort(key=lambda item: (LIFECYCLE_ORDER.get(item.get("lifecycle_state"), 99), -item.get("confidence", 0), item.get("pattern_id", "")))
        write_store(path, store)
        print(json.dumps(pattern, sort_keys=True))
        return

    if args.command == "list":
        patterns = store["patterns"]
        if args.active_only == "yes":
            patterns = [item for item in patterns if is_active(item)]
        print(json.dumps({"patterns": patterns}, sort_keys=True))
        return

    if args.command == "summary":
        counts = {}
        for item in store["patterns"]:
            key = item.get("lifecycle_state", "unknown")
            counts[key] = counts.get(key, 0) + 1
        print(json.dumps({"total_patterns": len(store["patterns"]), "by_lifecycle": counts}, sort_keys=True))
        return

    if args.command == "select":
        tags = parse_csv(args.tags)
        ranked = []
        for pattern in store["patterns"]:
            if not matches(pattern, tags, args.trigger, args.mode, args.adapter):
                continue
            if int(pattern.get("confidence", 0)) < args.min_confidence:
                continue
            ranked.append(rank_pattern(pattern, tags, args.adapter))
        ranked.sort(key=lambda item: (-item["score"], item["pattern"].get("pattern_id", "")))
        if ranked:
            ranked[0]["pattern"]["selection_count"] = ranked[0]["pattern"].get("selection_count", 0) + 1
            ranked[0]["pattern"]["last_selected_at"] = now()
            write_store(path, store)
        print(json.dumps({"selected": ranked[:1], "candidates": ranked}, sort_keys=True))
        return

    if args.command == "promote-auto":
        for item in store["patterns"]:
            if item.get("pattern_id") != args.pattern_id:
                continue
            promoted, target = maybe_promote(item)
            write_store(path, store)
            print(json.dumps({"pattern": item, "promoted": promoted, "new_state": target}, sort_keys=True))
            return
        raise SystemExit(f"pattern not found: {args.pattern_id}")

    for item in store["patterns"]:
        if item.get("pattern_id") != args.pattern_id:
            continue
        item["updated_at"] = now()
        if args.command == "promote":
            item["lifecycle_state"] = args.to
            item["best_lifecycle_state"] = stronger_lifecycle(item.get("best_lifecycle_state", item.get("lifecycle_state", "experimental")), args.to)
            item["promotion_count"] = item.get("promotion_count", 0) + 1
            item.setdefault("history", []).append({"ts": now(), "event": "promoted", "to": args.to, "reason": args.reason})
            if args.confidence is not None:
                item["confidence"] = args.confidence
            item["last_validated_at"] = now()
            write_store(path, store)
            print(json.dumps(item, sort_keys=True))
            return
        if args.command == "demote":
            item["lifecycle_state"] = args.to
            item["demotion_count"] = item.get("demotion_count", 0) + 1
            item.setdefault("history", []).append({"ts": now(), "event": "demoted", "to": args.to, "reason": args.reason})
            if args.confidence is not None:
                item["confidence"] = args.confidence
            write_store(path, store)
            print(json.dumps(item, sort_keys=True))
            return
        if args.command == "expire":
            item["lifecycle_state"] = "expired"
            item.setdefault("history", []).append({"ts": now(), "event": "expired", "reason": args.reason})
            write_store(path, store)
            print(json.dumps(item, sort_keys=True))
            return

    raise SystemExit(f"pattern not found: {args.pattern_id}")


if __name__ == "__main__":
    main()
