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

# ── 参数解析 ──
TARGET=""
MESSAGE=""
SESSION_ID=""
RESUME_SESSION="0"
SKIP_MEMORY="0"
CONF=""
META_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)     TARGET="$2"; shift 2 ;;
    --message)    MESSAGE="$2"; shift 2 ;;
    --session-id) SESSION_ID="$2"; shift 2 ;;
    --resume)     RESUME_SESSION="1"; shift ;;
    --skip-memory) SKIP_MEMORY="1"; shift ;;
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

# ── 读取配置 ──
source "$CONF"
TMP_ROOT="${TRIALOGUE_PRIVATE_TMP_DIR:-${WORKSPACE}/state/tmp}"
mkdir -p "$TMP_ROOT"
RUNNER_PRESERVE_ENV=(
  TRIALOGUE_TARGET_NAME
  TRIALOGUE_TARGET_SOURCE
  TRIALOGUE_TARGET_PATH
  TRIALOGUE_TARGET_CWD_OVERRIDE
  TRIALOGUE_ROOM_ID
  TRIALOGUE_SANITIZER_MODE
  TRIALOGUE_SANITIZER_RAW_COUNT
  TRIALOGUE_SANITIZER_INJECTED_COUNT
  TRIALOGUE_SANITIZER_MODIFICATIONS
  TRIALOGUE_SANITIZER_REMOVED_TYPES
  TRIALOGUE_SANITIZER_SANITIZED
  TRIALOGUE_VERSION_GATE_POLICY
  TRIALOGUE_VERSION_GATE_ALLOWED
  TRIALOGUE_VERSION_GATE_REASON
  TRIALOGUE_VERSION_RECHECK_POLICY
  TRIALOGUE_VERSION_RECHECK_ALLOWED
  TRIALOGUE_VERSION_RECHECK_RESULT
  TRIALOGUE_VERSION_RECHECK_REASON
  TRIALOGUE_VERSION_RECHECK_CHANGED_FIELDS
  TRIALOGUE_VERSION_STARTUP_BINARY_PATH
  TRIALOGUE_VERSION_STARTUP_BINARY_SHA256
  TRIALOGUE_VERSION_STARTUP_CLI_VERSION
  TRIALOGUE_VERSION_INVOCATION_BINARY_PATH
  TRIALOGUE_VERSION_INVOCATION_BINARY_SHA256
  TRIALOGUE_VERSION_INVOCATION_CLI_VERSION
  TRIALOGUE_VERSION_INVOCATION_SNAPSHOT_MODE
)
RUNNER_PRESERVE_ENV_CSV="$(IFS=,; echo "${RUNNER_PRESERVE_ENV[*]}")"

if [[ "$TARGET" == "codex" && -n "${CODEX_RUNNER:-}" ]]; then
  [[ -x "$CODEX_RUNNER" ]] || { echo "Codex runner 不存在或不可执行: $CODEX_RUNNER" >&2; exit 1; }
  RUNNER_CONF="${CODEX_RUNNER_CONF:-$CONF}"
  RUNNER_ARGS=(
    --message "$MESSAGE"
    --conf "$RUNNER_CONF"
    --meta-file "$META_FILE"
    --room-id "${TRIALOGUE_ROOM_ID:-}"
    --target-name "${TRIALOGUE_TARGET_NAME:-meeting}"
    --target-source "${TRIALOGUE_TARGET_SOURCE:-default}"
    --target-path "${TRIALOGUE_TARGET_PATH:-}"
    --target-cwd-override "${TRIALOGUE_TARGET_CWD_OVERRIDE:-}"
  )
  [[ "$SKIP_MEMORY" == "1" ]] && RUNNER_ARGS+=(--skip-memory)
  if [[ -n "${CODEX_RUNNER_USER:-}" ]]; then
    exec sudo --preserve-env="$RUNNER_PRESERVE_ENV_CSV" -n -u "$CODEX_RUNNER_USER" "$CODEX_RUNNER" "${RUNNER_ARGS[@]}"
  fi
  exec "$CODEX_RUNNER" "${RUNNER_ARGS[@]}"
fi

