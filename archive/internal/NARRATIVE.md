# Polaris 对外叙事与量化承诺（v4 契约根）

**签署日期**：2026-04-19
**适用版本**：v4 全部 gate 与对外物料
**废止条件**：Gate 2 实测数据与本文件承诺冲突时，回炉重签，不允许悄悄发布

---

## 1. 核心叙事（唯一对外主句）

> **Polaris 让你手里的代码 Agent 越用越好用：经验库持续增长，但每次只注入最相关的修复路径，context token 保持固定上限。**

任何对外首屏（README、landing、launch post、合作邮件、adapter package description）必须使用本句作为开篇。不允许改写、扩写、合并。副标题和段落可以展开，但**主句不可修改**。

## 2. 对外禁用表达

以下过时或不可信表达，在本 v4 周期内对外文案中禁用：

- "AI 一遇到 npm/pip 就瞎试" — 2026 年的 agent 已经质变，继续说显得落后
- "让 AI 突然变聪明" — 不可信，评论区会钉
- "覆盖 8 个生态" — 真相是 3 个 P0 + 5 个分层，平铺叙述属于自我伤害
- "命中率" — 这是内部术语，对外改用 "首次定位成功率 / CI pass rate / 根因定位轮数"
- "P1/P2 凑数" — 内部判断用语，对外一律改为 "重点优化 / 扩展验证 / 实验支持"

## 3. 量化承诺（工程硬门）

以下门限写进 v4 测试套件，未通过不允许对外宣传对应条款：

| 承诺项 | 阈值 | 测量方式 |
|--------|------|----------|
| 单次查询延迟 | 本地索引 p95 ≤ 10ms | `eval/metrics.py` 采集 1000 次查询 |
| 单次注入 context token | ≤ 300 tokens | tokenizer 实测，硬上限 |
| 经验库规模无关性 | official / full schema pool / synthetic stress pool 下，上两项指标不劣化 | 分档 benchmark |
| 发布锚点 | A=verified_live、B=sandbox-ready、D=schema-valid 三档均由 validator 输出 | `scripts/pattern_validator_v4.py` |

**关键：上三项承诺只约束"注入给 agent 的上下文与查询延迟"，不承诺"检索本身的 CPU/IO/tool call 零成本"。**避免被反驳 "你查一次 MCP 不也花 tool call"。

## 4. Gate 2 评测门（反自嗨保险丝）

Gate 2 Eval Harness 的 pass criteria 必须同时满足：

1. 至少两端能跑完整回路（Codex CLI 为 P0，Claude Code CLI 为 P1，Cursor 为 P2 transcript runner）
2. 每个 case 产出可复现 JSON 结果（seed 固定、prompt 固定）
3. **裸跑 vs 接 Polaris 的差值：不允许只在 token 或轮数上改善**。必须在 **CI pass rate 或根因定位轮数** 中至少一个硬指标上改善 ≥ 30%；仅 token 省下来不构成发布依据。
4. 若上述硬指标达不到，**结论是"疼点已迁移"**，必须回炉重选 case 或重新定位，不允许挑软指标发布。

## 5. Case 来源混合方案

- v0 闭环阶段：70% 现有 pattern 反向构造 + 30% 真实 GitHub issue/CI log
- Launch 前：真实 issue/CI log 比例必须 ≥ 50%
- 冷启动不允许 100% pattern 反查（"自己考自己"嫌疑），也不允许 100% 真实 issue（启动太慢）

## 6. 三端 runner 优先级

- **P0 — Codex CLI**：本地最容易脚本化，订阅可用
- **P1 — Claude Code CLI**：Pro plan 可用，有 rate limit 约束，需要预算会话配额
- **P2 — Cursor**：auto 模式可用，但自动化最麻烦、版本漂移最快。v0 用 transcript/manual runner 占位采集，不强求全自动

## 7. 签署

- 定位与产品形态：已于 2026-04-19 三方会谈定稿（参见 `project_polaris_platform0.md`）
- 本叙事契约：等待 Codex 签字确认；签字后 Gate 1（pattern schema 升级）开工
- 本契约修改须三方重新会谈，不允许单方修订对外承诺
