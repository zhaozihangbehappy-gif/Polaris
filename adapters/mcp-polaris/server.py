"""Polaris MCP stdio server.

Exposes a single tool: polaris_lookup(error_text, ecosystem?) -> matched
patterns serialized under a 300-token injection budget.

Install:
  pip install mcp

Run standalone (for adapter debugging):
  python -m adapters.mcp-polaris.server

Register with Claude Code / Codex / Cursor: see README.md in this directory.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from typing import Any

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool
except ImportError:
    print(
        "polaris-mcp: 'mcp' package not installed. Run: pip install mcp",
        file=sys.stderr,
    )
    raise

from adapters.mcp_polaris.polaris_index import format_for_constant_budget, match

server = Server("polaris")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="polaris_lookup",
            description=(
                "Look up verified engineering fix paths for a failing command "
                "or error. Returns a budgeted list of structured patterns the "
                "calling agent can use to short-circuit repeated trial-and-error."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "error_text": {
                        "type": "string",
                        "description": "Raw stderr or error message from the failing run.",
                    },
                    "ecosystem": {
                        "type": "string",
                        "enum": ["python", "node", "docker", "go", "java", "rust", "ruby", "terraform"],
                        "description": "Optional ecosystem hint to narrow matches.",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 3,
                        "minimum": 1,
                        "maximum": 5,
                    },
                },
                "required": ["error_text"],
            },
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name != "polaris_lookup":
        return [TextContent(type="text", text=json.dumps({"error": f"unknown tool: {name}"}))]
    t0 = time.perf_counter()
    hits = match(
        error_text=arguments["error_text"],
        ecosystem=arguments.get("ecosystem"),
        limit=arguments.get("limit", 3),
    )
    payload = format_for_constant_budget(hits)
    payload["_latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    return [TextContent(type="text", text=json.dumps(payload))]


async def _main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(_main())
