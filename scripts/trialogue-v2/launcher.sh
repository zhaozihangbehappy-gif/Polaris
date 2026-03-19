#!/bin/bash
# Trialogue v2 Launcher — 执行 CLI 调用 + 审计记录 + session 确认闭环
# 必须由 /bin/bash --noprofile --norc 启动
#
# 输出协议：
#   stdout     → 纯 agent 原始输出
#   --meta-file → JSON 元数据文件
#   exit 0     → agent 调用完成 且 审计+元数据均已写入
#   exit 非零  → 任何环节失败

set -uo pipefail
export PATH=/usr/bin:/bin:/usr/local/bin

TARGET=""
MESSAGE=""
SESSION_ID=""
CONF=""
META_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)     TARGET="$2"; shift 2 ;;
    --message)    MESSAGE="$2"; shift 2 ;;
    --session-id) SESSION_ID="$2"; shift 2 ;;
    --conf)       CONF="$2"; shift 2 ;;
    --meta-file)  META_FILE="$2"; shift 2 ;;
    *) echo "未知参数: $1" >&2; exit 1 ;;
  esac
done

[[ -z "$TARGET" ]]  && { echo "缺少 --target" >&2; exit 1; }
[[ -z "$MESSAGE" ]] && { echo "缺少 --message" >&2; exit 1; }
[[ -z "$CONF" ]]    && { echo "缺少 --conf" >&2; exit 1; }
[[ ! -f "$CONF" ]]  && { echo "配置文件不存在: $CONF" >&2; exit 1; }
command -v python3 > /dev/null 2>&1 || { echo "错误：python3 不可用" >&2; exit 1; }

source "$CONF"

case "$TARGET" in
  claude) BIN="$CLAUDE_BIN" ;;
  codex)  BIN="$CODEX_BIN" ;;
  *) echo "无效 target: $TARGET" >&2; exit 1 ;;
esac

[[ ! -x "$BIN" ]] && { echo "二进制不存在或不可执行: $BIN" >&2; exit 1; }
REAL_BIN=$(readlink -f "$BIN")
BIN_HASH=$(sha256sum "$REAL_BIN" | cut -d' ' -f1)
BIN_VERSION=$("$BIN" --version 2>/dev/null || echo "unknown")

if [[ "$TARGET" == "codex" ]]; then
  CODEX_PROCS=$(pgrep -u "$(id -u)" -c -x codex 2>/dev/null || echo "0")
  if [[ "$CODEX_PROCS" -gt 0 ]]; then
    echo "错误：检测到其他 codex 进程正在运行" >&2
    exit 1
  fi
fi

CODEX_PRE_SNAPSHOT=""
if [[ "$TARGET" == "codex" ]]; then
  CODEX_PRE_SNAPSHOT=$(find "$CODEX_SESSIONS" -type f -name "*.jsonl" 2>/dev/null | sort)
fi

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ")
STDOUT_FILE=$(mktemp)
STDERR_FILE=$(mktemp)
MESSAGE_FILE=$(mktemp)
trap "rm -f '$STDOUT_FILE' '$STDERR_FILE' '$MESSAGE_FILE'" EXIT

printf '%s' "$MESSAGE" > "$MESSAGE_FILE"

PRE_EXEC_TIME=$(date +%s)

if [[ "$TARGET" == "claude" ]]; then
  [[ -z "$SESSION_ID" ]] && { echo "Claude 调用缺少 --session-id" >&2; exit 1; }
  "$BIN" -p --session-id "$SESSION_ID" --output-format text "$MESSAGE" \
    < /dev/null > "$STDOUT_FILE" 2> "$STDERR_FILE" &
  CLI_PID=$!
elif [[ "$TARGET" == "codex" ]]; then
  "$BIN" exec "$MESSAGE" \
    < /dev/null > "$STDOUT_FILE" 2> "$STDERR_FILE" &
  CLI_PID=$!
fi

CLI_START_TIME=$(stat -c %Y /proc/$CLI_PID 2>/dev/null || echo "$PRE_EXEC_TIME")
CLI_PPID=$(awk '{print $4}' /proc/$CLI_PID/stat 2>/dev/null || echo "$$")

wait $CLI_PID 2>/dev/null
EXIT_CODE=$?

export _L_TIMESTAMP="$TIMESTAMP"
export _L_TARGET="$TARGET"
export _L_REAL_BIN="$REAL_BIN"
export _L_BIN_HASH="$BIN_HASH"
export _L_BIN_VERSION="$BIN_VERSION"
export _L_CLI_PID="$CLI_PID"
export _L_CLI_PPID="$CLI_PPID"
export _L_CLI_START_TIME="$CLI_START_TIME"
export _L_PRE_EXEC_TIME="$PRE_EXEC_TIME"
export _L_EXIT_CODE="$EXIT_CODE"
export _L_SESSION_ID="$SESSION_ID"
export _L_META_FILE="$META_FILE"
export _L_STDOUT_FILE="$STDOUT_FILE"
export _L_STDERR_FILE="$STDERR_FILE"
export _L_MESSAGE_FILE="$MESSAGE_FILE"
export _L_AUDIT_LOG="$AUDIT_LOG"
export _L_CLAUDE_SESSIONS="$CLAUDE_SESSIONS"
export _L_CLAUDE_PROJECTS="$CLAUDE_PROJECTS"
export _L_CLAUDE_HISTORY="$CLAUDE_HISTORY"
export _L_CODEX_SESSIONS="${CODEX_SESSIONS:-}"
export _L_CODEX_PRE_SNAPSHOT="$CODEX_PRE_SNAPSHOT"
export _L_BIN="$BIN"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "${SCRIPT_DIR}/_audit.py"
AUDIT_EXIT=$?

if [[ "$AUDIT_EXIT" -ne 0 ]]; then
  echo "致命错误：审计/元数据写入失败 (exit $AUDIT_EXIT)，拒绝返回 agent 输出" >&2
  exit 2
fi

cat "$STDOUT_FILE"
