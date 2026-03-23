#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import threading
from pathlib import Path

from hardening import append_summary_chain, load_hardening_settings, publish_remote_anchor
from hardening_p2_publish_smoke import FakeSinkServer, _free_port, _record
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
                "HARDENING_REMOTE_AUDIT_PUBLISH=blocking",
                "HARDENING_REMOTE_AUDIT_PUBLISH_URL=http://127.0.0.1:9/append",
                "HARDENING_REMOTE_AUDIT_VERIFY_URL=http://127.0.0.1:9/verify",
                f"HARDENING_REMOTE_AUDIT_PUBLISH_CREDENTIAL_PATH={root / 'publish.token'}",
                f"HARDENING_REMOTE_AUDIT_VERIFY_CREDENTIAL_PATH={root / 'verify.token'}",
            ]
        ),
        encoding="utf-8",
    )
    (root / "publish.token").write_text("publish-secret\n", encoding="utf-8")
    (root / "verify.token").write_text("verify-secret\n", encoding="utf-8")
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


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="trialogue-p2-operator-", dir="/tmp") as tmp_dir:
        root = Path(tmp_dir)
        conf = _write_conf(root)
        topic = "P2 operator smoke"
        room_id = make_room_id(topic)

        # Startup verify unreachable in blocking mode => anchor_blocked.
        state = TrialogueState(topic, "/bin/true", str(conf), str(root / "audit" / "audit.jsonl"))
        assert state.room_health == "anchor_blocked", state.snapshot()["hardening"]["remote_anchor"]

        # Explicit read-only diagnostic mode requires verifier pass + reset.
        with state.lock:
            state.remote_anchor["state"] = "read_only_diagnostic"
            state.remote_anchor["verify_status"] = "mismatch"
            state.remote_anchor["verify_reason"] = "startup mismatch"
        ok, reason = state.reset_recovery()
        assert ok is False
        assert "verifier" in reason

        with state.lock:
            state.remote_anchor["verify_status"] = "verified"
            state.remote_anchor["verify_reason"] = ""
        ok, reason = state.reset_recovery()
        assert ok is True, reason
        assert state.room_health in {"healthy", "degraded"}

        # Anchor-blocked requires publish recovery + verifier pass + operator reset.
        with state.lock:
            state.remote_anchor["state"] = "anchor_blocked"
            state.remote_anchor["last_status"] = "published"
            state.remote_anchor["backlog_count"] = 0
            state.remote_anchor["recovery_publish_ready"] = False
            state.remote_anchor["recovery_verify_ready"] = True
        ok, reason = state.reset_recovery()
        assert ok is False and "publish" in reason

        with state.lock:
            state.remote_anchor["recovery_publish_ready"] = True
            state.remote_anchor["recovery_verify_ready"] = False
        ok, reason = state.reset_recovery()
        assert ok is False and "verifier" in reason

        with state.lock:
            state.remote_anchor["recovery_verify_ready"] = True
        ok, reason = state.reset_recovery()
        assert ok is True, reason

        # Persisted state should keep remote anchor verifier fields.
        persisted = json.loads(Path(state.room_state_path).read_text(encoding="utf-8"))
        assert persisted["remote_anchor"]["verify_status"] in {"verified", "unreachable", "disabled", "mismatch", "startup-pending"}
        assert persisted["room_id"] == room_id

    with tempfile.TemporaryDirectory(prefix="trialogue-p2-operator-mismatch-", dir="/tmp") as tmp_dir:
        root = Path(tmp_dir)
        port = _free_port()
        server = FakeSinkServer(("127.0.0.1", port))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        conf = _write_conf(root)
        text = Path(conf).read_text(encoding="utf-8")
        text = text.replace(
            "HARDENING_REMOTE_AUDIT_PUBLISH_URL=http://127.0.0.1:9/append",
            f"HARDENING_REMOTE_AUDIT_PUBLISH_URL=http://127.0.0.1:{port}/append",
        ).replace(
            "HARDENING_REMOTE_AUDIT_VERIFY_URL=http://127.0.0.1:9/verify",
            f"HARDENING_REMOTE_AUDIT_VERIFY_URL=http://127.0.0.1:{port}/verify",
        )
        Path(conf).write_text(text, encoding="utf-8")
        settings = load_hardening_settings(str(conf))
        mismatch_room = make_room_id("P2 operator mismatch")
        chain = append_summary_chain(str(root / "audit" / "summary-chain"), _record(1), room_id=mismatch_room, source_mode="test")
        published = publish_remote_anchor(settings, chain, room_id=mismatch_room)
        assert published["status"] == "published", published
        chain_path = root / "audit" / "summary-chain" / f"{mismatch_room}.jsonl"
        lines = chain_path.read_text(encoding="utf-8").splitlines()
        lines[-1] = lines[-1].replace(chain["turn_summary_sha256"], "f" * 64)
        chain_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        mismatch_state = TrialogueState("P2 operator mismatch", "/bin/true", str(conf), str(root / "audit" / "audit.jsonl"))
        assert mismatch_state.room_health == "read_only_diagnostic", mismatch_state.snapshot()["hardening"]["remote_anchor"]
        server.shutdown()
        server.server_close()

    print("P2_OPERATOR_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
