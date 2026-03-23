#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from chat import make_room_id
from server import TrialogueState


def _write_conf(root: Path) -> Path:
    conf = root / "trialogue-v2.conf"
    conf.write_text(
        "\n".join(
            [
                f"WORKSPACE={root}",
                f"AUDIT_LOG={root / 'audit' / 'audit.jsonl'}",
                f"TRIALOGUE_STATE_ROOT={root / 'state'}",
                f"BROKER_ROOM_STATE_DIR={root / 'state' / 'broker-rooms'}",
                f"HARDENING_SANITIZER_PATTERNS={root / 'patterns.json'}",
                f"HARDENING_VERSION_ALLOWLIST={root / 'allowlist.json'}",
                "HARDENING_TRANSCRIPT_SANITIZER=strict",
                "HARDENING_VERSION_GATE=warn",
                "HARDENING_VERSION_GATE_RECHECK=warn",
                "HARDENING_OPERATION_LOCKS=enabled",
                "HARDENING_REMOTE_AUDIT_PUBLISH=disabled",
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
    (root / "audit").mkdir(parents=True, exist_ok=True)
    (root / "audit" / "audit.jsonl").write_text("", encoding="utf-8")
    return conf


def _record(idx: int) -> dict[str, object]:
    return {
        "rid": f"rid-{idx}",
        "nonce": f"nonce-{idx}",
        "target": "claude",
        "timestamp": f"2026-03-23T00:00:0{idx}Z",
        "message_body": f"hello-{idx}",
        "stdout": f"reply-{idx}",
        "session_confirmed": True,
        "session_id": f"session-{idx}",
        "confirmation_method": "claude_session_file",
        "exit_code": 0,
        "remote_anchor_policy": "blocking",
        "remote_anchor_status": "unanchored",
        "remote_anchor_reason": "remote publish failed",
        "remote_anchor_backlog_count": idx,
        "remote_anchor_drained_count": 0,
        "remote_anchor_remote_sequence": None,
        "remote_anchor_remote_record_id": "",
        "remote_anchor_hard_cap_exceeded": False,
        "remote_anchor_current_published": False,
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="trialogue-p2-broker-", dir="/tmp") as tmp_dir:
        root = Path(tmp_dir)
        conf = _write_conf(root)
        state = TrialogueState("P2 broker anchor smoke", "/bin/true", str(conf), str(root / "audit" / "audit.jsonl"))
        assert state.room_health in {"healthy", "degraded"}

        for idx in range(1, 4):
            assert state._merge_audit_record(_record(idx)) is True

        assert state.remote_anchor["consecutive_unanchored"] == 3
        assert state.remote_anchor["state"] == "anchor_blocked"
        assert state.room_health == "anchor_blocked"
        try:
            state.submit("@claude blocked?")
        except ValueError as exc:
            assert "anchor_blocked" in str(exc) or "远端审计锚当前阻断中" in str(exc)
        else:
            raise AssertionError("submit should be blocked in anchor_blocked")

        success = _record(4)
        success["remote_anchor_status"] = "published"
        success["remote_anchor_reason"] = ""
        success["remote_anchor_backlog_count"] = 0
        success["remote_anchor_remote_sequence"] = 10
        success["remote_anchor_current_published"] = True
        state._merge_audit_record(success)
        assert state.remote_anchor["consecutive_unanchored"] == 0
        assert state.remote_anchor["state"] == "anchor_blocked"
        with state.lock:
            state.remote_anchor["verify_status"] = "verified"
            state.remote_anchor["recovery_verify_ready"] = True
        ok, reason = state.reset_recovery()
        assert ok is True, reason
        assert state.room_health in {"healthy", "degraded"}

    print("P2_BROKER_ANCHOR_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
