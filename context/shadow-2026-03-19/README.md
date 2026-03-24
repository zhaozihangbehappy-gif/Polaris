# Shadow 上下文包（2026-03-19）

这个文件夹用于给 Claude / Codex / 其他 agent 预加载今天关于 **Shadow** 项目的讨论材料，避免在会话里直接粘贴超长上下文把输入框撑爆。

## 建议使用方式

先让 agent 读这些文件，再下具体任务。

### 最简用法

1. 先读：
   - `overview.md`
   - `brainstorming-context-verbatim.txt`
   - `claude-critical-feedback.md`
   - `codex-critical-feedback.md`
2. 再执行任务，例如：
   - 总结共识
   - 写 spec
   - 找核心风险
   - 提炼 v0 定义

## 文件说明

- `overview.md`
  - 一页式摘要，适合先快速建立全局理解
- `brainstorming-context-verbatim.txt`
  - 今天主会话里 Shadow brainstorming 的原始上下文摘录
- `claude-critical-feedback.md`
  - Claude 的批判性、建设性意见整理稿
- `codex-critical-feedback.md`
  - Codex 的批判性、建设性意见整理稿
- `merged-summary.md`
  - Northern Light 对 Claude + Codex 意见的汇总压缩
- `next-prompt-template.md`
  - 下次可直接复用的喂给 agent 的提示模板

## 推荐喂法

你可以直接对 agent 说：

> 先完整阅读 `/home/administrator/.openclaw/workspace/context/shadow-2026-03-19/README.md` 提到的几份文件，再基于这些上下文执行我接下来的任务。不要先复述，先吸收上下文。

## 当前核心结论（一句话）

Shadow 当前最大的敌人不是技术本身，而是**定义膨胀**；必须先把项目拆成 Helmet / Exo / Link 三段，并优先证明一个最小闭环为什么成立。
