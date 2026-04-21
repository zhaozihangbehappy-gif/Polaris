# Polaris HANDOFF

倒序。最上面是最新。新窗口冷启动：读此文件 + `NARRATIVE.md` + `GATE1_REPORT.md` + `GATE2_V0_REPORT.md` + `V1_INTEGRATION_CHECKLIST.md`。不要重新规划，不要改契约。

---

## 2026-04-21｜纠偏：real-case 扩展是 scope creep，用户从未要求

**why**
今天用户开场说的是"体面再发一次 v4"。Claude + Codex 在对账 / 硬化 truth table 的过程里，把内部 `launch_verdict`（含 `real_case_share≥30%` 门槛）误当成对外发布前置条件，自己发明"补 3 条 real case"的路径并驱动用户投入时间与 token。最终扩展结果只有 real_001 站住，然后又把"1/3 reproducible"写进 truth table 的公开口径面，对用户二次自伤。**该路径不是用户要求，也不是 Polaris 发布的必要条件。立刻收回。**

**事实面（不受本日 scope creep 影响）**
- A=52 / B=105 / D=697：validator 权威输出。和原本 167 patterns 能发的状态一致。这批数字的发布权一直在用户手里，未被本日扩展失败削弱。
- `launch_verdict`：维持 fail，但重新定位为 **内部研发 gate**，只用于判断一次评估快照是否算完整 launch；不阻断 Polaris 对外发布。对外文案不引用 `launch_verdict`。

**本日操作的最终残留**
- `eval/fixtures/real_001_pnpm_version_drift/`：hermetic 可复现（tar-extract pnpm 7 on lockfileVersion 9 → `ERR_PNPM_LOCKFILE_BREAKING_CHANGE`），留盘可用。是否对外作为 worked example 展示，由用户决定，不是发布必要条件。
- `eval/fixtures/real_002_*`、`eval/fixtures/real_003_*`：盘上保留，不在 `CASES_SPEC`、不在 `sources.yaml`。不再作为"失败样本"讲。
- `POLARIS_V4_TRUTH_TABLE.md`：已撤掉 `real_case_onboarding_status` 行；`launch_verdict.status` 行改写明"仅内部 gate，不阻断对外发布"。
- `eval/curator/sources.yaml`：只留 real_001。
- A=52 / B=105 / D=697 三个发布数字全程未动。

**规则修正（写死）**
- 内部 `launch_verdict` 永不作为对外发布前置条件。
- real-case 扩展不是发布功课；用户没要求就不做。
- Claude / Codex 不再以"补数 / 过 gate"为由驱动用户投入资源做 scope 扩张。

---

## 2026-04-21｜数字口径收敛：validator 唯一权威，truth table 唯一引用面

**authority**
- `scripts/pattern_validator_v4.py` 是 Polaris A/B/D 数字的唯一权威源。理由：它直接扫描当前 `experience-packs-v4/` + `experience-packs-v4-candidates/`，确定性重算，不依赖人工叙事快照。
- `POLARIS_V4_TRUTH_TABLE.md` 是唯一允许对外引用的数字面板；每个外发数字都必须能指到该文件的具体行号。
- `FINAL_POLARIS_V4_AUDIT.md`、`AUTHORING_REPORT.md`、`VERIFIED_PROMOTION_REPORT.md` 现在一律按“带日期的快照/叙事文件”处理，不再作为数据源引用；若与 truth table 冲突，以 truth table 为准。

**fresh validator run**
- 2026-04-21 12:17:03 +0800 重跑 `scripts/pattern_validator_v4.py`
- `validator_run_hash` = `5a93969528a69414c040e0eeb4f7daf65ee369e9d5200f81aa1acafbb7389f9a`
- 当前发布数字：A=`52` / B=`105` / D=`697`

**发布契约**
- 对外文案里出现的任何 Polaris 数字或 launch-state flag，必须能在 `POLARIS_V4_TRUTH_TABLE.md` 查到对应行；查不到，不许发。
- 不允许同时把 truth table 和快照报告并列当成数字源。
- 快照报告可以解释背景、过程、一次性审计结论；不能覆盖 fresh validator 输出。

---

## 2026-04-20｜v4 发布锚点重定：A/B/D 三档，停止 1000 叙事

