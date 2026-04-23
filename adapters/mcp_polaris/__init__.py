from __future__ import annotations

import warnings

warnings.warn(
    "adapters.mcp_polaris is deprecated; use `polaris serve-mcp`.",
    DeprecationWarning,
    stacklevel=2,
)

from polaris.adapter import *  # noqa: F401,F403
