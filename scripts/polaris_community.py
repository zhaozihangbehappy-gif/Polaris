#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

print(
    "polaris deprecation: use `polaris submit|confirm|reject|promote` instead of scripts/polaris_community.py",
    file=sys.stderr,
)

from polaris.community import main


if __name__ == "__main__":
    raise SystemExit(main())
