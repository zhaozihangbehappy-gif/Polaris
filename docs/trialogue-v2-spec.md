# Trialogue v2 — 最小可信三方群聊架构规范

## 设计原则

**任何一层都不能既演戏又当证人。**

展示层、路由层、执行层、会话存证层，不能由同一组件同时控制。

---

## 组件职责

### 1. 群聊脚本 (`chat.py`)

**职责：解析输入 + 格式化输出**

- 接收用户键盘输入
- 用正则硬解析 `@claude` / `@codex` / `@all`（不用 AI 猜）
- 把 target + message 传给 launcher
- 把 launcher 返回的原始回复格式化显示
- 维护本地聊天记录文件（纯展示用，不作为验真依据）

**禁止：**
- 禁止直接调用 `claude`、`codex` 或任何 agent CLI
- 禁止读写 `~/.claude/`、`~/.codex/`
- 禁止生成或伪造 session ID
- 禁止修改 launcher 返回的原始回复内容

### 2. Launcher (`launcher.sh`)

**职责：执行 CLI 调用 + 记录调用证据**

- 接收参数：`target`（claude/codex）、`message`、`session_id`（可选，首次为空）
- **二进制路径通过配置文件显式声明（不自动发现）：**
  配置文件 `trialogue-v2.conf` 中写死：
  ```
  CLAUDE_BIN=/home/administrator/.local/bin/claude
  CODEX_BIN=/home/administrator/.local/bin/codex
  ```
  launcher 启动时：
  1. 读取配置中的绝对路径
  2. 校验路径存在且可执行
  3. 记录 SHA-256 hash（`sha256sum <path>`）和版本号
  4. 如果 hash 或路径不一致于上次记录 → 输出警告到 stderr
  5. **始终用配置中的绝对路径调用，不用裸命令名，不用 command -v**
- 执行真实 CLI 命令：
  - Claude: `/home/administrator/.local/bin/claude -p --session-id <id> --output-format text "<message>"`
  - Codex: `/home/administrator/.local/bin/codex exec "<message>"`
- 记录调用日志到 `~/.openclaw/trialogue/audit.jsonl`，每条包含：
  - 调用时间戳（ISO 8601）
  - 完整命令行（含绝对路径）
  - 目标 agent
  - 可执行文件绝对路径
  - 可执行文件 SHA-256
  - CLI 版本号
  - PID
  - 父进程 PID（`$PPID`）
  - 进程启动时间（`/proc/<pid>/stat` 或 `ps -o lstart`）
  - 完整 argv
  - 原始 stdout
  - 原始 stderr
  - exit code
  - session ID 确认结果（见下方 session 确认闭环）
- 将原始 stdout 返回给 chat.py

**禁止：**
- 禁止修改原始 stdout/stderr 内容
- 禁止读写 chat.py 的聊天记录
- 禁止与 OpenClaw 进程通信
- 禁止从环境变量继承 PATH（launcher 内部硬编码 PATH 或仅用绝对路径）

**关键设计：launcher 是 shell 脚本，不是 Python。** 因为：
- shell 脚本可读性最高，行数最少
- 不依赖任何框架
- 任何人 `cat launcher.sh` 就能看懂它做了什么

**环境隔离要求：**
- launcher.sh 所有外部调用走配置文件中的绝对路径，不依赖 PATH
- launcher.sh shebang 使用 `#!/bin/bash`（不在 shebang 中传递 shell 选项，因为 shebang 参数解析跨平台不可靠）
- **start.sh 必须用 `/bin/bash --noprofile --norc launcher.sh` 显式启动 launcher**，由调用方保证 rc 文件不被加载
- 脚本开头显式 `export PATH=/usr/bin:/bin`（仅供 jq、sha256sum、pgrep 等基础工具使用）
- 禁止 source 任何 shell rc 文件

### 3. tmux

**职责：隔离 + 观察，仅此而已**

