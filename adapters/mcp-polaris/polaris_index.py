from __future__ import annotations

import sys

print(
    "polaris deprecation: import polaris.adapter.index instead of adapters.mcp_polaris.polaris_index",
    file=sys.stderr,
)

from polaris.adapter.index import *  # noqa: F401,F403
