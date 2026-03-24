#!/bin/bash
# Trialogue v3 — 唯一启动入口
# Level 2 时由 openclaw 用户通过 sudo -u administrator 调用
# 职责：启动 tmux session，不做任何其他事

set -euo pipefail

TOPIC="${1:?用法: start.sh <主题>}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONF="${SCRIPT_DIR}/trialogue-v3.conf"
DEFAULT_WORKDIR="/home/administrator/trialogue"
if [[ -d "$DEFAULT_WORKDIR" ]]; then
  WORKDIR="$DEFAULT_WORKDIR"
else
  WORKDIR="$(pwd)"
fi

# 读取审计日志路径
source "$CONF"

# 确保审计日志目录存在
mkdir -p "$(dirname "$AUDIT_LOG")"
touch "$AUDIT_LOG"
PRIVATE_TMP_DIR="${TRIALOGUE_PRIVATE_TMP_DIR:-${WORKSPACE}/state/tmp}"
SHARED_META_DIR="${TRIALOGUE_SHARED_META_DIR:-${WORKSPACE}/state/shared-meta}"
mkdir -p "$PRIVATE_TMP_DIR" "$SHARED_META_DIR"

# 如果已有 session 则先提示
if tmux has-session -t openclaw-chat 2>/dev/null; then
  echo "群聊 session 已存在。"
  echo "  附加: tmux attach -t openclaw-chat"
  echo "  结束: tmux kill-session -t openclaw-chat"
  exit 0
fi

# 将参数写入临时 env 文件，tmux 内的 shell 通过 source 读取
# 这样避免在 tmux shell 命令中内联插值任何用户输入
ENV_FILE=$(mktemp -p "$PRIVATE_TMP_DIR" trialogue-env-XXXXXX)
cat > "$ENV_FILE" <<ENVEOF
export _TRI_TOPIC=$(printf '%q' "$TOPIC")
export _TRI_LAUNCHER=${SCRIPT_DIR}/launcher.sh
export _TRI_CONF=${CONF}
export _TRI_AUDIT=${AUDIT_LOG}
export _TRI_CHAT=${SCRIPT_DIR}/chat.py
export _TRI_WORKDIR=${WORKDIR}
export _TRI_ENV_FILE=${ENV_FILE}
export TRIALOGUE_PRIVATE_TMP_DIR=${PRIVATE_TMP_DIR}
export TRIALOGUE_SHARED_META_DIR=${SHARED_META_DIR}
export TMPDIR=${PRIVATE_TMP_DIR}
ENVEOF
chmod 600 "$ENV_FILE"

# 启动 tmux session
# 左 pane: 读取 env 文件启动 chat.py
# 右 pane: tail 审计日志
# 两个 pane 都通过 source env 文件获取路径，不做字符串插值
tmux new-session -d -s openclaw-chat -x 200 -y 50 \
  "/bin/bash --noprofile --norc -c 'source $ENV_FILE && cd \"\$_TRI_WORKDIR\" && env -i HOME=$HOME TERM=\$TERM PATH=/usr/bin:/bin:/usr/local/bin python3 \$_TRI_CHAT --topic \"\$_TRI_TOPIC\" --launcher \"\$_TRI_LAUNCHER\" --conf \"\$_TRI_CONF\"; rm -f \$_TRI_ENV_FILE; exec bash'"

tmux split-window -h -t openclaw-chat \
  "/bin/bash --noprofile --norc -c 'source $ENV_FILE && cd \"\$_TRI_WORKDIR\" && echo \"══ 审计日志 (实时) ══\" && tail -f \$_TRI_AUDIT | jq --unbuffered . 2>/dev/null || tail -f \$_TRI_AUDIT; exec bash'"

tmux select-pane -t openclaw-chat:0.0

echo "群聊已启动。"
echo "  附加: tmux attach -t openclaw-chat"
echo "  左 pane = 群聊界面"
echo "  右 pane = 审计日志实时流"
