#!/usr/bin/env python3
# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Emit deterministic text for Polaris command-output contracts.")
    parser.add_argument("--text", required=True)
    args = parser.parse_args()
    print(args.text)


if __name__ == "__main__":
    main()
