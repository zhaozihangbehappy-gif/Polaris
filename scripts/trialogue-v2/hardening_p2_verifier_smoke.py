#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import threading
from pathlib import Path

from hardening import (
    _rewrite_jsonl,
    _remote_anchor_backlog_path,
    append_summary_chain,
    build_remote_anchor_payload,
    load_hardening_settings,
    publish_remote_anchor,
    verify_remote_anchor,
)
from hardening_p2_publish_smoke import FakeSinkServer, _free_port, _record, _write_conf


def _append(root: Path, settings, room_id: str, idx: int) -> None:
    chain = append_summary_chain(str(root / "audit" / "summary-chain"), _record(idx), room_id=room_id, source_mode="test")
    result = publish_remote_anchor(settings, chain, room_id=room_id)
    assert result["status"] == "published", result


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="trialogue-p2-verify-", dir="/tmp") as tmp_dir:
        root = Path(tmp_dir)
        port = _free_port()
        server = FakeSinkServer(("127.0.0.1", port))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        conf = _write_conf(root, "blocking", f"http://127.0.0.1:{port}/append")
        settings = load_hardening_settings(str(conf))
        room_id = "room-verify"

        _append(root, settings, room_id, 1)
        _append(root, settings, room_id, 2)

        verified = verify_remote_anchor(settings, room_id=room_id, expected_backlog_count=0)
        assert verified["result"] == "verified", verified
        assert verified["checked_local"] == 2
        assert verified["checked_remote"] == 2

        chain_path = root / "audit" / "summary-chain" / f"{room_id}.jsonl"
        original_lines = chain_path.read_text(encoding="utf-8").splitlines()

        # Expected unpublished suffix is tolerated in async-style verification.
        chain = append_summary_chain(str(root / "audit" / "summary-chain"), _record(3), room_id=room_id, source_mode="test")
        three_line_lines = chain_path.read_text(encoding="utf-8").splitlines()
        _rewrite_jsonl(
            _remote_anchor_backlog_path(settings.remote_anchor_backlog_dir, room_id),
            [build_remote_anchor_payload(chain)],
        )
        tolerated = verify_remote_anchor(settings, room_id=room_id, expected_backlog_count=1)
        assert tolerated["result"] == "verified", tolerated
        stale_expected = verify_remote_anchor(settings, room_id=room_id, expected_backlog_count=0)
        assert stale_expected["result"] == "verified", stale_expected
        assert stale_expected["backlog_count_used"] == 1
        assert stale_expected["expected_backlog_count"] == 0

        # Tail injection / crash window is visible when the backlog file is missing.
        backlog_path = root / "audit" / "remote-backlog" / f"{room_id}.jsonl"
        backlog_path.unlink()
        tail_injected = verify_remote_anchor(settings, room_id=room_id, expected_backlog_count=0)
        assert tail_injected["result"] == "mismatch", tail_injected
        assert tail_injected["mismatch_kind"] == "remote_missing_records"

        # Restore original chain, publish the third turn remotely, then truncate locally.
        chain_path.write_text("\n".join(original_lines) + "\n", encoding="utf-8")
        republish = publish_remote_anchor(settings, chain, room_id=room_id)
        assert republish["status"] == "published", republish
        truncated = verify_remote_anchor(settings, room_id=room_id, expected_backlog_count=0)
        assert truncated["result"] == "mismatch", truncated
        assert truncated["mismatch_kind"] == "remote_has_extra_records"

        # Restore, then corrupt local copy to simulate same-user replacement.
        chain_path.write_text("\n".join(three_line_lines) + "\n", encoding="utf-8")
        mutated_lines = chain_path.read_text(encoding="utf-8").splitlines()
        mutated_lines[-1] = mutated_lines[-1].replace(chain["turn_summary_sha256"], "0" * 64)
        chain_path.write_text("\n".join(mutated_lines) + "\n", encoding="utf-8")
        replaced = verify_remote_anchor(settings, room_id=room_id, expected_backlog_count=0)
        assert replaced["result"] == "mismatch", replaced
        assert replaced["mismatch_kind"] == "turn_summary_mismatch"

        server.shutdown()
        server.server_close()

    print("P2_VERIFIER_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
