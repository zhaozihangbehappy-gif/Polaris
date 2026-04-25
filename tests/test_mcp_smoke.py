# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

"""End-to-end MCP stdio smoke test.

Covers the path Cursor / Claude Desktop / Codex CLI actually use:
launch `polaris serve-mcp` as a subprocess and drive it via the official
mcp ClientSession. Guards against regressions that unit tests miss
(stdio framing, entry-point wiring, version reporting).
"""
from __future__ import annotations

import asyncio
import shutil
import sys

import pytest

from polaris import __version__ as POLARIS_VERSION


pytestmark = pytest.mark.skipif(
    shutil.which("polaris") is None,
    reason="polaris console script not on PATH (run `pip install -e .`)",
)


async def _drive_session():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command="polaris", args=["serve-mcp"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await asyncio.wait_for(session.initialize(), timeout=10)
            tools = await asyncio.wait_for(session.list_tools(), timeout=10)
            result = await asyncio.wait_for(
                session.call_tool(
                    "polaris_lookup",
                    {
                        "error_text": "ModuleNotFoundError: No module named 'requests'",
                        "ecosystem": "python",
                    },
                ),
                timeout=10,
            )
            return init, tools, result


def test_mcp_stdio_smoke():
    init, tools, result = asyncio.run(_drive_session())

    assert init.serverInfo.name == "polaris"
    assert init.serverInfo.version == POLARIS_VERSION, (
        f"serverInfo.version should be Polaris {POLARIS_VERSION}, got {init.serverInfo.version}"
    )

    tool_names = [t.name for t in tools.tools]
    assert "polaris_lookup" in tool_names

    assert result.content, "call_tool returned empty content"
    assert result.content[0].type == "text"
    assert "patterns" in result.content[0].text


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
