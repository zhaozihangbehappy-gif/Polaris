#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys

from hardening import verify_summary_chain


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a Trialogue summary chain and optional anchor bundles")
    parser.add_argument("chain_path", help="Path to local summary chain JSONL")
    parser.add_argument("--anchor-dir", default="", help="Optional anchor bundle root directory")
    parser.add_argument("--anchor-key", default="", help="Optional anchor signing key path")
    args = parser.parse_args()

    result = verify_summary_chain(
        args.chain_path,
        anchor_dir=args.anchor_dir,
        anchor_key_path=args.anchor_key,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
