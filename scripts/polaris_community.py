#!/usr/bin/env python3
"""Polaris community promotion channel.

Subcommands:
  submit    — user contributes a new candidate pattern
  confirm   — user reports a candidate helped them avoid a loop (validation hit)
  reject    — user reports a candidate is wrong / harmful
  promote   — check promotion rules and move eligible candidates to community
  status    — show counts and per-candidate tallies

Promotion rule: a candidate is eligible for community only if
  (a) it currently lives in experience-packs-v4-candidates/
  (b) >=2 confirmations from DISTINCT validator_fingerprints,
      none of which equals the original contributor_fingerprint
  (c) zero reject entries

Identity: contributor_fingerprint / validator_fingerprint = sha256 of a per-host
salt file at ~/.polaris/contributor_salt, truncated to 16 hex. Best-effort; we
explicitly do not claim this resists deliberate sybil attempts. See
community/README.md for the trust caveat.
"""
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

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from pattern_schema import validate_shape  # noqa: E402

CANDIDATE_DIR = REPO / "experience-packs-v4-candidates"
COMMUNITY_PACK_DIR = REPO / "experience-packs-v4-community"
OFFICIAL_DIR = REPO / "experience-packs-v4"
COMMUNITY = REPO / "community"
INBOX = COMMUNITY / "inbox"
VALIDATIONS = COMMUNITY / "validations"
REJECTS = COMMUNITY / "rejects"
PROMOTED = COMMUNITY / "promoted"

PROMOTION_MIN_CONFIRMATIONS = 2
UPSTREAM_AUTHORED = "upstream_authored"


def _salt_path() -> Path:
    return Path.home() / ".polaris" / "contributor_salt"


def _fingerprint() -> str:
    p = _salt_path()
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(secrets.token_hex(32))
        try:
            os.chmod(p, 0o600)
        except OSError:
            pass
    return hashlib.sha256(p.read_text().strip().encode()).hexdigest()[:16]


def _load_candidate_index() -> dict[str, Path]:
    idx = {}
    if not CANDIDATE_DIR.exists():
        return idx
    for shard in CANDIDATE_DIR.rglob("*.json"):
        data = json.loads(shard.read_text())
        for rec in data.get("records", []):
            pid = rec.get("pattern_id")
            if pid:
                idx[pid] = shard
    return idx


def _append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(row) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def _convert_v1_record(v1: dict) -> dict:
    """Convert a polaris_cli experience-contribute (schema_version=1) record
    into a v4 candidate record. Best-effort: preserves stderr_pattern as a
    trigger regex and turns avoidance_hints into a fix_path description.
    """
    hints = v1.get("avoidance_hints") or []
    hint_desc = "; ".join(
        h.get("kind", "") + (f"={h.get('package') or h.get('value') or ''}" if (h.get("package") or h.get("value")) else "")
        for h in hints if isinstance(h, dict)
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
    src = Path(args.file)
    if not src.exists():
        print(f"error: {src} not found", file=sys.stderr)
        return 1
    try:
        payload = json.loads(src.read_text())
    except json.JSONDecodeError as e:
        print(f"error: invalid JSON: {e}", file=sys.stderr)
        return 1
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list) or not payload["records"]:
        print("error: expected a JSON object with a non-empty 'records' array", file=sys.stderr)
        return 1

    converted_from_v1 = False
    if _looks_like_v1(payload):
        payload = {"records": [_convert_v1_record(r) for r in payload["records"]]}
        converted_from_v1 = True

    fp = _fingerprint()
    ts = time.strftime("%Y%m%dT%H%M%S")
    sid = uuid.uuid4().hex[:8]
    now = int(time.time())

    # Stamp defaults BEFORE shape check so the user isn't required to
    # supply fields the channel assigns (source, pattern_id, contributor_fingerprint).
    for i, rec in enumerate(payload["records"]):
        rec.setdefault("source", "community_submitted")
        rec["contributor_fingerprint"] = fp
        if not rec.get("pattern_id"):
            rec["pattern_id"] = f"community.{fp}.{ts}.{i:03d}"
        rec.setdefault("submitted_at", now)
        rec.setdefault("agent_reproducibility", {"evidence": []})
        rec.setdefault("false_paths", [])
        rec.setdefault("applicability_bounds", {})

    per_record_errors = []
    for i, rec in enumerate(payload["records"]):
        errs = validate_shape(rec)
        if errs:
            per_record_errors.append({"index": i, "errors": errs})
    if per_record_errors:
        INBOX.mkdir(parents=True, exist_ok=True)
        quarantine = INBOX / f"{ts}-{sid}-rejected.json"
        quarantine.write_text(json.dumps({
            "contributor_fingerprint": fp,
            "submitted_at": int(time.time()),
            "shape_errors": per_record_errors,
            "payload": payload,
        }, indent=2) + "\n")
        print(f"shape check failed ({len(per_record_errors)} record(s)); quarantined to {quarantine.relative_to(REPO)}", file=sys.stderr)
        return 2

    dst_dir = CANDIDATE_DIR / "community"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / f"{ts}-{fp[:8]}-{sid}.json"
    dst.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"ingested: {dst.relative_to(REPO)}")
    if converted_from_v1:
        print("note: converted from schema_version=1 (polaris_cli experience contribute) to v4 candidate shape")
    print(f"contributor_fingerprint: {fp}")
    print(f"pattern_ids: {[r['pattern_id'] for r in payload['records']]}")
    return 0


