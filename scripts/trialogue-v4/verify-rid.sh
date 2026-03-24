#!/bin/bash
# 根据 RID 汇总一次群聊请求的审计证据。

set -euo pipefail

RID="${1:-}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONF="${SCRIPT_DIR}/trialogue-v3.conf"

if [[ -z "$RID" ]]; then
  echo "用法: $0 <rid>" >&2
  exit 1
fi

if [[ ! -f "$CONF" ]]; then
  echo "配置文件不存在: $CONF" >&2
  exit 1
fi

source "$CONF"

python3 - "$RID" "$AUDIT_LOG" <<'PY'
import json
import sys

rid = sys.argv[1]
audit_log = sys.argv[2]

records = []
with open(audit_log, "r", encoding="utf-8", errors="replace") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("rid") == rid:
            records.append(obj)

if not records:
    print(f"未找到 RID: {rid}", file=sys.stderr)
    sys.exit(2)

latest = {}
for rec in records:
    latest[rec.get("target", "unknown")] = rec

print(f"RID: {rid}")
print(f"records: {len(records)} (showing latest per target)")
for target in ("claude", "codex"):
    rec = latest.get(target)
    if not rec:
        continue
    verify = rec.get("verify_commands", {})
    print("")
    print(f"[{target}]")
    print(f"confirmed: {rec.get('session_confirmed')}")
    print(f"session_id: {rec.get('session_id') or '(none)'}")
    print(f"session_file: {rec.get('session_file') or '(none)'}")
    if verify.get("resume_command"):
        print(f"resume: {verify['resume_command']}")
    if verify.get("verify_file_command"):
        print(f"verify_file: {verify['verify_file_command']}")
    if verify.get("verify_store_command"):
        print(f"verify_store: {verify['verify_store_command']}")
    if verify.get("verify_rid_command"):
        print(f"verify_rid: {verify['verify_rid_command']}")
PY
