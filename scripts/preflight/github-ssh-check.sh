#!/usr/bin/env bash
set -euo pipefail

echo '[1/3] remote check'
git -C /home/administrator/.openclaw/workspace remote -v

echo '[2/3] github ssh auth check'
set +e
ssh -T git@github.com
code=$?
set -e
if [ "$code" -ne 1 ]; then
  echo "Unexpected ssh exit code: $code" >&2
  exit "$code"
fi

echo '[3/3] fetch check'
git -C /home/administrator/.openclaw/workspace fetch --dry-run origin || git -C /home/administrator/.openclaw/workspace fetch origin

echo 'github ssh preflight OK'
