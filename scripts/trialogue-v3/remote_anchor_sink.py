#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_conf(path: str) -> dict[str, str]:
    conf: dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                conf[key.strip()] = value.strip()
    except FileNotFoundError:
        return conf
    return conf


def ensure_parent(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def read_token(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def validate_payload(payload: dict[str, Any]) -> tuple[bool, str]:
    required = [
        "schema",
        "room_id",
        "rid",
        "target",
        "generated_at",
        "prev_summary_sha256",
        "turn_summary_sha256",
        "genesis_summary_sha256",
        "source_mode",
        "local_timestamp",
    ]
    for key in required:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            return False, f"missing or invalid field: {key}"
    if payload.get("schema") != "trialogue_remote_anchor_publish_v1":
        return False, "unsupported schema"
    return True, ""


class SinkStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        ensure_parent(db_path)
        self._write_lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS records (
                    room_id TEXT NOT NULL,
                    remote_sequence INTEGER NOT NULL,
                    remote_record_id TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    rid TEXT NOT NULL,
                    turn_summary_sha256 TEXT NOT NULL,
                    prev_summary_sha256 TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (room_id, remote_sequence),
                    UNIQUE (room_id, rid)
                );
                CREATE INDEX IF NOT EXISTS idx_records_room_sequence
                    ON records (room_id, remote_sequence);
                """
            )

    def append(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        room_id = payload["room_id"]
        rid = payload["rid"]
        turn_sha = payload["turn_summary_sha256"]
        with self._write_lock:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                existing = conn.execute(
                    """
                    SELECT remote_sequence, remote_record_id, recorded_at, turn_summary_sha256
                    FROM records
                    WHERE room_id = ? AND rid = ?
                    """,
                    (room_id, rid),
                ).fetchone()
                if existing is not None:
                    if existing["turn_summary_sha256"] == turn_sha:
                        return HTTPStatus.OK, {
                            "remote_sequence": existing["remote_sequence"],
                            "remote_record_id": existing["remote_record_id"],
                            "recorded_at": existing["recorded_at"],
                        }
                    return HTTPStatus.CONFLICT, {
                        "error": "conflict",
                        "reason": "room_id + rid already exists with different turn_summary_sha256",
                    }

                next_seq = conn.execute(
                    "SELECT COALESCE(MAX(remote_sequence), 0) + 1 FROM records WHERE room_id = ?",
                    (room_id,),
                ).fetchone()[0]
                recorded_at = now_iso()
                remote_record_id = f"{room_id}:{next_seq}"
                conn.execute(
                    """
                    INSERT INTO records (
                        room_id, remote_sequence, remote_record_id, recorded_at,
                        rid, turn_summary_sha256, prev_summary_sha256, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        room_id,
                        next_seq,
                        remote_record_id,
                        recorded_at,
                        rid,
                        turn_sha,
                        payload["prev_summary_sha256"],
                        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    ),
                )
                conn.commit()
                return HTTPStatus.OK, {
                    "remote_sequence": next_seq,
                    "remote_record_id": remote_record_id,
                    "recorded_at": recorded_at,
                }

    def verify(self, room_id: str, after_sequence: int) -> dict[str, Any]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT remote_sequence, remote_record_id, recorded_at, payload_json
                FROM records
                WHERE room_id = ? AND remote_sequence > ?
                ORDER BY remote_sequence ASC
                """,
                (room_id, after_sequence),
            ).fetchall()
        records = []
        for row in rows:
            records.append(
                {
                    "remote_sequence": row["remote_sequence"],
                    "remote_record_id": row["remote_record_id"],
                    "recorded_at": row["recorded_at"],
                    "payload": json.loads(row["payload_json"]),
                }
            )
        return {"room_id": room_id, "records": records}


class SinkHandler(BaseHTTPRequestHandler):
    server_version = "TrialogueRemoteAnchor/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        return

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _auth_token(self) -> str:
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return ""
        return header[len("Bearer ") :].strip()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "service": "trialogue-remote-anchor",
                    "time": now_iso(),
                },
            )
            return
        if parsed.path != "/verify":
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found", "reason": "unknown endpoint"})
            return
        if self._auth_token() != self.server.verify_token:  # type: ignore[attr-defined]
            self._json(HTTPStatus.FORBIDDEN, {"error": "forbidden", "reason": "verify credential invalid"})
            return
        params = parse_qs(parsed.query)
        room_id = (params.get("room_id") or [""])[0].strip()
        if not room_id:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "bad_request", "reason": "room_id is required"})
            return
        after_raw = (params.get("after_sequence") or ["0"])[0].strip() or "0"
        try:
            after_sequence = int(after_raw)
        except ValueError:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "bad_request", "reason": "after_sequence must be an integer"})
            return
        if after_sequence < 0:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "bad_request", "reason": "after_sequence must be >= 0"})
            return
        payload = self.server.store.verify(room_id, after_sequence)  # type: ignore[attr-defined]
        self._json(HTTPStatus.OK, payload)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/append":
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found", "reason": "unknown endpoint"})
            return
        if self._auth_token() != self.server.publish_token:  # type: ignore[attr-defined]
            self._json(HTTPStatus.FORBIDDEN, {"error": "forbidden", "reason": "publish credential invalid"})
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "bad_request", "reason": "invalid content length"})
            return
        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except json.JSONDecodeError:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "bad_request", "reason": "invalid json"})
            return
        if not isinstance(payload, dict):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "bad_request", "reason": "payload must be an object"})
            return
        ok, reason = validate_payload(payload)
        if not ok:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "bad_request", "reason": reason})
            return
        status, response = self.server.store.append(payload)  # type: ignore[attr-defined]
        self._json(status, response)


class SinkServer(ThreadingHTTPServer):
    def __init__(self, host: str, port: int, *, store: SinkStore, publish_token: str, verify_token: str):
        super().__init__((host, port), SinkHandler)
        self.store = store
        self.publish_token = publish_token
        self.verify_token = verify_token


def main() -> int:
    parser = argparse.ArgumentParser(description="Trialogue remote anchor sink")
    parser.add_argument("--conf", required=True, help="Path to sink config")
    parser.add_argument("--host", default="", help="Override host")
    parser.add_argument("--port", type=int, default=0, help="Override port")
    args = parser.parse_args()

    conf = load_conf(args.conf)
    host = args.host or conf.get("SINK_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = args.port or int((conf.get("SINK_PORT", "8890").strip() or "8890"))
    db_path = conf.get("SINK_DB_PATH", "").strip()
    if not db_path:
        raise SystemExit("SINK_DB_PATH is required")
    publish_token_path = conf.get("SINK_PUBLISH_TOKEN_PATH", "").strip()
    verify_token_path = conf.get("SINK_VERIFY_TOKEN_PATH", "").strip()
    if not publish_token_path or not verify_token_path:
        raise SystemExit("SINK_PUBLISH_TOKEN_PATH and SINK_VERIFY_TOKEN_PATH are required")
    publish_token = read_token(publish_token_path)
    verify_token = read_token(verify_token_path)
    if not publish_token or not verify_token:
        raise SystemExit("sink token files are missing or empty")
    if publish_token == verify_token:
        raise SystemExit("publish and verify tokens must be different")

    store = SinkStore(db_path)
    server = SinkServer(host, port, store=store, publish_token=publish_token, verify_token=verify_token)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
