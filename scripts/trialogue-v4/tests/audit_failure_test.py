#!/usr/bin/env python3
"""Audit chain failure visibility test.

Verifies that when the audit chain fails (e.g. bad permissions, corrupted chain),
the failure is surfaced in the pipeline result metadata, not silently swallowed.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PARENT_DIR)

import audit as _audit_mod
import config as _config_mod

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL: {name} — {detail}")


# ── Setup: redirect chain dir to a read-only location to force failure ───────

tmpdir = tempfile.mkdtemp(prefix="audit_fail_test_")
orig_chain_dir = _audit_mod.DEFAULT_CHAIN_DIR

# Also ensure config singleton says audit_mode=local
orig_conf = _config_mod._conf
_config_mod._conf = {"audit_mode": "local", "search_endpoint": "", "max_response_bytes": "524288",
                      "default_timeout": "15", "sanitizer_mode": "strict",
                      "remote_anchor_url": "", "remote_anchor_token_path": ""}

try:
    from fixtures.server import FixtureServer
    from pipeline import pipeline_fetch

    # ── Normal audit: audit_status=ok ────────────────────────────────────────

    ok_dir = os.path.join(tmpdir, "ok-chain")
    _audit_mod.DEFAULT_CHAIN_DIR = ok_dir

    with FixtureServer() as srv:
        result = pipeline_fetch(srv.url("/clean.html"), via_guard=True)
    check("normal: audit_status=ok", result.get("audit_status") == "ok",
          f"got: {result.get('audit_status')}")
    check("normal: has audit_seq", isinstance(result.get("audit_seq"), int),
          f"got: {result.get('audit_seq')}")
    check("normal: no audit_error", "audit_error" not in result,
          f"keys: {[k for k in result if 'audit' in k]}")

    # ── Forced failure: read-only dir ────────────────────────────────────────

    bad_dir = os.path.join(tmpdir, "bad-chain")
    os.makedirs(bad_dir)
    os.chmod(bad_dir, 0o000)  # no permissions
    _audit_mod.DEFAULT_CHAIN_DIR = bad_dir

    with FixtureServer() as srv:
        result = pipeline_fetch(srv.url("/clean.html"), via_guard=True)
    check("failure: audit_status=failed", result.get("audit_status") == "failed",
          f"got: {result.get('audit_status')}")
    check("failure: has audit_error", "audit_error" in result,
          f"keys: {[k for k in result if 'audit' in k]}")
    check("failure: cleaned_text still present", len(result.get("cleaned_text", "")) > 0,
          f"cleaned_text empty")
    # The fetch itself should still succeed — audit failure doesn't kill the pipeline
    check("failure: fetch not broken", "Clean Page" in result.get("cleaned_text", ""),
          f"got: {result.get('cleaned_text', '')[:100]}")

    os.chmod(bad_dir, 0o755)  # restore so cleanup works

    # ── Strict mode: audit failure blocks pipeline ───────────────────────────

    strict_bad_dir = os.path.join(tmpdir, "strict-bad-chain")
    os.makedirs(strict_bad_dir)
    os.chmod(strict_bad_dir, 0o000)
    _audit_mod.DEFAULT_CHAIN_DIR = strict_bad_dir
    _config_mod._conf["audit_mode"] = "strict"

    with FixtureServer() as srv:
        result = pipeline_fetch(srv.url("/clean.html"), via_guard=True)
    check("strict+fail: audit_status=failed", result.get("audit_status") == "failed",
          f"got: {result.get('audit_status')}")
    check("strict+fail: has error field", "error" in result,
          f"keys: {list(result.keys())}")
    check("strict+fail: cleaned_text is empty", result.get("cleaned_text") == "",
          f"got: {repr(result.get('cleaned_text', 'MISSING')[:100])}")
    check("strict+fail: has audit_error", "audit_error" in result,
          f"keys: {[k for k in result if 'audit' in k]}")

    os.chmod(strict_bad_dir, 0o755)

    # ── Strict mode: audit success returns content normally ────────────────

    strict_ok_dir = os.path.join(tmpdir, "strict-ok-chain")
    _audit_mod.DEFAULT_CHAIN_DIR = strict_ok_dir
    _config_mod._conf["audit_mode"] = "strict"

    with FixtureServer() as srv:
        result = pipeline_fetch(srv.url("/clean.html"), via_guard=True)
    check("strict+ok: audit_status=ok", result.get("audit_status") == "ok",
          f"got: {result.get('audit_status')}")
    check("strict+ok: cleaned_text present", len(result.get("cleaned_text", "")) > 0,
          f"cleaned_text empty")
    check("strict+ok: no error field", "error" not in result,
          f"keys: {list(result.keys())}")

    # ── Disabled audit: audit_status=disabled ────────────────────────────────

    _config_mod._conf["audit_mode"] = "disabled"
    _audit_mod.DEFAULT_CHAIN_DIR = ok_dir

    with FixtureServer() as srv:
        result = pipeline_fetch(srv.url("/clean.html"), via_guard=True)
    check("disabled: audit_status=disabled", result.get("audit_status") == "disabled",
          f"got: {result.get('audit_status')}")
    check("disabled: no audit_error", "audit_error" not in result,
          f"keys: {[k for k in result if 'audit' in k]}")

finally:
    _audit_mod.DEFAULT_CHAIN_DIR = orig_chain_dir
    _config_mod._conf = orig_conf
    shutil.rmtree(tmpdir, ignore_errors=True)

# ── Summary ──────────────────────────────────────────────────────────────────

print(f"audit_failure_test: {passed}/{passed + failed} passed, {failed} failed")
sys.exit(1 if failed else 0)