if [[ "$TARGET" == "claude" && -n "${CLAUDE_RUNNER:-}" ]]; then
  [[ -x "$CLAUDE_RUNNER" ]] || { echo "Claude runner 不存在或不可执行: $CLAUDE_RUNNER" >&2; exit 1; }
  RUNNER_CONF="${CLAUDE_RUNNER_CONF:-$CONF}"
  RUNNER_ARGS=(
    --message "$MESSAGE"
    --conf "$RUNNER_CONF"
    --meta-file "$META_FILE"
    --session-id "$SESSION_ID"
  )
  [[ "$RESUME_SESSION" == "1" ]] && RUNNER_ARGS+=(--resume)
  [[ "$SKIP_MEMORY" == "1" ]] && RUNNER_ARGS+=(--skip-memory)
  if [[ -n "${CLAUDE_RUNNER_USER:-}" ]]; then
    exec sudo --preserve-env="$RUNNER_PRESERVE_ENV_CSV" -n -u "$CLAUDE_RUNNER_USER" "$CLAUDE_RUNNER" "${RUNNER_ARGS[@]}"
  fi
  exec "$CLAUDE_RUNNER" "${RUNNER_ARGS[@]}"
fi

# ── 选择二进制 ──
case "$TARGET" in
  claude) BIN="$CLAUDE_BIN" ;;
  codex)  BIN="$CODEX_BIN" ;;
  *) echo "无效 target: $TARGET" >&2; exit 1 ;;
esac

[[ ! -x "$BIN" ]] && { echo "二进制不存在或不可执行: $BIN" >&2; exit 1; }
REAL_BIN=$(readlink -f "$BIN")
BIN_HASH=$(sha256sum "$REAL_BIN" | cut -d' ' -f1)
BIN_VERSION=$("$BIN" --version 2>/dev/null || echo "unknown")

# ── Codex 并发检查 ──
# 不再硬拦截；并发风险交给 nonce 唯一命中确认，并把现场进程数写入审计。
CODEX_PROCS="0"
if [[ "$TARGET" == "codex" ]]; then
  CODEX_PROCS="$(pgrep -u "$(id -u)" -c -x codex 2>/dev/null || true)"
  CODEX_PROCS="${CODEX_PROCS//$'\n'/}"
  [[ "$CODEX_PROCS" =~ ^[0-9]+$ ]] || CODEX_PROCS="0"
fi

# ── Codex session 快照（诊断用；正式确认走 nonce 内容命中） ──
CODEX_PRE_SNAPSHOT=""
if [[ "$TARGET" == "codex" ]]; then
  CODEX_PRE_SNAPSHOT=$(find "$CODEX_SESSIONS" -type f -name "*.jsonl" 2>/dev/null | sort)
fi

# ── 执行 CLI ──
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ")
STDOUT_FILE=$(mktemp -p "$TMP_ROOT" trialogue-stdout-XXXXXX)
STDERR_FILE=$(mktemp -p "$TMP_ROOT" trialogue-stderr-XXXXXX)
MESSAGE_FILE=$(mktemp -p "$TMP_ROOT" trialogue-message-XXXXXX)
trap "rm -f '$STDOUT_FILE' '$STDERR_FILE' '$MESSAGE_FILE'" EXIT

# 把 MESSAGE 写入文件，python3 从文件读取，彻底避免 shell 插值
printf '%s' "$MESSAGE" > "$MESSAGE_FILE"

PRE_EXEC_TIME=$(date +%s)
CLAUDE_RESUME_FALLBACK="0"
CLAUDE_RESUME_FALLBACK_REASON=""
CLAUDE_RESUME_ORIGINAL_SESSION_ID=""
CLAUDE_RESUME_ORIGINAL_EXIT_CODE=""

run_claude() {
  local mode="$1"
  local sid="$2"
  : > "$STDOUT_FILE"
  if [[ "$mode" == "resume" ]]; then
    "$BIN" -p --resume "$sid" --output-format text "$MESSAGE" \
      < /dev/null > "$STDOUT_FILE" 2> >(tee -a "$STDERR_FILE" >&2) &
  else
    "$BIN" -p --session-id "$sid" --output-format text "$MESSAGE" \
      < /dev/null > "$STDOUT_FILE" 2> >(tee -a "$STDERR_FILE" >&2) &
  fi
  CLI_PID=$!
  CLI_START_TIME=$(stat -c %Y /proc/$CLI_PID 2>/dev/null || echo "$PRE_EXEC_TIME")
  CLI_PPID=$(awk '{print $4}' /proc/$CLI_PID/stat 2>/dev/null || echo "$$")
  wait $CLI_PID 2>/dev/null
  EXIT_CODE=$?
}

run_codex() {
  : > "$STDOUT_FILE"
  "$BIN" exec --skip-git-repo-check "$MESSAGE" \
    < /dev/null > "$STDOUT_FILE" 2> >(tee -a "$STDERR_FILE" >&2) &
  CLI_PID=$!
  CLI_START_TIME=$(stat -c %Y /proc/$CLI_PID 2>/dev/null || echo "$PRE_EXEC_TIME")
  CLI_PPID=$(awk '{print $4}' /proc/$CLI_PID/stat 2>/dev/null || echo "$$")
  wait $CLI_PID 2>/dev/null
  EXIT_CODE=$?
}

