"""Trialogue v4 — Runtime configuration loader.

Reads trialogue-v4.conf (key=value format, # comments).
Falls back to defaults if file doesn't exist.
"""
from __future__ import annotations

import os
from typing import Any

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONF_PATH = os.path.join(SCRIPT_DIR, "trialogue-v4.conf")

# Defaults (must match trialogue-v4.conf.example)
# audit_mode: "local" (best-effort), "strict" (failure blocks pipeline), "disabled" (skip)
# NOTE: remote audit anchor is not implemented in v4.
DEFAULTS: dict[str, str] = {
    "audit_mode": "local",
    "max_response_bytes": "524288",
    "default_timeout": "15",
    "sanitizer_mode": "strict",
    "search_endpoint": "",
    "remote_anchor_sink": "",
    "remote_anchor_url": "",
    "remote_anchor_interval": "0",
}


def load_conf(path: str = "") -> dict[str, str]:
    """Load config from file. Returns dict of key→value strings."""
    if not path:
        path = os.environ.get("TRIALOGUE_CONF", DEFAULT_CONF_PATH)
    conf = dict(DEFAULTS)
    if not os.path.exists(path):
        return conf
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            conf[key] = value
    return conf


def get_int(conf: dict[str, str], key: str, default: int = 0) -> int:
    try:
        return int(conf.get(key, str(default)))
    except (ValueError, TypeError):
        return default


# Module-level singleton — loaded once on first import
_conf: dict[str, str] | None = None


def get_conf() -> dict[str, str]:
    """Get the singleton config dict. Loaded once, cached."""
    global _conf
    if _conf is None:
        _conf = load_conf()
    return _conf
