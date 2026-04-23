from __future__ import annotations

import warnings

warnings.warn(
    "adapters.mcp_polaris.polaris_index is deprecated; use `polaris serve-mcp`.",
    DeprecationWarning,
    stacklevel=2,
)

from polaris.adapter.index import *  # noqa: F401,F403
