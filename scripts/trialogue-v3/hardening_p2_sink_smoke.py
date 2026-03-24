#!/usr/bin/env python3
from __future__ import annotations

import json
import socket
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

from remote_anchor_sink import SinkServer, SinkStore


def free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


def http_json(method: str, url: str, *, token: str = "", payload: dict | None = None) -> tuple[int, dict]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def payload(room_id: str, rid: str, prev_sha: str, turn_sha: str) -> dict:
    return {
        "schema": "trialogue_remote_anchor_publish_v1",
        "room_id": room_id,
        "rid": rid,
        "target": "claude",
        "generated_at": "2026-03-23T12:00:00Z",
        "prev_summary_sha256": prev_sha,
        "turn_summary_sha256": turn_sha,
        "genesis_summary_sha256": "genesis-sha",
        "source_mode": "launcher_audit",
        "local_timestamp": "2026-03-23T12:00:00Z",
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="trialogue-sink-smoke-", dir="/tmp") as tmp_dir:
        root = Path(tmp_dir)
        publish_token = "publish-secret"
        verify_token = "verify-secret"
        db_path = root / "anchor.sqlite3"
        server = SinkServer(
            "127.0.0.1",
            free_port(),
            store=SinkStore(str(db_path)),
            publish_token=publish_token,
            verify_token=verify_token,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"

        status, body = http_json("GET", f"{base}/health")
        assert status == 200 and body["ok"] is True

        status, body = http_json("POST", f"{base}/append", token=publish_token, payload=payload("room-a", "rid-1", "g", "sha-1"))
        assert status == 200
        assert body["remote_sequence"] == 1

        status, body = http_json("POST", f"{base}/append", token=publish_token, payload=payload("room-a", "rid-2", "sha-1", "sha-2"))
        assert status == 200
        assert body["remote_sequence"] == 2

        status, body = http_json("POST", f"{base}/append", token=publish_token, payload=payload("room-b", "rid-1", "g", "sha-b1"))
        assert status == 200
        assert body["remote_sequence"] == 1

        status, body = http_json("POST", f"{base}/append", token=publish_token, payload=payload("room-a", "rid-2", "sha-1", "sha-2"))
        assert status == 200
        assert body["remote_sequence"] == 2

        status, body = http_json("POST", f"{base}/append", token=publish_token, payload=payload("room-a", "rid-2", "sha-1", "sha-2-diff"))
        assert status == 409

        status, body = http_json("GET", f"{base}/verify?room_id=room-a", token=verify_token)
        assert status == 200
        assert [record["remote_sequence"] for record in body["records"]] == [1, 2]

        status, body = http_json("GET", f"{base}/verify?room_id=room-a&after_sequence=1", token=verify_token)
        assert status == 200
        assert [record["remote_sequence"] for record in body["records"]] == [2]

        status, body = http_json("GET", f"{base}/verify?room_id=room-a", token=publish_token)
        assert status == 403
        status, body = http_json("POST", f"{base}/append", token=verify_token, payload=payload("room-z", "rid-z", "g", "sha-z"))
        assert status == 403

        server.shutdown()
        server.server_close()

    print("P2_SINK_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
