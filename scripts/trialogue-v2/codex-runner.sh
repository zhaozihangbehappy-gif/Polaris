#!/bin/bash
# Trialogue v3 Codex Runner — 独立执行舱入口
# 设计目标：
#   1. broker 只调用本脚本，不直接调用 codex CLI
#   2. session confirm / 审计 / meta 输出都在 runner 内部完成
#   3. 运行目录、HOME、sandbox 可独立配置
# 注意：
#   codex exec 当前不支持 interactive approval；非交互 runner 下有效策略等同 never。

set -uo pipefail
export PATH=/usr/bin:/bin:/usr/local/bin

CONF=""
MESSAGE=""
META_FILE=""
SANDBOX_MODE=""
APPROVAL_MODE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --message)       MESSAGE="$2"; shift 2 ;;
    --conf)          CONF="$2"; shift 2 ;;
    --meta-file)     META_FILE="$2"; shift 2 ;;
    --sandbox-mode)  SANDBOX_MODE="$2"; shift 2 ;;
    --approval-mode) APPROVAL_MODE="$2"; shift 2 ;;
    *) echo "未知参数: $1" >&2; exit 1 ;;
  esac
done

[[ -z "$MESSAGE" ]]   && { echo "缺少 --message" >&2; exit 1; }
[[ -z "$CONF" ]]      && { echo "缺少 --conf" >&2; exit 1; }
[[ ! -f "$CONF" ]]    && { echo "配置文件不存在: $CONF" >&2; exit 1; }
[[ -z "$META_FILE" ]] && { echo "缺少 --meta-file" >&2; exit 1; }
command -v python3 > /dev/null 2>&1 || { echo "错误：python3 不可用" >&2; exit 1; }

source "$CONF"

BIN="${CODEX_BIN:-}"
[[ -n "$BIN" ]]              || { echo "配置缺少 CODEX_BIN" >&2; exit 1; }
[[ -x "$BIN" ]]              || { echo "二进制不存在或不可执行: $BIN" >&2; exit 1; }
[[ -n "${AUDIT_LOG:-}" ]]    || { echo "配置缺少 AUDIT_LOG" >&2; exit 1; }

RUNNER_HOME="${CODEX_RUNNER_HOME:-$HOME}"
RUNNER_WORKSPACE="${CODEX_RUNNER_WORKSPACE:-${WORKSPACE:-$(pwd)}}"
RUNNER_AUDIT_LOG="${CODEX_RUNNER_AUDIT_LOG:-$AUDIT_LOG}"
SANDBOX_MODE="${SANDBOX_MODE:-${CODEX_SANDBOX_MODE:-workspace-write}}"
APPROVAL_MODE="${APPROVAL_MODE:-${CODEX_APPROVAL_MODE:-never}}"
CODEX_MEMORY_SOURCE_DIR="${CODEX_MEMORY_SOURCE_DIR:-$RUNNER_HOME/.codex-facts}"
CODEX_MEMORY_LIVE_DIR="${CODEX_MEMORY_LIVE_DIR:-$RUNNER_WORKSPACE/state/codex-memory-live}"

export HOME="$RUNNER_HOME"
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$RUNNER_HOME/.config}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$RUNNER_HOME/.cache}"
export TRIALOGUE_WORKSPACE="$RUNNER_WORKSPACE"
export TRIALOGUE_CODEX_MEMORY_SOURCE_DIR="$CODEX_MEMORY_SOURCE_DIR"
export TRIALOGUE_CODEX_MEMORY_LIVE_DIR="$CODEX_MEMORY_LIVE_DIR"

mkdir -p "$(dirname "$RUNNER_AUDIT_LOG")"
touch "$RUNNER_AUDIT_LOG"
cd "$RUNNER_WORKSPACE" || { echo "工作目录不存在: $RUNNER_WORKSPACE" >&2; exit 1; }

REAL_BIN=$(readlink -f "$BIN")
BIN_HASH=$(sha256sum "$REAL_BIN" | cut -d' ' -f1)
BIN_VERSION=$("$BIN" --version 2>/dev/null || echo "unknown")

CODEX_PROCS="$(pgrep -u "$(id -u)" -c -x codex 2>/dev/null || true)"
CODEX_PROCS="${CODEX_PROCS//$'\n'/}"
[[ "$CODEX_PROCS" =~ ^[0-9]+$ ]] || CODEX_PROCS="0"
CODEX_PRE_SNAPSHOT=$(find "${CODEX_SESSIONS:-}" -type f -name "*.jsonl" 2>/dev/null | sort)

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ")
STDOUT_FILE=$(mktemp)
STDERR_FILE=$(mktemp)
MESSAGE_FILE=$(mktemp)
trap "rm -f '$STDOUT_FILE' '$STDERR_FILE' '$MESSAGE_FILE'" EXIT

