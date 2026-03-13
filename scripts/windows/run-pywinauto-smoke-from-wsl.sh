#!/usr/bin/env bash
set -euo pipefail
WINPATH=$(wslpath -w /home/administrator/.openclaw/workspace/scripts/windows/pywinauto_smoke.py)
'/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe' -NoProfile -Command "py \"$WINPATH\""
