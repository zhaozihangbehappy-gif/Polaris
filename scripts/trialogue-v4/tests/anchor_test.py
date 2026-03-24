#!/usr/bin/env python3
"""V4-C2 — Remote audit anchor tests.

Tests publish_ingestion_anchor() with both webhook and file sinks.
Uses a local fixture HTTP server for webhook tests and tmpdir for file tests.
"""
from __future__ import annotations

import http.server
import json
import os
import shutil
import sys
import tempfile
import threading
from typing import Any

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


# ── Webhook sink fixture ─────────────────────────────────────────────────────

_webhook_payloads: list[dict] = []


class _WebhookHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            _webhook_payloads.append(json.loads(body))
        except Exception:
            pass

        if self.path == "/fail":
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"Internal Server Error")
            return

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, fmt, *args):
        pass


class _WebhookServer:
    def __init__(self):
        self._server = http.server.HTTPServer(("127.0.0.1", 0), _WebhookHandler)
        self.port = self._server.server_address[1]
        self._thread = None

    def __enter__(self):
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *args):
        self._server.shutdown()
        if self._thread:
            self._thread.join(timeout=5)

    def url(self, path: str = "/anchor") -> str:
        return f"http://127.0.0.1:{self.port}{path}"


# ── Setup ─────────────────────────────────────────────────────────────────────

tmpdir = tempfile.mkdtemp(prefix="anchor_test_")
orig_chain_dir = _audit_mod.DEFAULT_CHAIN_DIR
orig_conf = _config_mod._conf

try:
    chain_dir = os.path.join(tmpdir, "chain")
    _audit_mod.DEFAULT_CHAIN_DIR = chain_dir

    # Populate chain with a couple of entries
    _config_mod._conf = dict(_config_mod.DEFAULTS)
    _config_mod._conf["audit_mode"] = "local"

    from pipeline import ingest
    for i in range(3):
        result = ingest(f"test content {i}", source_type="test", source_url=f"http://test/{i}")
        _audit_mod.append_ingestion_chain(result)

    chain_path = os.path.join(chain_dir, "default.jsonl")
    check("setup: chain has 3 entries", os.path.exists(chain_path), "chain file missing")

    # ── File sink: publish to local file ──────────────────────────────────────

    anchor_file = os.path.join(tmpdir, "anchors.jsonl")

    result = _audit_mod.publish_ingestion_anchor(
        chain_dir=chain_dir,
        sink_type="file",
        sink_url=anchor_file,
    )
    check("file sink: ok=True", result.get("ok") is True,
          f"got: {result}")
    check("file sink: anchor has seq=3", result.get("anchor", {}).get("seq") == 3,
          f"got: {result.get('anchor', {}).get('seq')}")
    check("file sink: anchor has head_sha256", len(result.get("anchor", {}).get("head_sha256", "")) == 64,
          f"got: {result.get('anchor', {}).get('head_sha256', '')[:20]}")
    check("file sink: anchor file created", os.path.exists(anchor_file),
          f"file: {anchor_file}")

    if os.path.exists(anchor_file):
        with open(anchor_file) as f:
            lines = [l for l in f if l.strip()]
        check("file sink: 1 anchor line", len(lines) == 1,
              f"got {len(lines)} lines")
        anchor_data = json.loads(lines[0])
        check("file sink: chain_id=default", anchor_data.get("chain_id") == "default",
              f"got: {anchor_data.get('chain_id')}")

    # Publish again → appends second line
    result2 = _audit_mod.publish_ingestion_anchor(
        chain_dir=chain_dir,
        sink_type="file",
        sink_url=anchor_file,
    )
    check("file sink 2nd: ok=True", result2.get("ok") is True, f"got: {result2}")
    with open(anchor_file) as f:
        lines = [l for l in f if l.strip()]
    check("file sink: 2 anchor lines after 2nd publish", len(lines) == 2,
          f"got {len(lines)}")

    # ── Webhook sink: publish to local server ─────────────────────────────────

    _webhook_payloads.clear()

    with _WebhookServer() as ws:
        result = _audit_mod.publish_ingestion_anchor(
            chain_dir=chain_dir,
            sink_type="webhook",
            sink_url=ws.url("/anchor"),
        )
        check("webhook: ok=True", result.get("ok") is True,
              f"got: {result}")
        check("webhook: publish status=200", result.get("publish", {}).get("status") == 200,
              f"got: {result.get('publish', {}).get('status')}")
        check("webhook: payload received", len(_webhook_payloads) == 1,
              f"payloads: {len(_webhook_payloads)}")
        if _webhook_payloads:
            check("webhook: payload has head_sha256",
                  len(_webhook_payloads[0].get("head_sha256", "")) == 64,
                  f"got: {_webhook_payloads[0].get('head_sha256', '')[:20]}")

    # ── Webhook failure ───────────────────────────────────────────────────────

    with _WebhookServer() as ws:
        result = _audit_mod.publish_ingestion_anchor(
            chain_dir=chain_dir,
            sink_type="webhook",
            sink_url=ws.url("/fail"),
        )
        check("webhook fail: ok=False", result.get("ok") is False,
              f"got: {result}")
        check("webhook fail: has error", "error" in result.get("publish", {}),
              f"publish: {result.get('publish', {})}")

    # ── No sink configured ────────────────────────────────────────────────────

    result = _audit_mod.publish_ingestion_anchor(
        chain_dir=chain_dir,
        sink_type="",
        sink_url="",
    )
    check("no sink: ok=False", result.get("ok") is False, f"got: {result}")
    check("no sink: has error msg", "error" in result, f"keys: {list(result.keys())}")

    # ── Unknown sink type ─────────────────────────────────────────────────────

    result = _audit_mod.publish_ingestion_anchor(
        chain_dir=chain_dir,
        sink_type="s3",
        sink_url="s3://bucket/prefix",
    )
    check("unknown sink: ok=False", result.get("ok") is False, f"got: {result}")

    # ── Empty chain anchor ────────────────────────────────────────────────────

    empty_dir = os.path.join(tmpdir, "empty-chain")
    anchor_empty = os.path.join(tmpdir, "empty-anchors.jsonl")
    result = _audit_mod.publish_ingestion_anchor(
        chain_dir=empty_dir,
        chain_id="empty",
        sink_type="file",
        sink_url=anchor_empty,
    )
    check("empty chain: ok=True", result.get("ok") is True, f"got: {result}")
    check("empty chain: seq=0", result.get("anchor", {}).get("seq") == 0,
          f"got: {result.get('anchor', {}).get('seq')}")
    check("empty chain: head=genesis",
          result.get("anchor", {}).get("head_sha256") == _audit_mod.INGESTION_CHAIN_GENESIS_SHA256,
          f"got: {result.get('anchor', {}).get('head_sha256', '')[:20]}")

finally:
    _audit_mod.DEFAULT_CHAIN_DIR = orig_chain_dir
    _config_mod._conf = orig_conf
    shutil.rmtree(tmpdir, ignore_errors=True)

# ── Summary ──────────────────────────────────────────────────────────────────

print(f"anchor_test: {passed}/{passed + failed} passed, {failed} failed")
sys.exit(1 if failed else 0)
