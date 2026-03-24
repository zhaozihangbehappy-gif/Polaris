#!/usr/bin/env python3
"""Trialogue v4 — MCP Server (stdio transport)

Minimal JSON-RPC 2.0 server exposing trialogue_fetch, trialogue_search,
and trialogue_sanitize tools via the Model Context Protocol.

Zero third-party dependencies. Lazy-loads heavy modules on first tool call.

Protocol: one JSON object per line on stdin/stdout, newline-delimited.
"""
from __future__ import annotations

# Only import json + sys at startup for fast cold start (~100ms).
# All other imports are deferred to first tool call.
import json
import sys

SERVER_NAME = "trialogue-guard"
SERVER_VERSION = "0.1.0"

TOOLS = [
    {
        "name": "trialogue_fetch",
        "description": (
            "Fetch a URL and return sanitized plain text. "
            "External content is cleaned of structural prompt injection "
            "before entering your context."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to fetch"},
                "json_output": {
                    "type": "boolean",
                    "description": "If true, return JSON with audit metadata",
                    "default": False,
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "trialogue_search",
        "description": "Search the web and return sanitized result summaries.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "json_output": {
                    "type": "boolean",
                    "description": "If true, return JSON with audit metadata",
                    "default": False,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "trialogue_sanitize",
        "description": "Sanitize arbitrary text through the tsan cleaning pipeline.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to sanitize"},
                "mode": {
                    "type": "string",
                    "enum": ["strict", "permissive", "report"],
                    "default": "strict",
                },
            },
            "required": ["text"],
        },
    },
]


# ── Lazy import ─────────────────────────────────────────────────────────────

_pipeline = None


def _ensure_pipeline():
    global _pipeline
    if _pipeline is None:
        import os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import pipeline as _mod
        _pipeline = _mod


# ── Tool handlers ───────────────────────────────────────────────────────────


def _handle_fetch(args: dict) -> dict:
    _ensure_pipeline()
    url = args.get("url", "")
    if not url:
        return {"isError": True, "content": [{"type": "text", "text": "Missing required parameter: url"}]}
    try:
        result = _pipeline.pipeline_fetch(url, via_guard=True)
    except Exception as e:
        return {"isError": True, "content": [{"type": "text", "text": f"Fetch error: {e}"}]}

    # Strict audit failure → error response (no content delivered)
    if result.get("error") and result.get("audit_status") == "failed":
        return {"isError": True, "content": [{"type": "text", "text": result["error"]}]}

    if args.get("json_output"):
        return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}
    text = result["cleaned_text"]
    if result.get("audit_status") == "failed":
        text += f"\n\n[trialogue-guard] WARNING: audit chain write failed: {result.get('audit_error', 'unknown')}"
    return {"content": [{"type": "text", "text": text}]}


def _handle_search(args: dict) -> dict:
    _ensure_pipeline()
    query = args.get("query", "")
    if not query:
        return {"isError": True, "content": [{"type": "text", "text": "Missing required parameter: query"}]}
    try:
        result = _pipeline.pipeline_search(query, via_guard=True)
    except Exception as e:
        return {"isError": True, "content": [{"type": "text", "text": f"Search error: {e}"}]}

    # Strict audit failure → error response
    if result.get("error") and result.get("audit_status") == "failed":
        return {"isError": True, "content": [{"type": "text", "text": result["error"]}]}

    if args.get("json_output"):
        return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}
    return {"content": [{"type": "text", "text": result["cleaned_text"]}]}


def _handle_sanitize(args: dict) -> dict:
    _ensure_pipeline()
    text = args.get("text", "")
    if not text:
        return {"isError": True, "content": [{"type": "text", "text": "Missing required parameter: text"}]}
    mode = args.get("mode", "strict")
    result = _pipeline.pipeline_sanitize(text, mode=mode)
    return {"content": [{"type": "text", "text": result["cleaned_text"]}]}


TOOL_HANDLERS = {
    "trialogue_fetch": _handle_fetch,
    "trialogue_search": _handle_search,
    "trialogue_sanitize": _handle_sanitize,
}


# ── JSON-RPC dispatch ───────────────────────────────────────────────────────


def _make_response(id_val, result=None, error=None):
    resp = {"jsonrpc": "2.0", "id": id_val}
    if error is not None:
        resp["error"] = error
    else:
        resp["result"] = result
    return resp


def _handle_request(msg: dict) -> dict | None:
    method = msg.get("method", "")
    msg_id = msg.get("id")
    params = msg.get("params", {})

    if method == "initialize":
        return _make_response(msg_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })

    if method == "notifications/initialized":
        # Client acknowledgment, no response needed
        return None

    if method == "tools/list":
        return _make_response(msg_id, {"tools": TOOLS})

    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})
        handler = TOOL_HANDLERS.get(tool_name)
        if not handler:
            return _make_response(msg_id, error={
                "code": -32601,
                "message": f"Unknown tool: {tool_name}",
            })
        try:
            result = handler(tool_args)
        except Exception as e:
            return _make_response(msg_id, error={
                "code": -32603,
                "message": str(e),
            })
        return _make_response(msg_id, result)

    # Unknown method
    if msg_id is not None:
        return _make_response(msg_id, error={
            "code": -32601,
            "message": f"Unknown method: {method}",
        })
    return None  # Notification for unknown method — ignore


# ── Main loop ───────────────────────────────────────────────────────────────


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            resp = {"jsonrpc": "2.0", "id": None, "error": {
                "code": -32700, "message": "Parse error"
            }}
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
            continue

        response = _handle_request(msg)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

    return 0


if __name__ == "__main__":
    sys.exit(main())
