#!/usr/bin/env bash
set -euo pipefail
cd /home/administrator/.openclaw/workspace/tools/playwright-free
npx playwright install chromium >/tmp/openclaw-playwright-install.log 2>&1 || true
cd /home/administrator/.openclaw/workspace
export NODE_PATH=/home/administrator/.openclaw/workspace/tools/playwright-free/node_modules
node scripts/browser/playwright_smoke.js
