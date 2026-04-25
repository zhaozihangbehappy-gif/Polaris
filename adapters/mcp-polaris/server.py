# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

from __future__ import annotations

import sys

print(
    "polaris deprecation: run `polaris serve-mcp` or import polaris.adapter.server instead of adapters.mcp_polaris.server",
    file=sys.stderr,
)

from polaris.adapter.server import main


if __name__ == "__main__":
    main()
