#!/usr/bin/env python3
# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

"""Polaris community promotion channel."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
import time
import uuid
from pathlib import Path

from polaris import paths
from polaris.schema import validate_shape

PROMOTION_MIN_CONFIRMATIONS = 2
UPSTREAM_AUTHORED = "upstream_authored"


def _salt_path() -> Path:
    paths.ensure_user_data()
    return paths.contributor_salt_path()


def _fingerprint() -> str:
    salt = _salt_path()
    if not salt.exists():
        salt.parent.mkdir(parents=True, exist_ok=True)
        salt.write_text(secrets.token_hex(32))
        try:
            os.chmod(salt, 0o600)
        except OSError:
            pass
    return hashlib.sha256(salt.read_text().strip().encode()).hexdigest()[:16]


def _load_candidate_index() -> dict[str, Path]:
    idx: dict[str, Path] = {}
    root = paths.candidate_packs_dir()
    if not root.exists():
        return idx
    for shard in root.rglob("*.json"):
        try:
            data = json.loads(shard.read_text())
        except json.JSONDecodeError:
            continue
        for rec in data.get("records", []):
            pid = rec.get("pattern_id")
            if pid:
                idx[pid] = shard
    return idx


def _bump_stamp(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / ".version").write_text(str(time.time_ns()) + "\n")


def _append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(row) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _convert_v1_record(v1: dict) -> dict:
    hints = v1.get("avoidance_hints") or []
    hint_desc = "; ".join(
        hint.get("kind", "") + (
            f"={hint.get('package') or hint.get('value') or ''}"
            if (hint.get("package") or hint.get("value"))
            else ""
        )
        for hint in hints
        if isinstance(hint, dict)
    )
    return {
        "ecosystem": v1.get("ecosystem", "unknown"),
        "error_class": v1.get("error_class", "unknown"),
        "description": v1.get("description") or v1.get("error_class", "user-contributed pattern"),
        "trigger_signals": {"stderr_regex": [v1["stderr_pattern"]] if v1.get("stderr_pattern") else []},
        "fix_path": {"description": hint_desc or "user-contributed avoidance", "fix_command": ""},
        "shortest_verification": {"command": ""},
    }


def _looks_like_v1(payload: dict) -> bool:
    if payload.get("schema_version") == 1:
        return True
    recs = payload.get("records") or []
    return bool(recs) and isinstance(recs[0], dict) and "stderr_pattern" in recs[0]


def cmd_submit(args: argparse.Namespace) -> int:
    paths.ensure_user_data()
    src = Path(args.file)
    if not src.exists():
        print(f"error: {src} not found", file=sys.stderr)
        return 1
    try:
        payload = json.loads(src.read_text())
    except json.JSONDecodeError as exc:
        print(f"error: invalid JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list) or not payload["records"]:
        print("error: expected a JSON object with a non-empty 'records' array", file=sys.stderr)
        return 1
    converted_from_v1 = False
    if _looks_like_v1(payload):
        payload = {"records": [_convert_v1_record(rec) for rec in payload["records"]]}
        converted_from_v1 = True
    fp = _fingerprint()
    ts = time.strftime("%Y%m%dT%H%M%S")
    sid = uuid.uuid4().hex[:8]
    now = int(time.time())
    for idx, rec in enumerate(payload["records"]):
        rec.setdefault("source", "community_submitted")
        rec["contributor_fingerprint"] = fp
        if not rec.get("pattern_id"):
            rec["pattern_id"] = f"community.{fp}.{ts}.{idx:03d}"
        rec.setdefault("submitted_at", now)
        rec.setdefault("agent_reproducibility", {"evidence": []})
        rec.setdefault("false_paths", [])
        rec.setdefault("applicability_bounds", {})
    per_record_errors = []
    for idx, rec in enumerate(payload["records"]):
        errs = validate_shape(rec)
        if errs:
            per_record_errors.append({"index": idx, "errors": errs})
    if per_record_errors:
        paths.inbox_dir().mkdir(parents=True, exist_ok=True)
        quarantine = paths.inbox_dir() / f"{ts}-{sid}-rejected.json"
        quarantine.write_text(json.dumps({
            "contributor_fingerprint": fp,
            "submitted_at": int(time.time()),
            "shape_errors": per_record_errors,
            "payload": payload,
        }, indent=2) + "\n")
        print(f"shape check failed ({len(per_record_errors)} record(s)); quarantined to {quarantine}", file=sys.stderr)
        return 2
    dst_dir = paths.candidate_packs_dir() / "community"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / f"{ts}-{fp[:8]}-{sid}.json"
    dst.write_text(json.dumps(payload, indent=2) + "\n")
    _bump_stamp(paths.candidate_packs_dir())
    print(f"ingested: {dst}")
    if converted_from_v1:
        print("note: converted from schema_version=1 (polaris_cli experience contribute) to v4 candidate shape")
    print(f"contributor_fingerprint: {fp}")
    print(f"pattern_ids: {[rec['pattern_id'] for rec in payload['records']]}")
    return 0


def cmd_confirm(args: argparse.Namespace) -> int:
    paths.ensure_user_data()
    idx = _load_candidate_index()
    if args.pattern_id not in idx:
        print(f"error: pattern_id {args.pattern_id} not in candidate pool", file=sys.stderr)
        return 1
    row = {
        "pattern_id": args.pattern_id,
        "validator_fingerprint": _fingerprint(),
        "confirmed_at": int(time.time()),
        "note": args.note or "",
    }
    _append_jsonl(paths.validations_dir() / f"{args.pattern_id}.jsonl", row)
    print(f"confirmed: {args.pattern_id} by {row['validator_fingerprint']}")
    return 0


def cmd_reject(args: argparse.Namespace) -> int:
    paths.ensure_user_data()
    idx = _load_candidate_index()
    if args.pattern_id not in idx:
        print(f"error: pattern_id {args.pattern_id} not in candidate pool", file=sys.stderr)
        return 1
    row = {
        "pattern_id": args.pattern_id,
        "validator_fingerprint": _fingerprint(),
        "rejected_at": int(time.time()),
        "reason": args.reason or "",
    }
    _append_jsonl(paths.rejects_dir() / f"{args.pattern_id}.jsonl", row)
    print(f"rejected: {args.pattern_id} by {row['validator_fingerprint']}")
    return 0


def _contributor_of(pid: str) -> str | None:
    shard = _load_candidate_index().get(pid)
    if not shard:
        return None
    data = json.loads(shard.read_text())
    for rec in data.get("records", []):
        if rec.get("pattern_id") == pid:
            return rec.get("contributor_fingerprint")
    return None


def _eligible(pid: str) -> tuple[bool, str]:
    confirms = _read_jsonl(paths.validations_dir() / f"{pid}.jsonl")
    rejects = _read_jsonl(paths.rejects_dir() / f"{pid}.jsonl")
    if rejects:
        return False, f"has {len(rejects)} reject(s)"
    contributor = _contributor_of(pid) or UPSTREAM_AUTHORED
    distinct = {row["validator_fingerprint"] for row in confirms}
    distinct.discard(contributor)
    if len(distinct) < PROMOTION_MIN_CONFIRMATIONS:
        return False, f"{len(distinct)} distinct non-contributor confirmations (need {PROMOTION_MIN_CONFIRMATIONS})"
    return True, f"{len(distinct)} distinct non-contributor confirmations, 0 rejects"


def cmd_promote(args: argparse.Namespace) -> int:
    paths.ensure_user_data()
    idx = _load_candidate_index()
    promoted: list[str] = []
    for pid, shard in sorted(idx.items()):
        ok, why = _eligible(pid)
        if args.verbose:
            print(f"  {pid}: {'PROMOTE' if ok else 'skip'} ({why})")
        if not ok:
            continue
        data = json.loads(shard.read_text())
        rec = next((row for row in data["records"] if row.get("pattern_id") == pid), None)
        if rec is None:
            continue
        rel = shard.relative_to(paths.candidate_packs_dir())
        dst = paths.community_packs_dir() / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            existing = json.loads(dst.read_text())
            if any(row.get("pattern_id") == pid for row in existing.get("records", [])):
                continue
            existing.setdefault("records", []).append(rec)
            dst.write_text(json.dumps(existing, indent=2) + "\n")
        else:
            dst.write_text(json.dumps({"schema_version": data.get("schema_version", 4), "records": [rec]}, indent=2) + "\n")
        data["records"] = [row for row in data["records"] if row.get("pattern_id") != pid]
        shard.write_text(json.dumps(data, indent=2) + "\n")
        log = {
            "pattern_id": pid,
            "promoted_at": int(time.time()),
            "confirmations": _read_jsonl(paths.validations_dir() / f"{pid}.jsonl"),
            "from": str(shard),
            "to": str(dst),
        }
        paths.promoted_dir().mkdir(parents=True, exist_ok=True)
        (paths.promoted_dir() / f"{pid}.json").write_text(json.dumps(log, indent=2) + "\n")
        promoted.append(pid)
    if promoted:
        _bump_stamp(paths.candidate_packs_dir())
        _bump_stamp(paths.community_packs_dir())
    print(f"promoted {len(promoted)} candidate(s)")
    for pid in promoted:
        print(f"  {pid}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    del args
    paths.ensure_user_data()
    idx = _load_candidate_index()
    print(f"candidate pool: {len(idx)} patterns in {paths.candidate_packs_dir()}")
    print(f"inbox submissions: {len(list(paths.inbox_dir().glob('*.json')))}")
    confirmable = 0
    ready = 0
    for pid in sorted(idx):
        confirms = _read_jsonl(paths.validations_dir() / f"{pid}.jsonl")
        rejects = _read_jsonl(paths.rejects_dir() / f"{pid}.jsonl")
        if confirms or rejects:
            confirmable += 1
            ok, why = _eligible(pid)
            if ok:
                ready += 1
            print(f"  {pid}: {len(confirms)} confirm / {len(rejects)} reject → {why}")
    print(f"candidates with activity: {confirmable}")
    print(f"candidates eligible for promotion: {ready}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="polaris")
    sub = parser.add_subparsers(dest="cmd", required=True)
    submit = sub.add_parser("submit", help="submit a new candidate pattern")
    submit.add_argument("file")
    submit.set_defaults(func=cmd_submit)
    confirm = sub.add_parser("confirm", help="confirm a candidate helped you")
    confirm.add_argument("pattern_id")
    confirm.add_argument("--note", default="")
    confirm.set_defaults(func=cmd_confirm)
    reject = sub.add_parser("reject", help="report a candidate as wrong or harmful")
    reject.add_argument("pattern_id")
    reject.add_argument("--reason", default="")
    reject.set_defaults(func=cmd_reject)
    promote = sub.add_parser("promote", help="promote eligible candidates to community")
    promote.add_argument("--verbose", action="store_true")
    promote.set_defaults(func=cmd_promote)
    status = sub.add_parser("status", help="show community state")
    status.set_defaults(func=cmd_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
