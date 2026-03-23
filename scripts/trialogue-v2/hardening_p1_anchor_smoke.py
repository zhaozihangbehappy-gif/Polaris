#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import threading
from pathlib import Path

from hardening import (
    append_summary_chain,
    export_anchor_bundle,
    verify_summary_chain,
)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="trialogue-p1-anchor-", dir="/tmp") as tmp_dir:
        tmp = Path(tmp_dir)
        chain_dir = tmp / "summary-chain"
        anchor_dir = tmp / "anchor"
        key_path = tmp / "anchor.key"
        key_path.write_text("test-anchor-key", encoding="utf-8")
        key_path.chmod(0o600)

        record1 = {
            "timestamp": "2026-03-23T00:00:00Z",
            "rid": "rid-1",
            "nonce": "nonce-1",
            "target": "claude",
            "target_name": "meeting",
            "target_source": "default",
            "target_path": "",
            "mode": "launcher_generated",
            "session_id": "sess-1",
            "session_confirmed": True,
            "confirmation_method": "claude_session_file",
            "confirmation": {"turn_id": "turn-1", "thread_id": "thread-1"},
            "exit_code": 0,
            "binary_path": "/bin/claude",
            "binary_sha256": "aaa",
            "cli_version": "claude 1.0",
            "version_gate_policy": "warn",
            "version_gate_allowed": True,
            "version_gate_reason": "",
            "version_recheck_policy": "warn",
            "version_recheck_allowed": True,
            "version_recheck_result": "match",
            "version_recheck_reason": "",
            "message_body": "hello",
            "stdout": "ok",
            "stderr": "",
            "raw_event_log_path": "",
            "room_state_path": "",
        }
        chain1 = append_summary_chain(str(chain_dir), record1, room_id="room-1", source_mode="launcher_audit")
        anchor1 = export_anchor_bundle(str(anchor_dir), str(key_path), chain1, policy="async")
        assert anchor1["status"] == "exported"

        record2 = dict(record1)
        record2["rid"] = "rid-2"
        record2["nonce"] = "nonce-2"
        record2["confirmation"] = {"turn_id": "turn-2", "thread_id": "thread-1"}
        record2["message_body"] = "hello again"
        chain2 = append_summary_chain(str(chain_dir), record2, room_id="room-1", source_mode="launcher_audit")
        anchor2 = export_anchor_bundle(str(anchor_dir), str(key_path), chain2, policy="async")
        assert anchor2["status"] == "exported"

        result = verify_summary_chain(
            str(chain_dir / "room-1.jsonl"),
            anchor_dir=str(anchor_dir),
            anchor_key_path=str(key_path),
        )
        assert result["ok"] is True
        assert result["checked"] == 2

        concurrent_chain_dir = tmp / "summary-chain-concurrent"
        concurrent_anchor_dir = tmp / "anchor-concurrent"

        def writer(idx: int) -> None:
            record = dict(record1)
            record["rid"] = f"rid-{idx + 10}"
            record["nonce"] = f"nonce-{idx + 10}"
            record["message_body"] = f"payload-{idx}"
            record["stdout"] = f"reply-{idx}"
            chain = append_summary_chain(
                str(concurrent_chain_dir),
                record,
                room_id="room-concurrent",
                source_mode="launcher_audit",
            )
            anchor = export_anchor_bundle(str(concurrent_anchor_dir), str(key_path), chain, policy="async")
            assert anchor["status"] == "exported"

        threads = [threading.Thread(target=writer, args=(idx,)) for idx in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        concurrent_result = verify_summary_chain(
            str(concurrent_chain_dir / "room-concurrent.jsonl"),
            anchor_dir=str(concurrent_anchor_dir),
            anchor_key_path=str(key_path),
        )
        assert concurrent_result["ok"] is True
        assert concurrent_result["checked"] == 12

        insecure_key = tmp / "anchor-insecure.key"
        insecure_key.write_text("test-anchor-key", encoding="utf-8")
        insecure_key.chmod(0o644)
        insecure_status = export_anchor_bundle(str(anchor_dir), str(insecure_key), chain1, policy="async")
        assert insecure_status["status"] == "failed"
        assert "insecure permissions" in insecure_status["reason"]

    print("P1_ANCHOR_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
