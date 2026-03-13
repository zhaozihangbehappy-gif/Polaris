#!/usr/bin/env bash
set -euo pipefail
cd /home/administrator/.openclaw/workspace

if ! env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY python3 - <<'PY'
import json, urllib.request, sys
body=json.dumps({'action':'list'}).encode()
req=urllib.request.Request('http://127.0.0.1:7788/window.inspect', data=body, method='POST', headers={'x-openclaw-desktop-key':'desktop-secret','Content-Type':'application/json'})
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
try:
    with opener.open(req, timeout=4) as r:
        sys.exit(0 if r.status == 200 else 1)
except Exception:
    sys.exit(1)
PY
then
  scripts/windows/run-start-desktop-bridge-from-wsl.sh >/tmp/openclaw-gui-start.log 2>&1 || {
    echo 'desktop bridge startup failed' >&2
    cat /tmp/openclaw-gui-start.log >&2
    exit 1
  }
fi

'/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe' -NoProfile -Command "Start-Process 'C:\\Program Files\\Blender Foundation\\Blender 5.0\\blender.exe'" >/dev/null 2>&1 || true
sleep 7

env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY OPENCLAW_DESKTOP_KEY=${OPENCLAW_DESKTOP_KEY:-desktop-secret} \
  python3 scripts/gui/run_gui_regression.py \
  --scenario G1 \
  --scenario G2 \
  --scenario G3 \
  --scenario G4 \
  --scenario G5 \
  --repeats 3