def cmd_confirm(args: argparse.Namespace) -> int:
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
    _append_jsonl(VALIDATIONS / f"{args.pattern_id}.jsonl", row)
    print(f"confirmed: {args.pattern_id} by {row['validator_fingerprint']}")
    return 0


def cmd_reject(args: argparse.Namespace) -> int:
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
    _append_jsonl(REJECTS / f"{args.pattern_id}.jsonl", row)
    print(f"rejected: {args.pattern_id} by {row['validator_fingerprint']}")
    return 0


def _contributor_of(pid: str) -> str | None:
    # Candidates in this repo are authored; their original "contributor" is the
    # upstream author. For community-submitted candidates, we stamp
    # contributor_fingerprint into the shard's record at ingest time.
    idx = _load_candidate_index()
    shard = idx.get(pid)
    if not shard:
        return None
    data = json.loads(shard.read_text())
    for rec in data.get("records", []):
        if rec.get("pattern_id") == pid:
            return rec.get("contributor_fingerprint")
    return None


def _eligible(pid: str) -> tuple[bool, str]:
    confirms = _read_jsonl(VALIDATIONS / f"{pid}.jsonl")
    rejects = _read_jsonl(REJECTS / f"{pid}.jsonl")
    if rejects:
        return False, f"has {len(rejects)} reject(s)"
    contributor = _contributor_of(pid) or UPSTREAM_AUTHORED
    distinct = {c["validator_fingerprint"] for c in confirms}
    distinct.discard(contributor)
    if len(distinct) < PROMOTION_MIN_CONFIRMATIONS:
        return False, f"{len(distinct)} distinct non-contributor confirmations (need {PROMOTION_MIN_CONFIRMATIONS})"
    return True, f"{len(distinct)} distinct non-contributor confirmations, 0 rejects"


def cmd_promote(args: argparse.Namespace) -> int:
    idx = _load_candidate_index()
    promoted = []
    for pid, shard in sorted(idx.items()):
        ok, why = _eligible(pid)
        if args.verbose:
            print(f"  {pid}: {'PROMOTE' if ok else 'skip'} ({why})")
        if not ok:
            continue
        data = json.loads(shard.read_text())
        rec = next((r for r in data["records"] if r.get("pattern_id") == pid), None)
        if not rec:
            continue
        rel = shard.relative_to(CANDIDATE_DIR)
        dst = COMMUNITY_PACK_DIR / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            off = json.loads(dst.read_text())
            if any(r.get("pattern_id") == pid for r in off.get("records", [])):
                continue
            off.setdefault("records", []).append(rec)
            dst.write_text(json.dumps(off, indent=2) + "\n")
        else:
            dst.write_text(json.dumps({"schema_version": data.get("schema_version"), "records": [rec]}, indent=2) + "\n")
        # remove from candidate shard
        data["records"] = [r for r in data["records"] if r.get("pattern_id") != pid]
        shard.write_text(json.dumps(data, indent=2) + "\n")
        # audit log
        log = {
            "pattern_id": pid,
            "promoted_at": int(time.time()),
            "confirmations": _read_jsonl(VALIDATIONS / f"{pid}.jsonl"),
            "from": str(shard.relative_to(REPO)),
            "to": str(dst.relative_to(REPO)),
        }
        (PROMOTED / f"{pid}.json").parent.mkdir(parents=True, exist_ok=True)
        (PROMOTED / f"{pid}.json").write_text(json.dumps(log, indent=2) + "\n")
        promoted.append(pid)
    print(f"promoted {len(promoted)} candidate(s)")
    for pid in promoted:
        print(f"  {pid}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    idx = _load_candidate_index()
    print(f"candidate pool: {len(idx)} patterns in {CANDIDATE_DIR.relative_to(REPO)}")
    print(f"inbox submissions: {len(list(INBOX.glob('*.json'))) if INBOX.exists() else 0}")
    confirmable = 0
    ready = 0
    for pid in sorted(idx):
        confirms = _read_jsonl(VALIDATIONS / f"{pid}.jsonl")
        rejects = _read_jsonl(REJECTS / f"{pid}.jsonl")
        if confirms or rejects:
            confirmable += 1
            ok, why = _eligible(pid)
            if ok:
                ready += 1
            if args.verbose:
                print(f"  {pid}: {len(confirms)} confirm / {len(rejects)} reject → {why}")
    print(f"candidates with activity: {confirmable}")
    print(f"candidates eligible for promotion: {ready}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="polaris_community")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("submit", help="submit a new candidate pattern")
    s.add_argument("file", help="path to contribution JSON")
    s.set_defaults(func=cmd_submit)

    s = sub.add_parser("confirm", help="confirm a candidate helped you")
    s.add_argument("pattern_id")
    s.add_argument("--note", default="")
    s.set_defaults(func=cmd_confirm)

    s = sub.add_parser("reject", help="report a candidate is wrong / unhelpful")
    s.add_argument("pattern_id")
    s.add_argument("--reason", default="")
    s.set_defaults(func=cmd_reject)

    s = sub.add_parser("promote", help="promote eligible candidates to official")
    s.add_argument("--verbose", action="store_true")
    s.set_defaults(func=cmd_promote)

    s = sub.add_parser("status", help="show community channel state")
    s.add_argument("--verbose", action="store_true")
    s.set_defaults(func=cmd_status)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