- 提供一个独立窗口运行群聊，不污染外部 CLI
- 可选双 pane：左 = 群聊界面，右 = launcher 审计日志实时 tail
- tmux 不做任何逻辑，不做任何验证

**禁止：**
- 禁止使用 `capture-pane` 抓取内容作为程序输入
- 禁止使用 `send-keys` 模拟用户输入
- 禁止将 tmux 显示内容作为真伪证据

### 4. OpenClaw

**职责：路由器（可选），不是执行器**

- 如果用户在 OpenClaw 会话中说"开群聊"，OpenClaw 只做一件事：启动 tmux + chat.py
- OpenClaw 不参与消息路由、不调用 agent CLI、不接触 session
- 群聊启动后 OpenClaw 的工作就结束了
- **OpenClaw 启动群聊时，不得向 tmux/chat.py/launcher 传递自身环境变量。** start.sh 必须用 `env -i` 或显式清洁环境启动，防止 PATH/别名/函数注入。

**禁止：**
- 禁止在群聊过程中代为转发消息
- 禁止读写 `~/.claude/`、`~/.codex/` 的 session 文件
- 禁止生成或管理 session ID
- 禁止修改 launcher 的审计日志
- 禁止向 launcher 传递环境变量（启动链路必须经过环境清洗）

---

## 验真流程

### 用户验真三步法

**第一步：直接 resume agent 原生会话**

```bash
claude --resume <session-id>
# 进入后看到的对话记录应与群聊中 Claude 的发言完全一致

codex resume <session-id>
# 同上
```

**第二步：比对审计日志**

```bash
cat ~/.openclaw/trialogue/audit.jsonl | jq .
```

每条日志包含完整命令、PID、时间戳。可与 agent 原生 session 文件交叉比对：
- Claude PID 映射: `~/.claude/sessions/<pid>.json`
- Claude 完整对话: `~/.claude/projects/<project-path>/<sessionId>.jsonl`
- Claude 输入索引: `~/.claude/history.jsonl`
- Codex: `~/.codex/sessions/<date>/<session-file>.jsonl`

**第三步：检查进程身份**

审计日志记录了每次调用的完整进程身份。验证方法：

```bash
# 审计日志中每条记录包含：
# - pid, ppid, start_time, binary_path, binary_sha256, cli_version, argv

# 从审计日志中提取 binary_path，用该路径验证（不用 command -v）
CLAUDE_PATH=$(jq -r 'select(.target=="claude") | .binary_path' ~/.openclaw/trialogue/audit.jsonl | tail -1)
sha256sum "$CLAUDE_PATH"   # 应与审计日志中的 binary_sha256 一致

CODEX_PATH=$(jq -r 'select(.target=="codex") | .binary_path' ~/.openclaw/trialogue/audit.jsonl | tail -1)
sha256sum "$CODEX_PATH"

# 或直接引用配置文件中的绝对路径
source ~/.openclaw/scripts/trialogue-v2/trialogue-v2.conf
sha256sum "$CLAUDE_BIN"
sha256sum "$CODEX_BIN"
```

注意：PID 会复用，单独的 PID 不构成身份证明。必须结合 PID + 启动时间 + 二进制路径 + PPID 四项才能定位唯一进程。

### 用户不应信任的证据

- tmux 里显示的任何文本
- chat.py 的聊天记录文件
- 任何中间层打印的 "session ID"（必须与 agent 原生记录交叉验证）

---

## 信任边界与已知风险

### 当前环境的残余风险（Level 1 下明确接受的）

OpenClaw、claude、codex 运行在同一个 OS 用户 (`administrator`) 下。这意味着：

