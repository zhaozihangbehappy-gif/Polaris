# Trialogue v2 Level 2 — 落地实施计划

## 前置条件

本计划基于已通过 Codex 审计的代码实现和 `trialogue-v2-spec.md` 架构规范。

当前代码文件（均已通过审计）：
```
~/.openclaw/scripts/trialogue-v2/
├── trialogue-v2.conf   # 二进制绝对路径 + session store 路径配置
├── start.sh            # tmux 启动入口（env 文件传参，防注入）
├── chat.py             # 群聊界面（@mention 硬解析 + --meta-file 协议）
├── launcher.sh         # CLI 调用（环境变量传数据，_audit.py 处理 JSON）
└── _audit.py           # 审计日志 + session 确认闭环 + 元数据生成
```

---

## Level 1 → Level 2 的核心变化

Level 1（当前）：所有组件同用户运行，信任边界靠代码自律
Level 2（目标）：OpenClaw 和 agent 执行链分属不同 OS 用户，信任边界靠内核强制

---

## 第一步：创建 openclaw 用户

```bash
sudo useradd -r -m -s /bin/bash openclaw
```

### 迁移策略：不做粗暴迁移

**只迁移 OpenClaw 服务自身的状态**，不动 administrator 侧的 agent 执行链：

迁移到 openclaw 用户：
```
openclaw.json          → /home/openclaw/.openclaw/openclaw.json
agents/                → /home/openclaw/.openclaw/agents/
bridge/                → /home/openclaw/.openclaw/bridge/
update-check.json      → /home/openclaw/.openclaw/update-check.json
```

**留在 administrator 侧（不迁移）：**
```
~/.openclaw/workspace/           # 工作目录
~/.openclaw/scripts/trialogue-v2/  # 群聊代码
~/.openclaw/trialogue/           # 审计日志
~/.openclaw/acpx-home/           # codex 二进制依赖（symlink 不断）
~/.claude/                       # Claude session store
~/.codex/                        # Codex session store
~/.local/bin/claude              # Claude 二进制
~/.local/bin/codex               # Codex 二进制（→ acpx-home）
```

---

## 第二步：配置 sudo 规则

openclaw 用户只允许执行一条命令：

```bash
# /etc/sudoers.d/openclaw-trialogue
openclaw ALL=(administrator) NOPASSWD: /home/administrator/.openclaw/scripts/trialogue-v2/start.sh
```

约束：
- 只能以 administrator 身份运行 start.sh
- 不能拿到 administrator 的任意 shell
- sudoers 默认 `env_reset` 清洗环境变量

---

## 第三步：文件权限锁定

```bash
# administrator 侧：禁止 openclaw 用户访问
chmod 700 /home/administrator/.claude
chmod 700 /home/administrator/.codex
chmod 700 /home/administrator/.openclaw/scripts
chmod 700 /home/administrator/.openclaw/trialogue
chmod 700 /home/administrator/.local/bin

# start.sh 需要 openclaw 能通过 sudo 执行
chown administrator:administrator /home/administrator/.openclaw/scripts/trialogue-v2/start.sh
chmod 755 /home/administrator/.openclaw/scripts/trialogue-v2/start.sh
```

---

## 第四步：启动链路

```
openclaw (OS 用户: openclaw)
  → sudo -u administrator /home/administrator/.openclaw/scripts/trialogue-v2/start.sh "主题"
    → tmux session (OS 用户: administrator)
      ├─ 左 pane: chat.py
      │   └─ /bin/bash --noprofile --norc launcher.sh --target claude --message "..." --meta-file /tmp/...
      │       └─ _audit.py (写审计日志 + session 确认 + 元数据)
      │       └─ /home/administrator/.local/bin/claude -p --session-id ...
      └─ 右 pane: tail -f audit.jsonl
```

环境清洗边界：
- sudoers `env_reset` 清掉 openclaw 的环境
- start.sh 用 `env -i` 启动 chat.py
- launcher.sh 由 `/bin/bash --noprofile --norc` 启动
- launcher.sh 内部 `export PATH=/usr/bin:/bin:/usr/local/bin`

---

## 第五步：验真流程

用户在任意终端（administrator 身份）：

```bash
# 1. 直接 resume agent 原生会话
claude --resume <session-id>
codex resume <session-id>

# 2. 查看 Claude 原生索引
tail -20 ~/.claude/history.jsonl

# 3. 查看 Codex 原生 session 文件
find ~/.codex/sessions -type f | tail

# 4. 查看审计日志（辅助对照）
tail -20 ~/.openclaw/trialogue/audit.jsonl

# 5. 确认 openclaw 用户无权访问
sudo -u openclaw cat ~/.claude/history.jsonl
# 应返回 Permission denied
```

判断原则：resume 对不上 → 判假；audit.jsonl 对不上 → 中间层有问题；只有群聊窗口对不上 → 优先信原生 CLI。

---

## 第六步：回滚方案

```bash
# 把 OpenClaw 数据搬回 administrator
sudo cp -r /home/openclaw/.openclaw/* /home/administrator/.openclaw/
sudo chown -R administrator:administrator /home/administrator/.openclaw/

# 删除 openclaw 用户
sudo userdel -r openclaw
sudo rm /etc/sudoers.d/openclaw-trialogue

# 群聊回退到 Level 1：直接以 administrator 运行 start.sh
```

---

## 实施顺序

| 步骤 | 内容 | 风险 | 可回滚 |
|------|------|------|--------|
| 1 | Level 1 测试（当前代码已通过审计） | 无 | N/A |
| 2 | 创建 openclaw 用户 | 低 | userdel -r |
| 3 | 迁移 OpenClaw 服务状态（不动 acpx-home） | 中 | 复制回来 |
| 4 | 配置 sudoers 规则 | 低 | 删除 sudoers 文件 |
| 5 | 锁定文件权限 | 低 | chmod 恢复 |
| 6 | Level 2 启动链测试 | 低 | 回退到 Level 1 |

---

## 已知限制

1. **群聊期间禁止该用户下其他 Codex 会话**：launcher 启动前 pgrep 检查
2. **不支持多群聊实例并行**：Codex session 快照 diff 在并发下不可靠
3. **Claude session 确认的加分项在 `claude -p` 模式下不可用**：PID 映射（`sessions/<pid>.json`）和 history.jsonl 在非交互模式下可能不写入，核心确认只依赖 conversation file + message 匹配
4. **同用户下二进制可替换**：Level 2 通过 OS 用户隔离缓解，Level 1 下是明确接受的残余风险
5. **codex 二进制路径**：`~/.local/bin/codex` → `~/.openclaw/acpx-home/...`，acpx-home 留在 administrator 侧，symlink 不断
