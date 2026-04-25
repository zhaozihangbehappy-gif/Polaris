#!/usr/bin/env python3
# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

"""Polaris stats — standalone entry point for experience store statistics.

Usage:
    polaris_stats.py --runtime-dir DIR [--json]

Also accessible via: polaris_cli.py stats --runtime-dir DIR [--json]

This file delegates to polaris_cli._build_stats / cmd_stats to avoid
duplicating the stats logic.
"""
import argparse
import sys
from pathlib import Path

# polaris_cli.py lives in the same directory
sys.path.insert(0, str(Path(__file__).resolve().parent))
import polaris_cli  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(prog="polaris-stats", description="Show Polaris experience store summary")
    parser.add_argument("--runtime-dir", required=True, help="Runtime directory to inspect")
    parser.add_argument("--json", dest="json_output", action="store_true", default=False, help="Output as JSON")
    args = parser.parse_args()
    polaris_cli.cmd_stats(args)


if __name__ == "__main__":
    main()
