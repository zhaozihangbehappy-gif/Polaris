#!/bin/bash
# Trialogue v3 Codex Runner — app-server thin wrapper

set -euo pipefail
export PATH=/usr/bin:/bin:/usr/local/bin

CONF=""
MESSAGE=""
META_FILE=""
SANDBOX_MODE=""
APPROVAL_MODE=""
ROOM_ID=""
TARGET_NAME=""
TARGET_SOURCE=""
TARGET_PATH=""
TARGET_CWD_OVERRIDE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --message)       MESSAGE="$2"; shift 2 ;;
    --conf)          CONF="$2"; shift 2 ;;
    --meta-file)     META_FILE="$2"; shift 2 ;;
    --sandbox-mode)  SANDBOX_MODE="$2"; shift 2 ;;
    --approval-mode) APPROVAL_MODE="$2"; shift 2 ;;
    --room-id)       ROOM_ID="$2"; shift 2 ;;
    --target-name)   TARGET_NAME="$2"; shift 2 ;;
    --target-source) TARGET_SOURCE="$2"; shift 2 ;;
    --target-path)   TARGET_PATH="$2"; shift 2 ;;
    --target-cwd-override) TARGET_CWD_OVERRIDE="$2"; shift 2 ;;
    *) echo "未知参数: $1" >&2; exit 1 ;;
  esac
done

[[ -n "$MESSAGE" ]]   || { echo "缺少 --message" >&2; exit 1; }
[[ -n "$CONF" ]]      || { echo "缺少 --conf" >&2; exit 1; }
[[ -f "$CONF" ]]      || { echo "配置文件不存在: $CONF" >&2; exit 1; }
[[ -n "$META_FILE" ]] || { echo "缺少 --meta-file" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "错误：python3 不可用" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

exec python3 "${SCRIPT_DIR}/codex_app_server_runner.py" \
  --message "$MESSAGE" \
  --conf "$CONF" \
  --meta-file "$META_FILE" \
  --sandbox-mode "$SANDBOX_MODE" \
  --approval-mode "$APPROVAL_MODE" \
  --room-id "$ROOM_ID" \
  --target-name "$TARGET_NAME" \
  --target-source "$TARGET_SOURCE" \
  --target-path "$TARGET_PATH" \
  --target-cwd-override "$TARGET_CWD_OVERRIDE"
