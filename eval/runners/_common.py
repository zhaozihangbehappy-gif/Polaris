# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

"""Shared runner helpers — no fabrication, honest None on missing signal.

Used by codex_runner, claude_code_runner, cursor_runner. Keeps each runner file
focused on its agent's output shape.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


REPO = Path(__file__).resolve().parent.parent.parent


def run_fix_command(fix_command_test: str, timeout: int = 120) -> tuple[bool, str]:
    """Return (ci_pass, combined_output)."""
    try:
        proc = subprocess.run(
            ["bash", "-c", fix_command_test],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        return False, f"[timeout] {e}"
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    return proc.returncode == 0, combined


def find_root_cause_round(assistant_texts: list[str], regex: str) -> Optional[int]:
    """First 1-indexed turn where regex matches. None if never."""
    if not regex:
        return None
    try:
        rx = re.compile(regex, re.IGNORECASE)
    except re.error:
        return None
    for i, text in enumerate(assistant_texts, start=1):
        if rx.search(text):
            return i
    return None


def count_redundant_tool_calls(tool_calls: list[tuple[str, str]]) -> int:
    """Identical (tool_name, stringified_args) seen before."""
    seen: set[tuple[str, str]] = set()
    redundant = 0
    for sig in tool_calls:
        if sig in seen:
            redundant += 1
        else:
            seen.add(sig)
    return redundant


def write_claude_mcp_config(polaris_enabled: bool) -> Path:
    """Temp JSON file for Claude Code --mcp-config."""
    if polaris_enabled:
        cfg = {
            "mcpServers": {
                "polaris": {
                    "command": "python3",
                    "args": ["-m", "adapters.mcp_polaris.server"],
                    "cwd": str(REPO),
                    "env": {"PYTHONPATH": str(REPO)},
                }
            }
        }
    else:
        cfg = {"mcpServers": {}}
    fd = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, prefix="polaris_mcp_"
    )
    json.dump(cfg, fd)
    fd.close()
    return Path(fd.name)


def codex_mcp_overrides(polaris_enabled: bool) -> list[str]:
    """Codex -c flag pairs for MCP server injection (empty when disabled)."""
    if not polaris_enabled:
        return []
    return [
        "-c", 'mcp_servers.polaris.command="python3"',
        "-c", f'mcp_servers.polaris.args=["-m","adapters.mcp_polaris.server"]',
        "-c", f'mcp_servers.polaris.cwd="{REPO}"',
    ]
