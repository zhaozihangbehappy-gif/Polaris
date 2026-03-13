#!/usr/bin/env bash
set -euo pipefail
PLAN_WIN=$(wslpath -w "$1")
SCRIPT_WIN=$(wslpath -w /home/administrator/.openclaw/workspace/scripts/windows/gui_macro_runner.ps1)
'/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe' -NoProfile -ExecutionPolicy Bypass -File "$SCRIPT_WIN" -PlanPath "$PLAN_WIN"
