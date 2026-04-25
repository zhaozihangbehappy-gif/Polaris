#!/usr/bin/env python3
# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

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
