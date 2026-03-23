#!/usr/bin/env python3
from __future__ import annotations

import json
import socket
import tempfile
import threading
from pathlib import Path

from hardening import atomic_write_json
from chat import make_room_id
from server import TrialogueState


def _find_free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


def _write_conf(root: Path) -> Path:
    state_root = root / "state"
    audit_root = root / "audit"
    conf = root / "trialogue-v2.conf"
    conf.write_text(
        "\n".join(
            [
                f"WORKSPACE={root}",
                f"AUDIT_LOG={audit_root / 'audit.jsonl'}",
                f"TRIALOGUE_STATE_ROOT={state_root}",
                f"BROKER_ROOM_STATE_DIR={state_root / 'broker-rooms'}",
                f"TRIALOGUE_PRIVATE_TMP_DIR={state_root / 'tmp'}",
                f"TRIALOGUE_SHARED_META_DIR={state_root / 'shared-meta'}",
                f"TRIALOGUE_PORT_REGISTRY_PATH={state_root / 'port-registry.json'}",
                f"HARDENING_SANITIZER_PATTERNS={root / 'patterns.json'}",
                f"HARDENING_VERSION_ALLOWLIST={root / 'allowlist.json'}",
                "HARDENING_TRANSCRIPT_SANITIZER=strict",
                "HARDENING_VERSION_GATE=warn",
                "HARDENING_VERSION_GATE_RECHECK=warn",
                "HARDENING_OPERATION_LOCKS=enabled",
                "HARDENING_EXTERNAL_AUDIT_ANCHOR=disabled",
                "HARDENING_BROKER_RECOVERY_MODE=auto",
                "HARDENING_SHARED_HOST_COLLISION_GUARD=enabled",
            ]
        ),
        encoding="utf-8",
    )
    (root / "patterns.json").write_text(
        json.dumps({"block_wrappers": ["MEMORY-CONTEXT"], "single_line_headers": ["TRIALOGUE-AUDIT"]}),
        encoding="utf-8",
    )
    (root / "allowlist.json").write_text(
        json.dumps({"policy": "warn", "runners": {"claude": {"versions": [], "hashes": []}, "codex": {"versions": [], "hashes": []}}}),
        encoding="utf-8",
    )
    (audit_root / "audit.jsonl").parent.mkdir(parents=True, exist_ok=True)
    (audit_root / "audit.jsonl").write_text("", encoding="utf-8")
    return conf


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="trialogue-p1-recovery-") as tmp_dir:
        root = Path(tmp_dir)
        conf = _write_conf(root)
        topic = "P1 recovery smoke"
        room_id = make_room_id(topic)
        state_root = root / "state"
        room_state_path = state_root / "broker-rooms" / f"{room_id}.json"
        orphan_port = _find_free_port()
        atomic_write_json(
            str(room_state_path),
            {
                "topic": topic,
                "room_id": room_id,
                "current_claude_session": "claude-old",
                "latest_codex_session": "codex-old",
                "claude_sessions": ["claude-old"],
                "claude_meeting_cursor": 2,
                "codex_meeting_cursor": 3,
                "target_override": "meeting",
                "last_rid": "rid-old",
                "room_health": "healthy",
                "recovery_reasons": [],
                "degraded_features": {},
                "system_events": [],
                "items": [
                    {
                        "id": "item-1",
                        "source": "live",
                        "raw_text": "@claude hello",
                        "message": "hello",
                        "targets": ["claude"],
                        "rid": "rid-old",
                        "nonce": "nonce-old",
                        "target_name": "meeting",
                        "target_source": "default",
                        "target_path": "",
                        "created_at": "2026-03-23T00:00:00Z",
                        "agents": [
                            {
                                "target": "claude",
                                "label": "Claude",
                                "status": "running",
                                "confirmed": None,
                                "created_at": "2026-03-23T00:00:00Z",
                                "started_at": "2026-03-23T00:00:01Z",
                                "finished_at": "",
                                "phase": "running",
                                "phase_label": "running",
                                "next_step": "pending",
                                "current_detail": "in flight",
                                "reply": "",
                                "meta": {},
                                "hardening": {},
                                "events": [],
                                "pending_approval": {"request_id": "req-1"},
                                "held_lock_owners": [],
                            }
                        ],
                    }
                ],
                "pending_approvals": [{"item_id": "item-1", "target": "claude", "request_id": "req-1", "summary": "approve"}],
                "lock_snapshot": {"class:systemd": "owner-1"},
                "port_registry": {"reservations": {str(orphan_port): {"owner": "owner-1", "reserved_at": "2026-03-23T00:00:00Z", "metadata": {}}}},
                "updated_at": "2026-03-23T00:00:02Z",
            },
        )
        atomic_write_json(
            str(state_root / "port-registry.json"),
            {"reservations": {str(orphan_port): {"owner": "owner-1", "reserved_at": "2026-03-23T00:00:00Z", "metadata": {}}}},
        )

        state = TrialogueState(topic, "/bin/true", str(conf), str(root / "audit" / "audit.jsonl"))
        assert state.room_health == "recovery_required"
        assert state.recovery_reasons
        assert state.items[0]["agents"][0]["status"] == "failed"
        assert state.items[0]["agents"][0]["phase"] == "recovery_required"
        assert any(ev.get("kind") == "port_registry_orphan_cleaned" for ev in state.system_events)

        blocked, reason = state.reset_recovery()
        assert blocked is True, reason
        assert state.room_health in {"healthy", "degraded"}
        assert not state.recovery_reasons

        state.pending_approvals[("item-2", "claude", "req-2")] = {"event": None, "response": None, "agent": {}}
        ok, reason = state.reset_recovery()
        assert ok is False and "pending approvals" in reason
        state.pending_approvals.clear()

        persisted = json.loads(room_state_path.read_text(encoding="utf-8"))
        assert persisted["room_id"] == room_id
        assert persisted["items"][0]["agents"][0]["status"] == "failed"

        concurrent_path = root / "state" / "concurrent-room.json"
        errors: list[str] = []

        def writer(idx: int) -> None:
            try:
                atomic_write_json(
                    str(concurrent_path),
                    {"writer": idx, "payload": f"value-{idx}"},
                )
            except Exception as exc:  # pragma: no cover - smoke should stay green
                errors.append(str(exc))

        threads = [threading.Thread(target=writer, args=(idx,)) for idx in range(30)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert not errors, errors
        concurrent_payload = json.loads(concurrent_path.read_text(encoding="utf-8"))
        assert "writer" in concurrent_payload and "payload" in concurrent_payload

    print("P1_RECOVERY_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
