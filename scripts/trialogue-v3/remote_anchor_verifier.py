#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from hardening import load_hardening_settings, verify_remote_anchor


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Trialogue remote anchor state for one room.")
    parser.add_argument("--conf", required=True, help="Path to trialogue-v3.conf")
    parser.add_argument("--room-id", required=True, help="Room id to verify")
    parser.add_argument("--expected-backlog", type=int, default=0, help="Expected unpublished suffix count")
    args = parser.parse_args()

    settings = load_hardening_settings(args.conf)
    result = verify_remote_anchor(
        settings,
        room_id=args.room_id,
        expected_backlog_count=max(0, args.expected_backlog),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