1. **session store 篡改**：OpenClaw 可以写 `~/.claude/` 和 `~/.codex/`，直接修改对话记录
2. **二进制替换**：claude 和 codex 的可执行文件位于用户目录下（`~/.local/bin/claude` → symlink → `~/.local/share/claude/versions/2.1.79`；`~/.local/bin/codex` → symlink → `~/.openclaw/acpx-home/node_modules/.bin/codex`）。OpenClaw 同用户下可以替换这些文件或修改 symlink 指向。此时"绝对路径 + hash + version"只会形成一套自洽的假证据，因为验证时读到的已经是被替换后的二进制。
3. **审计日志篡改**：审计日志存放在 `~/.openclaw/trialogue/audit.jsonl`，同用户下可直接修改

**Level 1 的定位：** 这些残余风险在 Level 1 下是**明确接受**的。Level 1 的防护目标是"提高造假成本、让造假留下更多痕迹"，不是"彻底杜绝造假"。彻底杜绝只能靠 Level 2（OS 用户隔离）。

### 缓解措施（按严格程度递增）

**Level 1 — 最小实现（当前可落地）：**
- launcher.sh 独立于 OpenClaw，用户可直接审计
- launcher 用绝对路径调用 CLI，记录二进制 hash + 版本
- launcher 启动时清洗环境（`env -i` 或硬编码 PATH）
- 审计日志包含完整进程身份（PID、PPID、启动时间、argv、二进制路径）
- chat.py 不接触 session store
- session ID 有确认闭环（见下方）

**Level 2 — OS 用户隔离（真实信任边界）：**
- OpenClaw 运行在 `openclaw` 用户下
- claude/codex 运行在 `administrator` 用户下
- OpenClaw 物理上无法写 `~/.claude/` 和 `~/.codex/`
- 这是唯一能真正阻止 session store 篡改的措施

注：~~文件权限隔离（chmod 700）~~不构成有效缓解。同用户下的 OpenClaw 可以绕过目录权限，因为 owner 是同一个人。已删除此虚假层级。

---

## 不可接受的实现

以下任一条出现，架构即为不可信：

1. chat.py 直接调用 `claude` 或 `codex`（绕过 launcher）
2. launcher 修改或过滤 agent 的原始输出
3. OpenClaw 在群聊运行期间代为路由消息
4. 任何组件使用 tmux `capture-pane` 或 `send-keys` 作为程序逻辑
5. session ID 由非 agent 原生进程生成（Claude 的 `--session-id` 除外，因为 Claude CLI 设计上接受外部传入），且未经确认闭环验证
6. 审计日志中 `session_confirmed` 为 false 的记录被当作可信证据使用
7. 单一组件同时控制"发给谁 + 实际执行 + 展示结果"三件事
8. launcher 从环境变量继承 PATH 或 source 了 shell rc 文件
9. CLI 调用使用裸命令名而非绝对路径

---

## 最小可接受实现

能交付的最小版本包含：

| 文件 | 行数估计 | 作用 |
|------|---------|------|
| `chat.py` | ~80 行 | 输入解析 + 格式化显示 |
| `launcher.sh` | ~40 行 | CLI 调用 + 审计日志 |
| `start.sh` | ~10 行 | 启动 tmux + chat.py |

总计约 130 行代码。任何人 10 分钟内可以通读完毕。

### 启动方式

```bash
# 启动群聊
~/.openclaw/scripts/trialogue-v2/start.sh --topic "讨论定价"

# 另一个终端验真
claude --resume <id>
codex resume <id>
cat ~/.openclaw/trialogue/audit.jsonl
```

### Session ID 确认闭环

Session ID 不是"记下来就够了"，必须确认 agent 确实采用了它。

**Claude 的确认闭环（基于本机真实存储模型）：**

Claude CLI 的实际落盘结构（已验证）：
- `~/.claude/sessions/<pid>.json` — PID → sessionId 映射，如 `{"pid":64571,"sessionId":"523e90a3-..."}`
- `~/.claude/history.jsonl` — 用户输入索引，每行含 sessionId + message
- `~/.claude/projects/<project-path>/<sessionId>.jsonl` — **完整对话记录**，每行含 sessionId、message、timestamp、entrypoint

