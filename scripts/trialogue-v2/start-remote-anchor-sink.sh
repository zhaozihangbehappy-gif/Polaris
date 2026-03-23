#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONF="${SCRIPT_DIR}/remote-anchor-sink.conf"
SESSION_NAME="trialogue-remote-anchor"

if [[ ! -f "$CONF" ]]; then
  echo "缺少配置文件: $CONF"
  echo "先从 remote-anchor-sink.conf.example 复制一份。"
  exit 1
fi

source "$CONF"

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
  echo "Remote anchor sink 已存在。"
  echo "  附加日志: tmux attach -t ${SESSION_NAME}"
  echo "  结束服务: tmux kill-session -t ${SESSION_NAME}"
  exit 0
fi

mkdir -p "$(dirname "$SINK_DB_PATH")"
mkdir -p "$(dirname "$SINK_PUBLISH_TOKEN_PATH")"
mkdir -p "$(dirname "$SINK_VERIFY_TOKEN_PATH")"

tmux new-session -d -s "$SESSION_NAME" -x 140 -y 40 \
  "/bin/bash --noprofile --norc -c 'python3 \"${SCRIPT_DIR}/remote_anchor_sink.py\" --conf \"${CONF}\"; exec bash'"

echo "Remote anchor sink 已启动。"
echo "  健康检查: http://${SINK_HOST}:${SINK_PORT}/health"
echo "  日志: tmux attach -t ${SESSION_NAME}"
echo "  停止: tmux kill-session -t ${SESSION_NAME}"
