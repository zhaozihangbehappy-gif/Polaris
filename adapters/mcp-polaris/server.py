from __future__ import annotations

import sys

print(
    "polaris deprecation: run `polaris serve-mcp` or import polaris.adapter.server instead of adapters.mcp_polaris.server",
    file=sys.stderr,
)

from polaris.adapter.server import main


if __name__ == "__main__":
    main()
