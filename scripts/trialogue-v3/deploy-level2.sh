#!/bin/bash
# Trialogue v2 Level 2 一键部署
# 用法：sudo bash deploy-level2.sh
# 回滚：sudo bash deploy-level2.sh --rollback

set -euo pipefail

ADMIN_HOME="/home/administrator"
OC_USER="openclaw"

if [[ "${1:-}" == "--rollback" ]]; then
  echo "══ 回滚 Level 2 ══"

  if [[ -d "/home/$OC_USER/.openclaw" ]]; then
    echo "迁回 OpenClaw 数据..."
    cp -r /home/$OC_USER/.openclaw/openclaw.json "$ADMIN_HOME/.openclaw/" 2>/dev/null || true
    cp -r /home/$OC_USER/.openclaw/agents "$ADMIN_HOME/.openclaw/" 2>/dev/null || true
    cp -r /home/$OC_USER/.openclaw/bridge "$ADMIN_HOME/.openclaw/" 2>/dev/null || true
    cp -r /home/$OC_USER/.openclaw/update-check.json "$ADMIN_HOME/.openclaw/" 2>/dev/null || true
    chown -R administrator:administrator "$ADMIN_HOME/.openclaw/"
  fi

  echo "恢复权限..."
  chmod 755 "$ADMIN_HOME/.claude" 2>/dev/null || true
  chmod 755 "$ADMIN_HOME/.codex" 2>/dev/null || true
  chmod 755 "$ADMIN_HOME/.openclaw/scripts" 2>/dev/null || true
  chmod 755 "$ADMIN_HOME/.openclaw/trialogue" 2>/dev/null || true
  chmod 755 "$ADMIN_HOME/.local/bin" 2>/dev/null || true

  rm -f /etc/sudoers.d/openclaw-trialogue

  if id "$OC_USER" &>/dev/null; then
    echo "删除 $OC_USER 用户..."
    userdel -r "$OC_USER" 2>/dev/null || true
  fi

  echo "══ 回滚完成 ══"
  exit 0
fi

echo "══ Trialogue v2 Level 2 部署 ══"
echo ""

echo "[1/5] 创建 $OC_USER 用户..."
if id "$OC_USER" &>/dev/null; then
  echo "  用户已存在，跳过"
else
  useradd -r -m -s /bin/bash "$OC_USER"
  echo "  创建成功: $(id $OC_USER)"
fi

echo "[2/5] 迁移 OpenClaw 服务状态..."
OC_DEST="/home/$OC_USER/.openclaw"
mkdir -p "$OC_DEST"

for item in openclaw.json update-check.json; do
  if [[ -f "$ADMIN_HOME/.openclaw/$item" ]]; then
    cp "$ADMIN_HOME/.openclaw/$item" "$OC_DEST/$item"
    echo "  迁移: $item"
  fi
done

for dir in agents bridge; do
  if [[ -d "$ADMIN_HOME/.openclaw/$dir" ]]; then
    cp -r "$ADMIN_HOME/.openclaw/$dir" "$OC_DEST/$dir"
    echo "  迁移: $dir/"
  fi
done

chown -R "$OC_USER:$OC_USER" "$OC_DEST"
echo "  完成"

echo "[3/5] 配置 sudoers 规则..."
SUDOERS_FILE="/etc/sudoers.d/openclaw-trialogue"
SUDOERS_LINE="$OC_USER ALL=(administrator) NOPASSWD: $ADMIN_HOME/.openclaw/scripts/trialogue-v3/start.sh"

echo "$SUDOERS_LINE" > "$SUDOERS_FILE"
chmod 440 "$SUDOERS_FILE"

if visudo -cf "$SUDOERS_FILE" &>/dev/null; then
  echo "  sudoers 语法验证通过"
else
  echo "  错误：sudoers 语法无效！删除并退出"
  rm -f "$SUDOERS_FILE"
  exit 1
fi

echo "[4/5] 锁定文件权限..."

chmod 700 "$ADMIN_HOME/.claude"
echo "  ~/.claude → 700"

chmod 700 "$ADMIN_HOME/.codex"
echo "  ~/.codex → 700"

chmod 700 "$ADMIN_HOME/.openclaw/scripts"
echo "  ~/.openclaw/scripts → 700"

chmod 700 "$ADMIN_HOME/.openclaw/trialogue"
echo "  ~/.openclaw/trialogue → 700"

chmod 700 "$ADMIN_HOME/.local/bin"
echo "  ~/.local/bin → 700"

chmod 755 "$ADMIN_HOME/.openclaw/scripts/trialogue-v3/start.sh"
echo "  start.sh → 755"

echo "[5/5] 验证..."
echo ""

echo "  测试: openclaw 能否读取 ~/.claude/"
if su -s /bin/bash -c "cat $ADMIN_HOME/.claude/history.jsonl 2>&1" "$OC_USER" | grep -q "Permission denied"; then
  echo "  ✓ openclaw 无法读取 ~/.claude/"
else
  echo "  ✗ 警告：openclaw 仍可读取 ~/.claude/"
fi

echo "  测试: openclaw 能否读取 ~/.codex/"
if su -s /bin/bash -c "ls $ADMIN_HOME/.codex/ 2>&1" "$OC_USER" | grep -q "Permission denied"; then
  echo "  ✓ openclaw 无法读取 ~/.codex/"
else
  echo "  ✗ 警告：openclaw 仍可读取 ~/.codex/"
fi

echo "  测试: openclaw 能否通过 sudo 启动群聊"
if su -s /bin/bash -c "sudo -n -u administrator $ADMIN_HOME/.openclaw/scripts/trialogue-v3/start.sh --help 2>&1" "$OC_USER" | grep -q "用法"; then
  echo "  ✓ openclaw 可以 sudo 启动 start.sh"
else
  echo "  (sudo 测试需要 TTY，部署后手动验证)"
fi

echo ""
echo "══ 部署完成 ══"
echo ""
echo "启动群聊："
echo "  # 以 openclaw 用户身份"
echo "  sudo -u openclaw bash -c 'sudo -u administrator $ADMIN_HOME/.openclaw/scripts/trialogue-v3/start.sh \"主题\"'"
echo ""
echo "  # 或者直接以 administrator 身份（Level 1 模式）"
echo "  $ADMIN_HOME/.openclaw/scripts/trialogue-v3/start.sh \"主题\""
echo ""
echo "  # 附加到群聊 tmux session"
echo "  tmux attach -t openclaw-chat"
echo ""
echo "回滚："
echo "  sudo bash $0 --rollback"
