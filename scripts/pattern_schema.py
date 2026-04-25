# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

print(
    "polaris deprecation: import polaris.schema instead of scripts/pattern_schema.py",
    file=sys.stderr,
)

from polaris.schema import *  # noqa: F401,F403
