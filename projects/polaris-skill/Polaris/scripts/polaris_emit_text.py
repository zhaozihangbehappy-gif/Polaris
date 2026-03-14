#!/usr/bin/env python3
import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Emit deterministic text for Polaris command-output contracts.")
    parser.add_argument("--text", required=True)
    args = parser.parse_args()
    print(args.text)


if __name__ == "__main__":
    main()
