#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

print(
    "polaris deprecation: use polaris.validator instead of scripts/pattern_validator_v4.py",
    file=sys.stderr,
)

from polaris.validator import main


if __name__ == "__main__":
    raise SystemExit(main())
