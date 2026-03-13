#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class BridgeError(RuntimeError):
    pass


@dataclass
class BridgeClient:
    base_url: str
    auth_header: str = 'x-openclaw-desktop-key'
    auth_key: str | None = None
    timeout_seconds: int = 15

    @classmethod
    def from_env(cls) -> 'BridgeClient':
        return cls(
            base_url=os.environ.get('OPENCLAW_DESKTOP_BASE_URL', 'http://127.0.0.1:7788'),
            auth_header=os.environ.get('OPENCLAW_DESKTOP_AUTH_HEADER', 'x-openclaw-desktop-key'),
            auth_key=os.environ.get('OPENCLAW_DESKTOP_KEY'),
            timeout_seconds=int(os.environ.get('OPENCLAW_DESKTOP_TIMEOUT_SECONDS', '15')),
        )

    def post_json(self, path: str, payload: dict[str, Any]) -> Any:
        if not self.auth_key:
            raise BridgeError('OPENCLAW_DESKTOP_KEY is not set')
        body = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            url=self.base_url.rstrip('/') + '/' + path.lstrip('/'),
            data=body,
            method='POST',
            headers={
                self.auth_header: self.auth_key,
                'Content-Type': 'application/json',
            },
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=self.timeout_seconds) as resp:
                data = resp.read().decode('utf-8')
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode('utf-8', errors='replace')
            raise BridgeError(f'HTTP {exc.code} calling {path}: {detail}') from exc
        except urllib.error.URLError as exc:
            raise BridgeError(f'Network error calling {path}: {exc}') from exc
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return data

    def list_windows(self) -> Any:
        return self.post_json('window.inspect', {'action': 'list'})

    def activate(self, hwnd: int) -> Any:
        return self.post_json('window.inspect', {'action': 'activate', 'window': {'hwnd': int(hwnd)}})

    def capture_window(self, hwnd: int, purpose: str) -> Any:
        return self.post_json('desktop.capture', {
            'target': 'window',
            'window': {'hwnd': int(hwnd)},
            'format': 'png',
            'purpose': purpose,
        })

    def move_mouse(self, hwnd: int, x: int, y: int, reason: str) -> Any:
        return self.post_json('desktop.input', {
            'action': 'move',
            'x': int(x),
            'y': int(y),
            'window': {'hwnd': int(hwnd)},
            'verifyForeground': True,
            'abortKey': 'esc',
            'reason': reason,
        })
