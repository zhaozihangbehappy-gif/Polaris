#!/usr/bin/env python3
from __future__ import annotations

import socket
import tempfile
from pathlib import Path

from hardening import PortReservationRegistry


def _find_free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="trialogue-p1-shared-host-") as tmp_dir:
        root = Path(tmp_dir)
        registry_path = root / "port-registry.json"

        free_port = _find_free_port()
        busy_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        busy_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        busy_sock.bind(("127.0.0.1", 0))
        busy_sock.listen(1)
        busy_port = int(busy_sock.getsockname()[1])

        registry = PortReservationRegistry(str(registry_path))
        assert registry.reserve(free_port, "owner-free", {"room_id": "room-a"})["granted"] is True
        assert registry.reserve(busy_port, "owner-busy", {"room_id": "room-b"})["granted"] is True

        reloaded = PortReservationRegistry(str(registry_path))
        snapshot = reloaded.snapshot()
        assert str(free_port) in snapshot["reservations"]
        assert str(busy_port) in snapshot["reservations"]

        events = reloaded.reconcile_after_restart()
        kinds = {f"{event['kind']}:{event['port']}" for event in events}
        assert f"port_registry_orphan_cleaned:{free_port}" in kinds
        assert f"port_registry_occupied:{busy_port}" in kinds

        after = reloaded.snapshot()["reservations"]
        assert str(free_port) not in after
        assert str(busy_port) in after

        released = reloaded.release_owner("owner-busy")
        assert str(busy_port) in released

        busy_sock.close()

    print("P1_SHARED_HOST_SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
