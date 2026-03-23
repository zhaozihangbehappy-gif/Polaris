#!/bin/bash
# Trialogue v2 — 浏览器 UI 启动入口

set -euo pipefail

TOPIC="${1:?用法: start-web.sh <主题> [端口]}"
PORT="${2:-8765}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONF="${SCRIPT_DIR}/trialogue-v2.conf"
SESSION_NAME="openclaw-chat-web"
DEFAULT_WORKDIR="/home/administrator/trialogue"
if [[ -d "$DEFAULT_WORKDIR" ]]; then
  WORKDIR="$DEFAULT_WORKDIR"
else
  WORKDIR="$(pwd)"
fi

source "$CONF"

mkdir -p "$(dirname "$AUDIT_LOG")"
touch "$AUDIT_LOG"
PRIVATE_TMP_DIR="${TRIALOGUE_PRIVATE_TMP_DIR:-${WORKSPACE}/state/tmp}"
SHARED_META_DIR="${TRIALOGUE_SHARED_META_DIR:-${WORKSPACE}/state/shared-meta}"
mkdir -p "$PRIVATE_TMP_DIR" "$SHARED_META_DIR"

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
  echo "Web UI session 已存在。"
  echo "  浏览器: http://127.0.0.1:${PORT}"
  echo "  附加日志: tmux attach -t ${SESSION_NAME}"
  echo "  结束服务: tmux kill-session -t ${SESSION_NAME}"
  exit 0
fi

ENV_FILE=$(mktemp -p "$PRIVATE_TMP_DIR" trialogue-web-env-XXXXXX)
cat > "$ENV_FILE" <<ENVEOF
export _TRI_TOPIC=$(printf '%q' "$TOPIC")
export _TRI_PORT=$(printf '%q' "$PORT")
export _TRI_LAUNCHER=${SCRIPT_DIR}/launcher.sh
export _TRI_CONF=${CONF}
export _TRI_AUDIT=${AUDIT_LOG}
export _TRI_SERVER=${SCRIPT_DIR}/server.py
export _TRI_WORKDIR=${WORKDIR}
export _TRI_ENV_FILE=${ENV_FILE}
export TRIALOGUE_PRIVATE_TMP_DIR=${PRIVATE_TMP_DIR}
export TRIALOGUE_SHARED_META_DIR=${SHARED_META_DIR}
export TMPDIR=${PRIVATE_TMP_DIR}
ENVEOF
chmod 600 "$ENV_FILE"

tmux new-session -d -s "$SESSION_NAME" -x 180 -y 48 \
  "/bin/bash --noprofile --norc -c 'source $ENV_FILE && env -i HOME=$HOME TERM=\$TERM PATH=/usr/bin:/bin:/usr/local/bin python3 \$_TRI_SERVER --topic \"\$_TRI_TOPIC\" --launcher \"\$_TRI_LAUNCHER\" --conf \"\$_TRI_CONF\" --audit-log \"\$_TRI_AUDIT\" --workdir \"\$_TRI_WORKDIR\" --host 127.0.0.1 --port \"\$_TRI_PORT\"; rm -f \$_TRI_ENV_FILE; exec bash'"

tmux split-window -h -t "$SESSION_NAME" \
  "/bin/bash --noprofile --norc -c 'source $ENV_FILE && echo \"══ 审计日志 (实时) ══\" && tail -f \$_TRI_AUDIT | jq --unbuffered . 2>/dev/null || tail -f \$_TRI_AUDIT; exec bash'"

tmux select-pane -t "${SESSION_NAME}:0.0"

echo "Web UI 已启动。"
echo "  浏览器: http://127.0.0.1:${PORT}"
echo "  日志: tmux attach -t ${SESSION_NAME}"
echo "  停止: tmux kill-session -t ${SESSION_NAME}"
