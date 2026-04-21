# Polaris 三方会谈文档
## Claude Opus × Codex × 决策者

---

## 第零部分：会谈目的

Polaris v3.0 已通过全部技术门控（Platform 3: 44/44, Platform 2: 216/220），Codex 已签署"可发布"。技术层面的讨论已经结束。

本次三方会谈的议题是 **商业化路径**——如何在保留源码版权的前提下，把 Polaris 卖给全世界每一个日常用 agent 的人。

---

## 第一部分：已锁定的技术事实（不再讨论）

| 指标 | 数值 | 状态 |
|------|------|------|
| 总 pattern 数 | 167 | 锁定 |
| 覆盖生态 | 8 (python, node, docker, go, rust, java, terraform, ruby) | 锁定 |
| Holdout 首次命中率 | 53/80 = 66.2% (P0 生态 ≥60%) | 达标 |
| 成功路径 overhead | <2ms query, <1MB memory | 达标 |
| Reproduction 通过率 | 167/167 | 达标 |
| Platform 3 gates | 44/44 pass | 达标 |
| Codex 签署 | "可发布" | 确认 |

---

## 第二部分：产品本质（三方共识基础）

### Polaris 是什么

Agent execution skill。给 AI agent 装上环境错误的**确定性修复能力**。

- **不做推理，做查表**。见过的错误走反射弧（regex match → hint apply），没见过的退回给 LLM
- **零损耗**。成功路径 <2ms，不烧 token，不打断执行流
- **可验证**。每个 pattern 有 reproduction case，每个 fix 可证伪

### 产品价值的三层结构

1. **钩子（首次 wow）**：prebuilt 经验库首次就命中修复，用户零配置
2. **粘性（有/无落差）**：关掉 Polaris 后 agent 变笨，同模型不同体验
3. **飞轮（贡献正反馈）**：用户经验 → 验证 → 入库 → 其他用户命中

---

## 第三部分：商业化辩论记录

### 立场 A（Claude Opus 初始建议）：BSL 许可证

- 源码可读，个人/小团队免费，企业付费
- 参考 HashiCorp、MariaDB 的 BSL 模式
- 优点：法律保护强，商业边界清晰
- **决策者反对理由**：
  - Polaris 还没有市场份额，BSL 会吓跑早期用户
  - 协议层需要开放才能成为标准
  - 真正的护城河不是源码，是数据

### 立场 B（决策者确定路径）：开放协议 + 商业知识库

核心思路：**免费的是管道，收费的是水**

| 层 | 策略 | 开源/商业 |
|----|------|-----------|
| 协议层 | Polaris Protocol（hint kinds, fingerprint schema, query interface） | 完全开源，Apache 2.0 或类似 |
| 引擎层 | polaris-core（匹配引擎、本地存储、CLI） | 开源，CLA/DCO 保护 |
| 数据层 | Polaris Verified Knowledge Base | 商业授权，按生态/按量/按 SLA 定价 |
| 平台集成 | API、仪表盘、团队协作 | SaaS 商业 |

#### 为什么这样切

1. **协议开放 → 成为标准**：让每个 agent 框架都支持 Polaris hint format，protocol adoption 是第一优先
2. **引擎开源 → 降低试用门槛**：任何人都能 `pip install polaris-skill` 跑起来
3. **知识库收费 → 真正的护城河**：167 个 verified pattern 只是起点；覆盖 50 个生态、5000 个 pattern、经过百万次生产验证的知识库，是别人无法轻易复制的
4. **CLA/DCO → 永久版权**：社区贡献的 pattern 经过验证管线后，版权归项目

#### 真正的护城河是四件事的合体

单拆任何一件都不够：
- **数据来源**：每个用户的 agent 在本地积累经验，opt-in 贡献
- **验证管线**：reproduction case + holdout recall + 生产验证 = 别人不敢直接抄数据
- **协议标准**：如果 Polaris Protocol 成为事实标准，别人只能 extend，不能 fork
- **默认分发**：如果 Claude/OpenAI/Cursor 等平台默认集成，网络效应碾压后来者

### 目标客户分层

| 阶段 | 目标 | 商业模式 |
|------|------|----------|
| Phase 1 (现在) | Agent 平台方（Anthropic, OpenAI, Cursor, Windsurf） | 集成合作，平台默认开启 |
| Phase 2 | 重度 agent 用户团队（DevOps, SRE, CI/CD 重度用户） | Team plan, 按席位/按量 |
| Phase 3 | 长尾开发者 | Freemium，免费 prebuilt + 付费 premium patterns |

---

## 第四部分：需要三方讨论的开放问题

### Q1：协议标准化的时机

协议层现在就开放，还是等到有 2-3 个平台集成后再标准化？

- **开放太早**：可能被大平台 fork 后自己定标准
- **开放太晚**：每个平台做自己的 hint format，Polaris 变成又一个私有格式

### Q2：知识库定价模型

- **按生态定价**：python pack $X/月, 全生态 $Y/月
- **按 pattern 命中量**：每 1000 次 hit 收费
- **按 SLA**：免费版有 community patterns，付费版有 verified + 24h 更新承诺
- 混合？

### Q3：首个平台合作方的优先级

假设 Anthropic、OpenAI、Cursor 同时有兴趣，优先投入哪个？考虑：
- 技术集成难度
- 用户基数
- 品牌背书效应
- 对协议标准化的推动力

### Q4：社区贡献的激励设计

用户贡献 pattern 后能得到什么？
- Credit（"your contribution, verified in N deployments"）
- 付费用户的免费额度
- Leaderboard / reputation
- Revenue share（贡献的 pattern 被付费用户使用时分润）

### Q5：与现有 agent 框架的关系

Polaris 是独立 skill 还是嵌入 agent 框架？
- 独立 → 跨平台，但需要每个框架单独集成
- 嵌入 → 深度集成一个框架，但锁定平台

---

## 第五部分：给 Codex 的背景补充

Codex，你在之前的审计中确认了 Polaris 的技术可发布性。现在讨论的是商业化路径。

你需要知道的关键上下文：
1. 决策者明确反对 BSL，理由是 Polaris 还没有市场份额，协议层必须开放才能成为标准
2. 决策者认为真正的护城河是"数据来源 + 验证管线 + 协议标准 + 默认分发"四件事的合体，不是源码保护
3. 决策者倾向于先打平台方（Phase 1），不是先打长尾开发者
4. CLA/DCO 是底线要求——社区可以贡献，但版权归项目

请从你的角度评估：
- 这个商业化路径的风险点在哪里？
- 协议标准化有没有被大平台架空的风险？如何防范？
- 167 个 pattern 的知识库体量够不够支撑收费？到多少才够？
- 你见过类似的 "开放协议 + 商业数据" 模式成功的案例吗？

---

*文档生成时间：2026-03-18*
*参与方：Claude Opus (技术实现 + 初始商业建议) | Codex (技术审计 + 商业评估) | 决策者 (最终裁定)*
