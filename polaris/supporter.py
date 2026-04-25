# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from polaris import paths

TRIAL_DAYS = 7
POLARIS_PRODUCT_ID = os.getenv("POLARIS_PRODUCT_ID", "")  # TODO: set real Gumroad product id
GUMROAD_VERIFY_URL = "https://api.gumroad.com/v2/licenses/verify"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _load_token() -> dict[str, Any] | None:
    path = paths.supporter_token_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def _save_token(token: dict[str, Any]) -> None:
    path = paths.supporter_token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(token, indent=2) + "\n")


def ensure_trial_token() -> dict[str, Any]:
    paths.ensure_user_data()
    token = _load_token()
    if token:
        return token
    now = _now()
    token = {
        "kind": "trial",
        "status": "trial",
        "created_at": _iso(now),
        "expires_at": _iso(now + timedelta(days=TRIAL_DAYS)),
    }
    _save_token(token)
    return token


def token_state() -> dict[str, Any]:
    token = _load_token()
    if token is None:
        token = ensure_trial_token()
    status = token.get("status", "missing")
    expires_at = token.get("expires_at")
    if status == "trial" and expires_at:
        try:
            expires = datetime.fromisoformat(expires_at)
        except ValueError:
            expires = _now() - timedelta(seconds=1)
        if expires <= _now():
            token["status"] = "expired"
            _save_token(token)
    token["channel"] = current_channel(token)
    return token


def current_channel(token: dict[str, Any] | None = None) -> str:
    token = token or token_state()
    return "fresh" if token.get("status") in {"trial", "active"} else "stable"


def fresh_allowed(token: dict[str, Any] | None = None) -> bool:
    token = token or token_state()
    return token.get("status") in {"trial", "active"}


def activate_license(license_key: str) -> tuple[bool, str]:
    if not POLARIS_PRODUCT_ID:
        return False, "POLARIS_PRODUCT_ID is not configured yet"
    try:
        response = requests.post(
            GUMROAD_VERIFY_URL,
            data={
                "product_id": POLARIS_PRODUCT_ID,
                "license_key": license_key,
                "increment_uses_count": "false",
            },
            timeout=15,
        )
    except requests.RequestException as exc:
        return False, f"Gumroad verify request failed: {exc}"
    try:
        payload = response.json()
    except ValueError:
        return False, f"Gumroad verify returned non-JSON (HTTP {response.status_code})"
    success = bool(payload.get("success"))
    if not success:
        message = payload.get("message") or payload.get("error") or f"verify failed (HTTP {response.status_code})"
        return False, str(message)
    token = {
        "kind": "supporter",
        "status": "active",
        "created_at": _iso(_now()),
        "expires_at": None,
        "license_key_suffix": license_key[-4:],
    }
    _save_token(token)
    return True, "Supporter token activated"
