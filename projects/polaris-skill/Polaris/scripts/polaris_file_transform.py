#!/usr/bin/env python3
import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply a simple file transform for Polaris contract testing.")
    parser.add_argument("--input-file", required=True)
    parser.add_argument("--output-file", required=True)
    parser.add_argument("--marker", required=True)
    parser.add_argument("--mode", default="append-marker")
    args = parser.parse_args()

    input_path = Path(args.input_file)
    output_path = Path(args.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    content = input_path.read_text(encoding="utf-8") if input_path.exists() else ""
    if args.mode == "append-marker":
        transformed = content + ("\n" if content and not content.endswith("\n") else "") + args.marker + "\n"
    else:
        raise SystemExit(f"unsupported transform mode: {args.mode}")

    output_path.write_text(transformed, encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