if [[ "$TARGET" == "claude" ]]; then
  [[ -z "$SESSION_ID" ]] && { echo "Claude 调用缺少 --session-id" >&2; exit 1; }
  if [[ "$RESUME_SESSION" == "1" ]]; then
    CLAUDE_RESUME_ORIGINAL_SESSION_ID="$SESSION_ID"
    run_claude "resume" "$SESSION_ID"
    if [[ "$EXIT_CODE" -ne 0 ]]; then
      CLAUDE_RESUME_FALLBACK="1"
      CLAUDE_RESUME_ORIGINAL_EXIT_CODE="$EXIT_CODE"
      CLAUDE_RESUME_FALLBACK_REASON="$(awk 'NF { print; exit }' "$STDERR_FILE")"
      echo "[launcher] Claude resume failed, retrying with a new session-id" | tee -a "$STDERR_FILE" >&2
      SESSION_ID="$(cat /proc/sys/kernel/random/uuid)"
      RESUME_SESSION="0"
      run_claude "create" "$SESSION_ID"
    fi
  else
    run_claude "create" "$SESSION_ID"
  fi
elif [[ "$TARGET" == "codex" ]]; then
  run_codex
fi

# ── Session 确认 + 审计 + 元数据：全部交给一个 python3 脚本 ──
# 所有数据通过环境变量和文件传递，零 shell 插值
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
export _L_RESUME_SESSION="$RESUME_SESSION"
export _L_META_FILE="$META_FILE"
export _L_STDOUT_FILE="$STDOUT_FILE"
export _L_STDERR_FILE="$STDERR_FILE"
export _L_MESSAGE_FILE="$MESSAGE_FILE"
export _L_CONF_PATH="$CONF"
export _L_AUDIT_LOG="$AUDIT_LOG"
export _L_CLAUDE_SESSIONS="$CLAUDE_SESSIONS"
export _L_CLAUDE_PROJECTS="$CLAUDE_PROJECTS"
export _L_CLAUDE_HISTORY="$CLAUDE_HISTORY"
export _L_CODEX_SESSIONS="${CODEX_SESSIONS:-}"
export _L_CODEX_PRE_SNAPSHOT="$CODEX_PRE_SNAPSHOT"
export _L_CODEX_PROCS="$CODEX_PROCS"
export _L_BIN="$BIN"
export _L_WORKDIR="$(pwd)"
export _L_MEMORY_SOURCE_FILES="${TRIALOGUE_MEMORY_SOURCE_FILES:-}"
export _L_MEMORY_MIRROR_GENERATED_AT="${TRIALOGUE_MEMORY_MIRROR_GENERATED_AT:-}"
export _L_TARGET_NAME="${TRIALOGUE_TARGET_NAME:-meeting}"
export _L_TARGET_SOURCE="${TRIALOGUE_TARGET_SOURCE:-default}"
export _L_TARGET_PATH="${TRIALOGUE_TARGET_PATH:-}"
export _L_TARGET_CWD_OVERRIDE="${TRIALOGUE_TARGET_CWD_OVERRIDE:-}"
export _L_ROOM_ID="${TRIALOGUE_ROOM_ID:-}"
export _L_CLAUDE_RESUME_FALLBACK="$CLAUDE_RESUME_FALLBACK"
export _L_CLAUDE_RESUME_FALLBACK_REASON="$CLAUDE_RESUME_FALLBACK_REASON"
export _L_CLAUDE_RESUME_ORIGINAL_SESSION_ID="$CLAUDE_RESUME_ORIGINAL_SESSION_ID"
export _L_CLAUDE_RESUME_ORIGINAL_EXIT_CODE="$CLAUDE_RESUME_ORIGINAL_EXIT_CODE"
export TRIALOGUE_EXTERNAL_AUDIT_ANCHOR="${HARDENING_EXTERNAL_AUDIT_ANCHOR:-disabled}"
export TRIALOGUE_SUMMARY_CHAIN_DIR="${HARDENING_SUMMARY_CHAIN_DIR:-}"
export TRIALOGUE_ANCHOR_DIR="${HARDENING_ANCHOR_DIR:-}"
export TRIALOGUE_ANCHOR_KEY_PATH="${HARDENING_ANCHOR_KEY_PATH:-}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "${SCRIPT_DIR}/_audit.py"
AUDIT_EXIT=$?

if [[ "$AUDIT_EXIT" -ne 0 ]]; then
  echo "致命错误：审计/元数据写入失败 (exit $AUDIT_EXIT)，拒绝返回 agent 输出" >&2
  exit 2
fi

# stdout 只有 agent 原始输出
cat "$STDOUT_FILE"
