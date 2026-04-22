"""Polaris MCP stdio server."""
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
    print("polaris-mcp: 'mcp' package not installed. Run: pip install mcp", file=sys.stderr)
    raise

from polaris.adapter.index import CONTEXT_TOKEN_BUDGET, format_for_injection, match

server = Server("polaris")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="polaris_lookup",
            description="Look up structured engineering fix paths for an error before guessing.",
            inputSchema={
                "type": "object",
                "properties": {
                    "error_text": {"type": "string", "description": "Raw stderr or error message."},
                    "ecosystem": {
                        "type": "string",
                        "enum": ["python", "node", "docker", "go", "java", "rust", "ruby", "terraform"],
                    },
                    "limit": {"type": "integer", "default": 3, "minimum": 1, "maximum": 5},
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
    payload = format_for_injection(
        hits,
        token_budget=CONTEXT_TOKEN_BUDGET,
        max_patterns=arguments.get("limit", 3),
    )
    payload["_latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    return [TextContent(type="text", text=json.dumps(payload))]


async def _main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