确认步骤：
1. launcher 生成 UUID，传入 `claude -p --session-id <uuid> --output-format text "<message>"`
2. 记录 CLI 进程的 PID
3. 调用完成后，执行确认验证：

**核心确认（必须通过）：**
   a. 根据 launcher 实际 cwd 计算 project slug（规则：将 cwd 绝对路径中的 `/` 替换为 `-`，**保留开头的 `-`**，例 `/home/user` → `-home-user`）。拼出 `~/.claude/projects/<slug>/<uuid>.jsonl`，检查该文件是否存在。如果精确路径找不到，扫描所有 project 目录查找该 session 文件。
   b. 读取该 JSONL 文件中最后一条 `type=user` 的 `message.content`，确认内容包含本次发送的 message 文本。
   c. 以上两项全通过 → `session_confirmed: true`

**加分验证（可选，`claude -p` 非交互模式可能不写这些文件）：**
   d. 检查 `~/.claude/sessions/<pid>.json` 是否存在且 sessionId 匹配（`claude -p` 模式可能不生成此文件）
   e. 检查 `~/.claude/history.jsonl` 中是否有对应 sessionId 条目（`claude -p` 模式可能不写入此索引）

4. 核心确认失败 → `session_confirmed: false`，记录具体哪项失败
5. 加分验证结果记录在 confirmation 详情中，但不影响 confirmed 判定

**Codex 的确认闭环：**

Codex CLI 不支持外部传入 `--session-id`，session ID 由 Codex 自己生成。

1. 调用前：快照 `~/.codex/sessions/` 目录（记录所有现有文件名 + mtime）
2. 执行 `codex exec "..."`
3. 调用后：再次扫描目录，找出**新增的**文件（排除调用前已存在的文件）
4. 如果新增恰好一个文件 → 从中提取 session ID，记录 `session_confirmed: true`
5. 如果新增零个或多个文件（并发冲突）→ 记录 `session_confirmed: false`，标记为不可信
6. **launcher 不生成 Codex 的 ID，只提取并确认**

**并发约束（硬性要求）：**

群聊运行期间，**该 OS 用户下不允许有任何其他 Codex 会话启动或恢复**。包括：
- 不允许手动在其他终端运行 `codex exec` 或 `codex resume`
- 不允许其他自动化进程（包括 OpenClaw）启动 Codex
- 不允许同时运行多个群聊实例

原因：Codex 的 session 提取依赖 `~/.codex/sessions/` 目录快照 diff，任何并发写入都会导致错绑。如果违反此约束，launcher 会检测到多个新增文件并标记 `session_confirmed: false`，但错绑风险仍在（两个文件可能在扫描窗口内交替出现）。

launcher 启动时应检查是否有其他 codex 进程在运行（`pgrep -u $USER codex`），如有则拒绝启动并报错。

**审计日志中 session 字段的完整结构：**

Claude 示例：
```json
{
  "session_id": "abc-123-def",
  "session_source": "launcher_generated",
  "session_confirmed": true,
  "confirmation_checks": {
    "pid_mapping": {"path": "/home/administrator/.claude/sessions/64571.json", "found": true, "sid_match": true},
    "conversation_file": {"path": "/home/administrator/.claude/projects/<computed-from-cwd>/abc-123-def.jsonl", "found": true},
    "message_match": {"expected_substring": "看看定价逻辑", "found": true}
  },
  "resume_command": "claude --resume abc-123-def"
}
```

Codex 示例：
```json
{
  "session_id": "019cf948-207f-7000-ab3e-d5e3909c2f02",
  "session_source": "agent_native",
  "session_confirmed": true,
  "confirmation_checks": {
    "pre_snapshot_count": 3,
    "post_snapshot_count": 4,
    "new_files": ["rollout-2026-03-19T14-01-00-019cf948-207f-7000-ab3e-d5e3909c2f02.jsonl"],
    "concurrent_codex_processes": 0
  },
  "resume_command": "codex resume 019cf948-207f-7000-ab3e-d5e3909c2f02"
}
```
