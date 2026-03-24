#!/usr/bin/env python3
"""G3.1-G3.5 — Ingestion audit chain tests."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PARENT_DIR)

from audit import (
    INGESTION_CHAIN_GENESIS_SHA256,
    append_ingestion_chain,
    build_ingestion_entry,
    verify_ingestion_chain,
)
from hardening import SUMMARY_CHAIN_GENESIS_SHA256
from pipeline import pipeline_fetch, pipeline_sanitize

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL: {name} — {detail}")


# ── Setup temp chain directory ───────────────────────────────────────────────

tmpdir = tempfile.mkdtemp(prefix="trialogue_chain_test_")

try:
    chain_dir = os.path.join(tmpdir, "ingestion-chain")

    # ── G3.1: Chain continuity — 10 sequential appends ───────────────────────

    for i in range(10):
        result = pipeline_sanitize(f"test content {i} [SYSTEM-PROMPT]evil{i}[/SYSTEM-PROMPT]")
        result["source_type"] = "fetch"
        result["source_url"] = f"https://example.com/page{i}"
        chain_result = append_ingestion_chain(
            result, chain_dir=chain_dir, chain_id="test-continuity"
        )
        check(f"G3.1: append seq {i+1}", chain_result["seq"] == i + 1,
              f"got seq={chain_result['seq']}")

    # Verify full chain
    chain_path = os.path.join(chain_dir, "test-continuity.jsonl")
    verify = verify_ingestion_chain(chain_path)
    check("G3.1: chain verified", verify["ok"], f"reason: {verify['reason']}")
    check("G3.1: 10 entries verified", verify["checked"] == 10,
          f"checked={verify['checked']}")

    # ── G3.2: Tamper detection ───────────────────────────────────────────────

    tamper_dir = os.path.join(tmpdir, "tamper-chain")
    os.makedirs(tamper_dir, exist_ok=True)

    # Build a 3-entry chain
    for i in range(3):
        result = pipeline_sanitize(f"tamper test {i}")
        append_ingestion_chain(result, chain_dir=tamper_dir, chain_id="tamper")

    tamper_path = os.path.join(tamper_dir, "tamper.jsonl")
    # Verify it's valid first
    verify = verify_ingestion_chain(tamper_path)
    check("G3.2: pre-tamper chain valid", verify["ok"], f"reason: {verify['reason']}")

    # Tamper with second entry's cleaned_sha256 — full verify detects it
    with open(tamper_path, "r") as f:
        lines = f.readlines()
    entry = json.loads(lines[1])
    entry["cleaned_sha256"] = "0000000000000000000000000000000000000000000000000000000000000000"
    lines[1] = json.dumps(entry) + "\n"
    with open(tamper_path, "w") as f:
        f.writelines(lines)

    verify = verify_ingestion_chain(tamper_path)
    check("G3.2: mid-chain tamper detected", not verify["ok"], f"reason: {verify['reason']}")
    check("G3.2: tamper at seq 2", "seq 2" in verify["reason"],
          f"reason: {verify['reason']}")

    # Tamper with LAST entry — append detects it
    tamper_dir2 = os.path.join(tmpdir, "tamper-chain2")
    os.makedirs(tamper_dir2, exist_ok=True)
    for i in range(3):
        result = pipeline_sanitize(f"tamper2 test {i}")
        append_ingestion_chain(result, chain_dir=tamper_dir2, chain_id="tamper2")

    tamper_path2 = os.path.join(tamper_dir2, "tamper2.jsonl")
    with open(tamper_path2, "r") as f:
        lines = f.readlines()
    last_entry = json.loads(lines[-1])
    last_entry["cleaned_sha256"] = "0000000000000000000000000000000000000000000000000000000000000000"
    lines[-1] = json.dumps(last_entry) + "\n"
    with open(tamper_path2, "w") as f:
        f.writelines(lines)

    try:
        result = pipeline_sanitize("after tamper")
        append_ingestion_chain(result, chain_dir=tamper_dir2, chain_id="tamper2")
        check("G3.2: append after last-entry tamper raises", False, "should have raised ValueError")
    except ValueError as e:
        check("G3.2: append after last-entry tamper raises", "integrity" in str(e).lower(),
              f"error: {e}")

    # ── G3.4: Broker chain isolation ─────────────────────────────────────────

    check("G3.4: genesis hashes differ",
          INGESTION_CHAIN_GENESIS_SHA256 != SUMMARY_CHAIN_GENESIS_SHA256,
          "ingestion and summary genesis should differ")

    # Chain files are in different directories by design
    check("G3.4: chain dir is ingestion-chain",
          "ingestion-chain" in chain_dir,
          f"got: {chain_dir}")

    # ── G3.5: via_guard field ────────────────────────────────────────────────

    guard_dir = os.path.join(tmpdir, "guard-chain")

    # via_guard=True (MCP/hook path)
    result_guard = pipeline_sanitize("guard test")
    result_guard["via_guard"] = True  # simulate MCP path
    chain_result = append_ingestion_chain(
        result_guard, chain_dir=guard_dir, chain_id="guard"
    )
    check("G3.5: via_guard=True recorded",
          chain_result["entry"]["via_guard"] is True,
          f"got: {chain_result['entry']['via_guard']}")

    # via_guard=False (CLI fallback)
    result_cli = pipeline_sanitize("cli test")
    result_cli["via_guard"] = False  # simulate CLI path
    chain_result = append_ingestion_chain(
        result_cli, chain_dir=guard_dir, chain_id="guard"
    )
    check("G3.5: via_guard=False recorded",
          chain_result["entry"]["via_guard"] is False,
          f"got: {chain_result['entry']['via_guard']}")

    # ── Entry structure validation ───────────────────────────────────────────

    entry = chain_result["entry"]
    check("entry: has schema", entry["schema"] == "trialogue_ingestion_chain_entry_v1",
          f"got: {entry['schema']}")
    check("entry: has seq", isinstance(entry["seq"], int), f"got: {type(entry['seq'])}")
    check("entry: has timestamp", "T" in entry["timestamp"], f"got: {entry['timestamp']}")
    check("entry: has source_type", "source_type" in entry, f"keys: {list(entry.keys())}")
    check("entry: has raw_sha256", len(entry.get("raw_sha256", "")) == 64,
          f"got len: {len(entry.get('raw_sha256', ''))}")
    check("entry: has cleaned_sha256", len(entry.get("cleaned_sha256", "")) == 64,
          f"got len: {len(entry.get('cleaned_sha256', ''))}")
    check("entry: has entry_sha256", len(entry.get("entry_sha256", "")) == 64,
          f"got len: {len(entry.get('entry_sha256', ''))}")
    check("entry: has prev_entry_sha256", len(entry.get("prev_entry_sha256", "")) == 64,
          f"got len: {len(entry.get('prev_entry_sha256', ''))}")

    # ── Empty chain verification ─────────────────────────────────────────────

    empty_path = os.path.join(tmpdir, "nonexistent.jsonl")
    verify = verify_ingestion_chain(empty_path)
    check("empty chain: ok", verify["ok"], f"reason: {verify['reason']}")
    check("empty chain: 0 checked", verify["checked"] == 0,
          f"checked: {verify['checked']}")

    # ── First entry links to genesis ─────────────────────────────────────────

    genesis_dir = os.path.join(tmpdir, "genesis-chain")
    result = pipeline_sanitize("genesis test")
    chain_result = append_ingestion_chain(result, chain_dir=genesis_dir, chain_id="gen")
    check("first entry: prev is genesis",
          chain_result["prev_entry_sha256"] == INGESTION_CHAIN_GENESIS_SHA256,
          f"got: {chain_result['prev_entry_sha256'][:32]}...")

finally:
    shutil.rmtree(tmpdir, ignore_errors=True)

# ── Summary ──────────────────────────────────────────────────────────────────

print(f"ingestion_chain_test: {passed}/{passed + failed} passed, {failed} failed")
sys.exit(1 if failed else 0)
