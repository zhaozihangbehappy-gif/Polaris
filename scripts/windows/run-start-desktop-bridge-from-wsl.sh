#!/usr/bin/env bash
set -euo pipefail
WINPATH=$(wslpath -w /home/administrator/.openclaw/workspace/scripts/windows/start-desktop-bridge.ps1)
'/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe' -NoProfile -ExecutionPolicy Bypass -File "$WINPATH"
