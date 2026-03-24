#!/usr/bin/env python3
"""Trialogue v4 — Ingestion audit chain.

Provides append_ingestion_chain() for recording each external content
ingestion into a local SHA-256 hash chain (JSONL).

Also provides publish_ingestion_anchor() for pushing chain head hashes
to an external sink (webhook or file) for tamper-evident remote audit.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from hardening import (
    append_jsonl,
    ensure_parent_dir,
    _last_jsonl_record,
    _load_jsonl_records,
    _rewrite_jsonl,
)

# Genesis hash — different from v3's to keep chains independent
INGESTION_CHAIN_GENESIS_SHA256 = hashlib.sha256(
    b"TRIALOGUE_V4_INGESTION_CHAIN_V1"
).hexdigest()

# Default chain directory (relative to script dir at runtime)
DEFAULT_CHAIN_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "state", "ingestion-chain"
)


def _canonical_bytes(entry: dict[str, Any]) -> bytes:
    """Canonical JSON encoding for hash computation."""
    return json.dumps(
        entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def build_ingestion_entry(
    ingest_result: dict[str, Any],
    *,
    seq: int,
    prev_entry_sha256: str,
) -> dict[str, Any]:
    """Build a single chain entry from a pipeline ingest result."""
    entry = {
        "schema": "trialogue_ingestion_chain_entry_v1",
        "seq": seq,
        "timestamp": ingest_result.get(
            "fetched_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        ),
        "source_type": ingest_result.get("source_type", ""),
        "source_url": ingest_result.get("source_url", ""),
        "raw_sha256": ingest_result.get("raw_sha256", ""),
        "cleaned_sha256": ingest_result.get("cleaned_sha256", ""),
        "modifications": ingest_result.get("modifications", 0),
        "removed": ingest_result.get("removed", []),
        "mode": ingest_result.get("mode", "strict"),
        "via_guard": ingest_result.get("via_guard", False),
        "prev_entry_sha256": prev_entry_sha256,
    }
    # Compute entry hash over all fields except entry_sha256 itself
    entry["entry_sha256"] = hashlib.sha256(_canonical_bytes(entry)).hexdigest()
    return entry


def append_ingestion_chain(
    ingest_result: dict[str, Any],
    *,
    chain_dir: str = "",
    chain_id: str = "default",
) -> dict[str, Any]:
    """Append an ingestion record to the hash chain.

    Returns dict with chain_path, entry, prev/current hashes.
    Raises ValueError if chain integrity is broken.
    """
    if not chain_dir:
        chain_dir = DEFAULT_CHAIN_DIR

    Path(chain_dir).mkdir(parents=True, exist_ok=True)
    chain_path = os.path.join(chain_dir, f"{chain_id}.jsonl")
    lock_path = f"{chain_path}.lock"
    ensure_parent_dir(lock_path)

    with open(lock_path, "a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

        # Read last entry
        last_record = _last_jsonl_record(chain_path)
        prev_sha = INGESTION_CHAIN_GENESIS_SHA256
        seq = 1

        if last_record:
            prev_sha = str(
                last_record.get("entry_sha256") or INGESTION_CHAIN_GENESIS_SHA256
            )
            seq = int(last_record.get("seq", 0)) + 1

            # Verify chain integrity: recompute last entry's hash
            verify_entry = dict(last_record)
            stored_hash = verify_entry.pop("entry_sha256", "")
            recomputed = hashlib.sha256(_canonical_bytes(verify_entry)).hexdigest()
            if stored_hash and recomputed != stored_hash:
                raise ValueError(
                    f"Chain integrity error at seq {last_record.get('seq')}: "
                    f"stored={stored_hash[:16]}... recomputed={recomputed[:16]}..."
                )

        entry = build_ingestion_entry(
            ingest_result, seq=seq, prev_entry_sha256=prev_sha
        )
        append_jsonl(chain_path, entry)

    return {
        "chain_path": chain_path,
        "entry": entry,
        "prev_entry_sha256": prev_sha,
        "entry_sha256": entry["entry_sha256"],
        "genesis_sha256": INGESTION_CHAIN_GENESIS_SHA256,
        "seq": seq,
    }


def verify_ingestion_chain(chain_path: str) -> dict[str, Any]:
    """Verify the full integrity of an ingestion chain file.

    Returns {"ok": bool, "checked": int, "reason": str}.
    """
    records = _load_jsonl_records(chain_path)
    if not records:
        return {"ok": True, "checked": 0, "reason": "empty chain"}

    prev_expected = INGESTION_CHAIN_GENESIS_SHA256

    for i, record in enumerate(records):
        # Check prev pointer
        if record.get("prev_entry_sha256") != prev_expected:
            return {
                "ok": False,
                "checked": i,
                "reason": (
                    f"seq {record.get('seq')}: prev_entry_sha256 mismatch — "
                    f"expected {prev_expected[:16]}..., "
                    f"got {record.get('prev_entry_sha256', '')[:16]}..."
                ),
            }

        # Verify entry hash
        verify = dict(record)
        stored_hash = verify.pop("entry_sha256", "")
        recomputed = hashlib.sha256(_canonical_bytes(verify)).hexdigest()
        if stored_hash != recomputed:
            return {
                "ok": False,
                "checked": i,
                "reason": (
                    f"seq {record.get('seq')}: entry_sha256 mismatch — "
                    f"stored {stored_hash[:16]}..., recomputed {recomputed[:16]}..."
                ),
            }

        # Check seq continuity
        if record.get("seq") != i + 1:
            return {
                "ok": False,
                "checked": i,
                "reason": f"seq discontinuity: expected {i + 1}, got {record.get('seq')}",
            }

        prev_expected = stored_hash

    return {"ok": True, "checked": len(records), "reason": ""}


# ── Remote audit anchor ──────────────────────────────────────────────────────


def _build_anchor_payload(
    chain_path: str,
    chain_id: str,
) -> dict[str, Any]:
    """Build the anchor payload from the current chain state."""
    records = _load_jsonl_records(chain_path)
    if not records:
        return {
            "chain_id": chain_id,
            "chain_path": chain_path,
            "seq": 0,
            "head_sha256": INGESTION_CHAIN_GENESIS_SHA256,
            "genesis_sha256": INGESTION_CHAIN_GENESIS_SHA256,
            "entry_count": 0,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    last = records[-1]
    return {
        "chain_id": chain_id,
        "chain_path": chain_path,
        "seq": last.get("seq", 0),
        "head_sha256": last.get("entry_sha256", ""),
        "genesis_sha256": INGESTION_CHAIN_GENESIS_SHA256,
        "entry_count": len(records),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _publish_to_webhook(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST anchor payload to a webhook URL."""
    import urllib.request
    import urllib.error

    data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return {"ok": True, "status": resp.status, "sink": "webhook", "url": url}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "sink": "webhook", "url": url,
                "error": str(e)}
    except Exception as e:
        return {"ok": False, "status": 0, "sink": "webhook", "url": url,
                "error": str(e)}


