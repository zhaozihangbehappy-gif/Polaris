#!/usr/bin/env python3
from __future__ import annotations

import json
import socket
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from hardening import (
    HardeningSettings,
    append_summary_chain,
    load_hardening_settings,
    publish_remote_anchor,
)


class FakeSinkHandler(BaseHTTPRequestHandler):
    server_version = "FakeRemoteAnchor/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        auth = self.headers.get("Authorization", "")
        if self.path != "/append":
            self.send_response(404)
            self.end_headers()
            return
        if auth != "Bearer publish-secret":
            self.send_response(403)
            self.end_headers()
            return
        payload = json.loads(body or "{}")
        sequence = len(self.server.records) + 1  # type: ignore[attr-defined]
        stored = {
            "remote_sequence": sequence,
            "remote_record_id": f"remote-{sequence}",
            "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "payload": payload,
        }
        self.server.records.append(stored)  # type: ignore[attr-defined]
        response = {
            "remote_sequence": sequence,
            "remote_record_id": f"remote-{sequence}",
            "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        raw = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/verify":
            self.send_response(404)
            self.end_headers()
            return
        auth = self.headers.get("Authorization", "")
        if auth != "Bearer verify-secret":
            self.send_response(403)
            self.end_headers()
            return
        room_id = (parse_qs(parsed.query).get("room_id") or [""])[0]
        records = [record for record in self.server.records if ((record.get("payload") or {}).get("room_id") == room_id)]  # type: ignore[attr-defined]
        raw = json.dumps({"room_id": room_id, "records": records}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class FakeSinkServer(ThreadingHTTPServer):
    def __init__(self, server_address):
        super().__init__(server_address, FakeSinkHandler)
        self.records: list[dict[str, object]] = []


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


def _write_conf(root: Path, publish_mode: str, publish_url: str) -> Path:
    conf = root / "trialogue-v2.conf"
    conf.write_text(
        "\n".join(
            [
                f"WORKSPACE={root}",
                f"AUDIT_LOG={root / 'audit' / 'audit.jsonl'}",
                f"TRIALOGUE_STATE_ROOT={root / 'state'}",
                f"HARDENING_SUMMARY_CHAIN_DIR={root / 'audit' / 'summary-chain'}",
                f"HARDENING_REMOTE_AUDIT_PUBLISH={publish_mode}",
                f"HARDENING_REMOTE_AUDIT_PUBLISH_URL={publish_url}",
                f"HARDENING_REMOTE_AUDIT_VERIFY_URL={publish_url.rsplit('/', 1)[0]}/verify",
                f"HARDENING_REMOTE_AUDIT_PUBLISH_CREDENTIAL_PATH={root / 'publish.token'}",
                f"HARDENING_REMOTE_AUDIT_VERIFY_CREDENTIAL_PATH={root / 'verify.token'}",
                f"HARDENING_REMOTE_AUDIT_BACKLOG_DIR={root / 'audit' / 'remote-backlog'}",
                "HARDENING_REMOTE_AUDIT_SOFT_CAP=2",
                "HARDENING_REMOTE_AUDIT_HARD_CAP=3",
                "HARDENING_REMOTE_AUDIT_DRAIN_BATCH_SIZE=10",
                "HARDENING_REMOTE_AUDIT_REQUEST_TIMEOUT_SEC=1",
                "HARDENING_REMOTE_AUDIT_VERIFY_INTERVAL_TURNS=10",
            ]
        ),
        encoding="utf-8",
    )
    (root / "publish.token").write_text("publish-secret\n", encoding="utf-8")
    (root / "verify.token").write_text("verify-secret\n", encoding="utf-8")
    return conf


def _record(idx: int) -> dict[str, object]:
    return {
        "timestamp": f"2026-03-23T00:00:0{idx}Z",
        "rid": f"rid-{idx}",
        "target": "claude",
        "target_name": "meeting",
        "target_source": "default",
        "target_path": "",
        "mode": "launcher_audit",
        "session_id": f"session-{idx}",
        "session_confirmed": True,
        "confirmation_method": "claude_session_file",
        "confirmation": {"turn_id": f"turn-{idx}", "thread_id": "thread-1"},
        "exit_code": 0,
        "binary_path": "/bin/claude",
        "binary_sha256": "abc",
        "cli_version": "claude",
        "version_gate_policy": "warn",
        "version_gate_allowed": True,
        "version_gate_reason": "",
        "version_recheck_policy": "warn",
        "version_recheck_allowed": True,
        "version_recheck_result": "match",
        "version_recheck_reason": "",
        "message_body": f"message-{idx}",
        "stdout": f"reply-{idx}",
        "stderr": "",
        "raw_event_log_path": "",
        "room_state_path": "",
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="trialogue-p2-publish-", dir="/tmp") as tmp_dir:
        root = Path(tmp_dir)
        port = _free_port()
        server = FakeSinkServer(("127.0.0.1", port))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        conf = _write_conf(root, "async", f"http://127.0.0.1:{port}/append")
        settings = load_hardening_settings(str(conf))

        chain1 = append_summary_chain(str(root / "audit" / "summary-chain"), _record(1), room_id="room-p2", source_mode="test")
        result1 = publish_remote_anchor(settings, chain1, room_id="room-p2")
        assert result1["status"] == "published"
        assert result1["backlog_count"] == 0
        assert result1["remote_sequence"] == 1

        server.shutdown()
        server.server_close()
        dead_port = port

        conf_dead = _write_conf(root, "async", f"http://127.0.0.1:{dead_port}/append")
        settings_dead = load_hardening_settings(str(conf_dead))
        chain2 = append_summary_chain(str(root / "audit" / "summary-chain"), _record(2), room_id="room-p2", source_mode="test")
        result2 = publish_remote_anchor(settings_dead, chain2, room_id="room-p2")
        assert result2["status"] == "backlogged"
        assert result2["backlog_count"] == 1

        server2 = FakeSinkServer(("127.0.0.1", dead_port))
        thread2 = threading.Thread(target=server2.serve_forever, daemon=True)
        thread2.start()
        chain3 = append_summary_chain(str(root / "audit" / "summary-chain"), _record(3), room_id="room-p2", source_mode="test")
        result3 = publish_remote_anchor(settings, chain3, room_id="room-p2")
        assert result3["status"] == "published"
        assert result3["drained_count"] == 1
        assert result3["backlog_count"] == 0
        assert len(server2.records) == 2

        conf_blocking = _write_conf(root, "blocking", f"http://127.0.0.1:{_free_port()}/append")
        settings_blocking = load_hardening_settings(str(conf_blocking))
        chain4 = append_summary_chain(str(root / "audit" / "summary-chain"), _record(4), room_id="room-block", source_mode="test")
        result4 = publish_remote_anchor(settings_blocking, chain4, room_id="room-block")
        assert result4["status"] == "unanchored"
        assert result4["backlog_count"] == 1

        # Missing publish credential is explicit and still preserves backlog.
        (root / "publish.token").unlink()
        chain5 = append_summary_chain(str(root / "audit" / "summary-chain"), _record(5), room_id="room-missing-token", source_mode="test")
        result5 = publish_remote_anchor(settings, chain5, room_id="room-missing-token")
        assert result5["status"] == "unconfigured"
        assert result5["reason"] == "remote publish credential missing"
        assert result5["backlog_count"] == 1

        server2.shutdown()
        server2.server_close()

    print("P2_PUBLISH_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
