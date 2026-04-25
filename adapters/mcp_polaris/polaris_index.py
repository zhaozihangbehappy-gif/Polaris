# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

from __future__ import annotations

import warnings

warnings.warn(
    "adapters.mcp_polaris.polaris_index is deprecated; use `polaris serve-mcp`.",
    DeprecationWarning,
    stacklevel=2,
)

from polaris.adapter.index import *  # noqa: F401,F403