def _publish_to_file(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Append anchor payload to a local/shared file (JSONL)."""
    try:
        ensure_parent_dir(path)
        line = json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
        with open(path, "a", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            f.write(line)
        return {"ok": True, "sink": "file", "path": path}
    except Exception as e:
        return {"ok": False, "sink": "file", "path": path, "error": str(e)}


def publish_ingestion_anchor(
    *,
    chain_dir: str = "",
    chain_id: str = "default",
    sink_type: str = "",
    sink_url: str = "",
) -> dict[str, Any]:
    """Publish the current chain head hash to an external sink.

    sink_type: "webhook" or "file". If empty, reads from config.
    sink_url:  URL (webhook) or file path (file). If empty, reads from config.

    Returns {"ok": bool, "anchor": {...}, "publish": {...}}.
    """
    from config import get_conf

    if not chain_dir:
        chain_dir = DEFAULT_CHAIN_DIR
    if not sink_type:
        sink_type = get_conf().get("remote_anchor_sink", "")
    if not sink_url:
        sink_url = get_conf().get("remote_anchor_url", "")

    if not sink_type or not sink_url:
        return {
            "ok": False,
            "error": "No remote anchor sink configured (set remote_anchor_sink and remote_anchor_url in conf)",
        }

    chain_path = os.path.join(chain_dir, f"{chain_id}.jsonl")
    anchor = _build_anchor_payload(chain_path, chain_id)

    if sink_type == "webhook":
        pub = _publish_to_webhook(sink_url, anchor)
    elif sink_type == "file":
        pub = _publish_to_file(sink_url, anchor)
    else:
        return {
            "ok": False,
            "error": f"Unknown sink type: {sink_type} (must be 'webhook' or 'file')",
            "anchor": anchor,
        }

    return {
        "ok": pub.get("ok", False),
        "anchor": anchor,
        "publish": pub,
    }