printf '%s' "$MESSAGE" > "$MESSAGE_FILE"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export TRIALOGUE_MESSAGE_FILE="$MESSAGE_FILE"
export TRIALOGUE_TARGET_NAME="${TRIALOGUE_TARGET_NAME:-meeting}"
PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY'
import json
import os
from _memory import build_injected_message, load_memory

target_name = os.environ.get("TRIALOGUE_TARGET_NAME", "meeting")
message_file = os.environ["TRIALOGUE_MESSAGE_FILE"]
with open(message_file, "r", encoding="utf-8") as f:
    wrapped_message = f.read()

memory_result = load_memory("codex", target_name=target_name)
injected_message = build_injected_message(memory_result, wrapped_message)
with open(message_file, "w", encoding="utf-8") as f:
    f.write(injected_message)

with open(message_file + ".memory.json", "w", encoding="utf-8") as f:
    json.dump(
        {
            "source_files": memory_result.get("source_files", []),
            "mirror_generated_at": memory_result.get("mirror_generated_at", ""),
        },
        f,
        ensure_ascii=False,
    )
PY
MEMORY_META_FILE="${MESSAGE_FILE}.memory.json"
if [[ -f "$MEMORY_META_FILE" ]]; then
  export MEMORY_META_FILE
  export TRIALOGUE_MEMORY_SOURCE_FILES="$(python3 - <<'PY'
import json
import os
path = os.environ["MEMORY_META_FILE"]
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)
print("\n".join(data.get("source_files", [])))
PY
)"
  export TRIALOGUE_MEMORY_MIRROR_GENERATED_AT="$(python3 - <<'PY'
import json
import os
path = os.environ["MEMORY_META_FILE"]
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)
print(data.get("mirror_generated_at", ""))
PY
)"
  rm -f "$MEMORY_META_FILE"
fi

PRE_EXEC_TIME=$(date +%s)
: > "$STDOUT_FILE"

CMD=(
  "$BIN"
  exec
  --skip-git-repo-check
  -s "$SANDBOX_MODE"
  "$(cat "$MESSAGE_FILE")"
)

"${CMD[@]}" < /dev/null > "$STDOUT_FILE" 2> >(tee -a "$STDERR_FILE" >&2) &
CLI_PID=$!
CLI_START_TIME=$(stat -c %Y /proc/$CLI_PID 2>/dev/null || echo "$PRE_EXEC_TIME")
CLI_PPID=$(awk '{print $4}' /proc/$CLI_PID/stat 2>/dev/null || echo "$$")
wait $CLI_PID 2>/dev/null
EXIT_CODE=$?

export _L_TIMESTAMP="$TIMESTAMP"
export _L_TARGET="codex"
export _L_REAL_BIN="$REAL_BIN"
export _L_BIN_HASH="$BIN_HASH"
export _L_BIN_VERSION="$BIN_VERSION"
export _L_CLI_PID="$CLI_PID"
export _L_CLI_PPID="$CLI_PPID"
export _L_CLI_START_TIME="$CLI_START_TIME"
export _L_PRE_EXEC_TIME="$PRE_EXEC_TIME"
export _L_EXIT_CODE="$EXIT_CODE"
export _L_SESSION_ID=""
export _L_RESUME_SESSION="0"
export _L_META_FILE="$META_FILE"
export _L_STDOUT_FILE="$STDOUT_FILE"
export _L_STDERR_FILE="$STDERR_FILE"
export _L_MESSAGE_FILE="$MESSAGE_FILE"
export _L_AUDIT_LOG="$RUNNER_AUDIT_LOG"
export _L_CLAUDE_SESSIONS=""
export _L_CLAUDE_PROJECTS=""
export _L_CLAUDE_HISTORY=""
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
export _L_CLAUDE_RESUME_FALLBACK="0"
export _L_CLAUDE_RESUME_FALLBACK_REASON=""
export _L_CLAUDE_RESUME_ORIGINAL_SESSION_ID=""
export _L_CLAUDE_RESUME_ORIGINAL_EXIT_CODE=""

python3 "${SCRIPT_DIR}/_audit.py"
AUDIT_EXIT=$?

if [[ "$AUDIT_EXIT" -ne 0 ]]; then
  echo "致命错误：Codex runner 审计/元数据写入失败 (exit $AUDIT_EXIT)" >&2
  exit 2
fi

cat "$STDOUT_FILE"
