#!/usr/bin/env python3
# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

"""Analyze a real file and produce a structured report with independently verifiable metrics."""
import argparse
import hashlib
import json
from pathlib import Path


def analyze_file(target: str) -> dict:
    path = Path(target)
    if not path.exists():
        raise FileNotFoundError(f"No such file or directory: {target}")
    if not path.is_file():
        raise ValueError(f"Not a regular file: {target}")
    raw_bytes = path.read_bytes()
    content = raw_bytes.decode("utf-8")
    lines = content.splitlines()
    words = content.split()
    return {
        "target": str(path.resolve()),
        "size_bytes": len(raw_bytes),
        "line_count": len(lines),
        "word_count": len(words),
        "char_count": len(content),
        "sha256_bytes": hashlib.sha256(raw_bytes).hexdigest(),
        "first_line": lines[0] if lines else "",
        "last_line": lines[-1] if lines else "",
        "empty": len(raw_bytes) == 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze a real file for Polaris execution contracts.")
    parser.add_argument("--target", required=True, help="Path to the file to analyze")
    parser.add_argument("--output-file", required=True, help="Path to write the JSON analysis report")
    args = parser.parse_args()

    report = analyze_file(args.target)
    output = Path(args.output_file)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "output": str(output)}, sort_keys=True))


if __name__ == "__main__":
    main()
