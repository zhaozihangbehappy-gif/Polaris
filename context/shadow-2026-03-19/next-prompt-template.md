# 下次给 Claude / Codex 的提示模板

你可以直接复制下面这段：

---

先完整阅读以下文件，再基于这些上下文执行我接下来的任务：

- `/home/administrator/.openclaw/workspace/context/shadow-2026-03-19/overview.md`
- `/home/administrator/.openclaw/workspace/context/shadow-2026-03-19/brainstorming-context-verbatim.txt`
- `/home/administrator/.openclaw/workspace/context/shadow-2026-03-19/claude-critical-feedback.md`
- `/home/administrator/.openclaw/workspace/context/shadow-2026-03-19/codex-critical-feedback.md`
- `/home/administrator/.openclaw/workspace/context/shadow-2026-03-19/merged-summary.md`

要求：
1. 先吸收，不要先复述；
2. 如果上下文里存在冲突，明确指出；
3. 回答时优先引用已经收束出的约束，而不是重新发散；
4. 先完成我接下来的具体任务，再讨论延伸问题。

我的任务是：
[把你的新任务写在这里]

---

## 如果只想让对方快速进入状态

只让它先读这两个文件也可以：

- `/home/administrator/.openclaw/workspace/context/shadow-2026-03-19/overview.md`
- `/home/administrator/.openclaw/workspace/context/shadow-2026-03-19/merged-summary.md`
