#!/usr/bin/env python3
"""G0.2 — Verify tsan output matches hardening.py _sanitize_text_once() for all 130 benchmark payloads."""
from __future__ import annotations

import json
import os
import subprocess
import sys

# Add parent dir to path so we can import hardening and benchmark
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PARENT_DIR)

from hardening import _sanitize_text_once, DEFAULT_SANITIZER_PATTERNS
from hardening_injection_benchmark import (
    _ipi_payloads,
    _sms_payloads,
    _tki_payloads,
    _indirect_payloads,
    _benign_payloads,
)

TSAN_PATH = os.path.join(PARENT_DIR, "tsan")


def run_tsan_json(text: str) -> dict:
    result = subprocess.run(
        [sys.executable, TSAN_PATH, "--json"],
        input=text,
        capture_output=True,
        text=True,
        timeout=10,
    )
    # tsan exits 0 (no mods) or 1 (mods), both are valid
    if result.returncode == 2:
        raise RuntimeError(f"tsan error: {result.stderr}")
    return json.loads(result.stdout)


def main() -> int:
    all_payloads = (
        _ipi_payloads()
        + _sms_payloads()
        + _tki_payloads()
        + _indirect_payloads()
        + _benign_payloads()
    )
    patterns = dict(DEFAULT_SANITIZER_PATTERNS)

    passed = 0
    failed = 0
    errors = []

    for i, entry in enumerate(all_payloads):
        payload = entry["payload"]
        category = entry["category"]

        # v3 reference
        v3_cleaned, v3_mods, v3_removed = _sanitize_text_once(payload, patterns)

        # tsan
        try:
            tsan_out = run_tsan_json(payload)
        except Exception as e:
            errors.append(f"[{i}] {category}: tsan error: {e}")
            failed += 1
            continue

        tsan_cleaned = tsan_out["cleaned"]
        tsan_mods = tsan_out["modifications"]
        tsan_removed = tsan_out["removed"]

        # Compare
        if tsan_cleaned != v3_cleaned:
            errors.append(
                f"[{i}] {category}: CLEANED MISMATCH\n"
                f"  v3:   {repr(v3_cleaned[:100])}\n"
                f"  tsan: {repr(tsan_cleaned[:100])}"
            )
            failed += 1
        elif tsan_mods != v3_mods:
            errors.append(
                f"[{i}] {category}: MOD COUNT MISMATCH v3={v3_mods} tsan={tsan_mods}"
            )
            failed += 1
        elif sorted(tsan_removed) != sorted(v3_removed):
            errors.append(
                f"[{i}] {category}: REMOVED MISMATCH\n"
                f"  v3:   {sorted(v3_removed)}\n"
                f"  tsan: {sorted(tsan_removed)}"
            )
            failed += 1
        else:
            passed += 1

    print(f"tsan vs v3 parity: {passed}/{len(all_payloads)} passed, {failed} failed")
    if errors:
        print("\nFailures:")
        for e in errors:
            print(f"  {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
