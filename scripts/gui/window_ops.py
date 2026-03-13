#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from typing import Any


def _run_powershell(script: str) -> str:
    cmd = [
        '/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe',
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-Command',
        script,
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def set_window_rect(hwnd: int, left: int, top: int, width: int, height: int) -> dict[str, Any]:
    ps = rf"""
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Win32 {{
  [DllImport("user32.dll", SetLastError=true)]
  public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);
}}
"@
$ok = [Win32]::MoveWindow([IntPtr]{hwnd}, {left}, {top}, {width}, {height}, $true)
[PSCustomObject]@{{ ok = $ok; hwnd = {hwnd}; left = {left}; top = {top}; width = {width}; height = {height} }} | ConvertTo-Json -Compress
"""
    out = _run_powershell(ps)
    return json.loads(out) if out else {'ok': False}


def activate_window_by_title_fragment(title_fragment: str) -> dict[str, Any]:
    escaped = title_fragment.replace("'", "''")
    ps = rf"""
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Win32 {{
  [DllImport("user32.dll", SetLastError=true)]
  public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll", SetLastError=true)]
  public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);
}}
"@
$p = Get-Process | Where-Object {{ $_.MainWindowTitle -like '*{escaped}*' -and $_.MainWindowHandle -ne 0 }} | Select-Object -First 1
if (-not $p) {{
  [PSCustomObject]@{{ ok = $false; reason = 'not_found'; titleFragment = '{escaped}' }} | ConvertTo-Json -Compress
  exit 0
}}
[Win32]::ShowWindowAsync($p.MainWindowHandle, 5) | Out-Null
$ok = [Win32]::SetForegroundWindow($p.MainWindowHandle)
[PSCustomObject]@{{ ok = $ok; hwnd = $p.MainWindowHandle; title = $p.MainWindowTitle }} | ConvertTo-Json -Compress
"""
    out = _run_powershell(ps)
    return json.loads(out) if out else {'ok': False}
