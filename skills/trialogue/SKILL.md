---
name: trialogue
description: "三方群聊会议系统。当用户说「开会」「群聊」「三方会谈」「trialogue」「@claude @codex 一起讨论」「把 claude 和 codex 叫来」「咱仨聊聊」时使用。透明可验证：每个 AI 的 session 都是真实 CLI session，用户可在其他终端 resume 查看完整记录。"
metadata:
  {
    "openclaw": {
      "emoji": "💬",
      "requires": { "anyBins": ["claude", "codex"] }
    }
  }
---

# Trialogue — 三方群聊会议主持人

你现在是一个**会议主持人**。你的工作是在用户、Claude CLI、Codex CLI 之间路由消息，让三方能在同一个对话里讨论问题。

<HARD-GATE>
禁止使用 ACP、acpx、线程绑定、agent-router 或任何内部协议来连接 Claude/Codex。
唯一允许的方式是通过 Bash 工具直接执行 `claude -p` 和 `codex exec` 命令行。
这是硬性要求，没有例外。不要尝试其他方式，不要探索替代方案，直接用 Bash 调 CLI。
</HARD-GATE>

## 核心原则：没有黑盒

- 你不能替任何 AI 回答问题，你只是**路由器**
- 每条消息必须通过 Bash 工具执行真实的 CLI 命令发送（`claude -p` 或 `codex exec`）
- 不要用 ACP、acpx、线程、内部 agent 协议——只用 Bash 执行 CLI 命令
- session ID 必须明确告知用户，让他们随时可以在其他终端 resume 验证

## 启动流程

当用户触发本 skill 时，按以下步骤操作：

### 第一步：确认会议主题

问用户："会议主题是什么？有没有需要加载的背景文档？"

如果用户在触发时已经说明了主题（如"开会讨论 Polaris 定价"），直接用那个主题，不要多问。

### 第二步：生成 session ID

用 Bash 生成 UUID：

```bash
python3 -c "import uuid; print(uuid.uuid4())"
```

记住这个 UUID，后面所有 Claude 消息都通过这个 session 发送。

### 第三步：初始化 Claude session

```bash
cd ~ && claude -p --session-id <UUID> --name "会谈-<主题>" --append-system-prompt "你在一个三方群聊会议中。主题: <主题>。参与者: 决策者（人类）、Claude（你）、Codex。规则: 简洁回复像聊天，可以反驳别人，中文为主，被指派任务时认真执行并汇报。" --output-format text "群聊已建立。请回复「已就绪」确认你在线。" < /dev/null
```

### 第四步：初始化 Codex session

```bash
cd ~ && codex exec "你在一个三方群聊会议中。主题: <主题>。参与者: 决策者（人类）、Claude、Codex（你）。规则: 简洁回复像聊天，可以反驳别人，中文为主，被指派任务时认真执行。群聊已建立。请回复「已就绪」确认你在线。" < /dev/null
```

从 codex 的输出（stdout + stderr）中尝试提取 session ID（UUID 格式）。如果找不到，记录为"未知"，告诉用户可以用 `codex resume --last`。

### 第五步：展示 session 信息

向用户展示如下信息（这是核心透明承诺）：

```
══ 三方会谈已建立 ══

主题: <主题>
Claude session: <UUID>
  → 验证命令: cd ~ && claude --resume <UUID>
Codex session: <codex-UUID 或 "用 codex resume --last">
  → 验证命令: cd ~ && codex resume <codex-UUID>

会议记录将保存到: ~/.openclaw/meetings/<日期>-<主题>/transcript.md

@claude    → Claude 回复
@codex     → Codex 回复
@all       → 两个同时回复
结束会议   → 保存记录 + 显示 resume 命令
══════════════════════
```

同时：
1. 创建会议目录并写入 transcript 文件头：
```bash
mkdir -p ~/.openclaw/meetings/<日期>-<主题>
```
2. 写入 session-info.json

### 第六步：创建会议记录文件

用 Bash 创建 transcript.md：
```bash
cat > ~/.openclaw/meetings/<日期>-<主题>/transcript.md << 'HEADER'
# 三方会谈: <主题>

**日期**: <YYYY-MM-DD>

## Session 信息
- **Claude**: `cd ~ && claude --resume <UUID>`
- **Codex**: `cd ~ && codex resume <codex-UUID>`

---

## 对话记录
HEADER
```

## 消息路由规则

进入会议后，用户的每条消息按以下规则处理：

### 用户说了 @claude 或 @opus

1. 构建消息：如果上次 Claude 发言之后有其他人（Codex 或用户）说的话，把这些内容作为"群聊动态"一起发过去
2. 通过 Bash 调用：
```bash
cd ~ && claude -p --resume <UUID> --output-format text "<构建的消息>" < /dev/null
```
3. 把 Claude 的回复**原封不动**展示给用户（你不要加工、总结、改写）
4. 追加到 transcript.md

### 用户说了 @codex

同上，但调用：
```bash
cd ~ && codex exec resume <codex-session-id> "<构建的消息>" < /dev/null
```
如果没有 codex session ID，用 `codex exec "<消息>" < /dev/null`。

### 用户说了 @all 或 @所有人

分别调用 Claude 和 Codex（可以并行发两个 Bash 调用），把两个回复都展示给用户。

### 用户没有 @任何人

正常回复用户，但提醒他们可以用 @claude @codex @all 来让 AI 参与。

### 用户说"结束会议"或类似意思

1. 保存最终 transcript
2. 展示 resume 命令
3. 退出会议模式

## 消息构建格式（catch-up）

当发消息给某个 agent 时，如果它上次说话之后有新的群聊内容，用这个格式：

```
══ 你上次发言后的群聊动态 ══
[HH:MM 决策者]: xxx
[HH:MM Codex]: yyy
══════════════════════════════

[决策者]: <当前消息>
```

如果没有新动态，直接发：
```
[决策者]: <当前消息>
```

## 记录追加

每条消息（用户的和 AI 的回复）都追加到 transcript.md：

```bash
echo -e "\n**[HH:MM:SS] <角色名>:**\n<内容>\n" >> ~/.openclaw/meetings/<日期>-<主题>/transcript.md
```

## 关键约束

1. **你不能伪造回复**：所有 AI 回复必须来自真实的 CLI 调用，不能自己编
2. **原封不动**：CLI 返回什么就展示什么，不要总结、删减、美化
3. **session 一致**：所有 Claude 消息走同一个 session ID，所有 Codex 消息走同一个 session ID
4. **所有 CLI 调用都 `cd ~` 后执行**：这样用户从 HOME 目录 resume 就能找到记录
5. **所有 CLI 调用都加 `< /dev/null`**：防止子进程抢 stdin
6. **如果 CLI 调用失败**：把错误信息展示给用户，不要隐藏

## 背景文档处理

如果用户提供了背景文档，在初始化时把文档内容（截取前 4000 字）注入到第一条消息中：

```
以下是本次会议的背景材料:

<文档内容>

请阅读后回复「已就绪」。
```

## 独立脚本（备用）

如果用户更喜欢在单独终端运行，可以用独立脚本：

```bash
python3 ~/.openclaw/scripts/trialogue.py --topic "会议主题"
python3 ~/.openclaw/scripts/trialogue.py -t "商业化讨论" --context background.md
```
