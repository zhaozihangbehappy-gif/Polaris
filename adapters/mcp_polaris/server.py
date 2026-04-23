from __future__ import annotations

import warnings

warnings.warn(
    "adapters.mcp_polaris.server is deprecated; use `polaris serve-mcp`.",
    DeprecationWarning,
    stacklevel=2,
)

from polaris.adapter.server import *  # noqa: F401,F403


if __name__ == "__main__":
    main()