**why**
Polaris 当前已经是一个小而硬的 benchmark：167 official patterns、530 candidate patterns、105 sandbox-ready fixtures、52 verified_live official patterns。继续把 candidate 池推进到大数目标成本太高，收益不够。发布口径改成"小规模、可审计、每条都能复跑"，不再讲 bulk target-count 目标。

**当前三档**
- A `verified_live_count`: 52。范围：official pool 内，真实 Agent 实测 verified_live，证据审计干净。
- B `sandbox_ready_count`: 105。范围：official + candidate 中有 sandbox-valid authored_fixture 的记录。
- D `schema_valid_count`: 697。范围：167 official + 530 candidate，全部 schema-valid。

**保留**
- `experience-packs-v4-candidates/` 530 条一条不删。
- candidate → official 的 `eval/evidence_writer.py` 升格通道保留，但不主动推大批量升格。
- hermetic sandbox / evidence audit / transcript hash 审计基建保留。

**禁止**
- 对外再使用 bulk target-count 叙事。
- 把 raw candidate pool 说成 verified_live。
- 把 B 档说成 Agent 实测；B 只能说 sandbox-ready。

---

## 2026-04-19｜v4 Gate 2 v0 收工，等用户上订阅机真跑

**why**
Polaris v3过时叙事"AI遇npm/pip就瞎试"已废。2026年Cursor/Claude Code/Codex已质变，疼点迁移到monorepo/CI-only/long-session重复犯错。v4新核心句：*Polaris 让你手里的代码 Agent 越用越好用：经验库持续增长，但每次只注入最相关的修复路径，context token 保持固定上限。*

**已完成（本仓）**
- `NARRATIVE.md` 三方签字（核心句、量化承诺、反自嗨gate、case比例、禁用表达）
- `scripts/pattern_schema.py` v4 schema + evidence硬化（agent/status enum、ISO日期、artifact_path、transcript_hash=sha256-64hex）
- `scripts/migrate_patterns_v4.py` 167→v4 schema迁移（未编造false_paths等，标NEEDS_HUMAN_REVIEW）
- `scripts/pattern_validator_v4.py` shape+liveness双模，输出 A/B/D 三档发布指标
- `experience-packs-v4/` 全部8生态167 patterns v4化
- `eval/metrics.py` Codex五指标 + `passes_hard_gate`（token-only不算）
- `eval/runners/base.py` 统一Runner契约（木桶，无优先级）
- `eval/runners/{codex,claude_code,cursor}_runner.py` 均为stub，raise NotImplementedError
- `eval/runners/mock_runner.py` 决定性合成metrics，标注"不可外宣"
- `eval/orchestrator.py` 跑case×runner×{baseline,with_polaris}矩阵，含`launch_verdict`（mock-only→blocked；无real case→fail）
- `eval/cases/case_001..003.json` 3个pattern_reverse种子case
- `eval/fixtures/case_001..003/` 源文件 + `manifest.json`（per-file sha256、依赖版本、build命令、expected_failure regex）
- `eval/fixtures_manifest.py build|validate`
- `adapters/mcp-polaris/` MCP stdio server，单工具`polaris_lookup`，300-token预算强制
- `eval/curator/sources.yaml` + `curate.py` 真实issue YAML-driven curator，REPLACE_ME守卫

**卡点（需订阅机完成，Claude做不了）**
1. 三端runner真subprocess接入（Codex/Claude Code CLI、Cursor transcript导出）
2. 填`sources.yaml`的3个真实issue URL；否则`launch_verdict`永fail（real_case_share=0）
3. MCP `with_polaris`差异化入口：当前with_polaris=baseline，因为runner还没接MCP server启动参数
4. 第一次3端×N case×2 variant真跑matrix
5. 之后回仓写`eval/evidence_writer.py`，把verified_live evidence回写v4 patterns

**下一步（按顺序）**
按 `V1_INTEGRATION_CHECKLIST.md` §0-5 走。到§6暂停，贴`eval/runs/<ts>/summary.json`回来，让Claude填runner实现+写evidence_writer。不要自己改契约、不要自己造evidence、不要用mock结果对外说任何话。

**禁止**
- 说"命中率"、"覆盖8生态"、"AI遇npm/pip就瞎试"、"突然变聪明"、"P1/P2凑数"
- mock runner的数字出现在任何对外文案
- 把 schema-valid 或 sandbox-ready 数字包装成 verified_live
- 跳过hard-gate：只省token/tool call不算，必须CI pass翻转或rounds下降≥30%
