# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

from __future__ import annotations

import sys

print(
    "polaris deprecation: import polaris.adapter.index instead of adapters.mcp_polaris.polaris_index",
    file=sys.stderr,
)

from polaris.adapter.index import *  # noqa: F401,F403
