# Polaris v3.0 发布计划

---

## 第一部分：产品定位（开工前锁死，不可改）

### Polaris 是什么

Polaris 是一个 agent execution skill，给 AI agent 装上环境错误的**确定性修复能力**。

它不做推理。它做查表。见过的错误走反射，没见过的退回给 LLM，零损耗。

装了 Polaris 的 agent 和没装的 agent 跑同一批任务，差距不在智力，在反应速度：
一个每遇到环境错误就停 5 秒、烧 3000 token、可能还要问用户；
另一个 80ms 静默修好，继续执行。

### Polaris 不是什么

- 不是本地大模型——不做推理，做查表
- 不是万能修复器——只修已知环境错误，不碰源码、不碰业务逻辑
- 不是黑盒——每个修复可追溯到具体 pattern，有 reproduction case 证明

### 产品价值的三层结构

**第一层（钩子）：首次 wow moment**

新用户第一次用，Polaris 凭 prebuilt 经验库命中修复。用户什么都没配，
什么经验都没积累，第一次就修好了。这是留人的钩子。

> 如果第一次没命中，后面的一切都到不了。首次命中率是发布的硬门槛。

**第二层（粘性）：有/无落差**

用了一周后关掉 Polaris，agent 突然变笨——同一个顶配模型，怎么又开始
动不动停下来问我了？这个落差是粘性的来源。

**第三层（飞轮）：贡献 + 正反馈**

用户本地积累的经验，经过验证后贡献回中央库。其他用户命中你的 pattern 时，
你能看到 "your contribution, verified in N deployments"。库越厚，命中率
越高，吸引更多人用和贡献。这是长期护城河。

### 发布标准（三个条件，缺一不发）

1. **首次命中率 ≥ 60%**：每个覆盖生态取 10 条野外真实 stderr，仅凭 prebuilt pack 命中修复
2. **成功路径 overhead < 5ms**：用户无感
3. **贡献全链路走通**：contribute → CI 验证 → 合并 → 其他用户命中

### "一鸣惊人"的具体含义

不是营销噱头，是产品体验的硬指标：

- 用户装完跑第一批任务，**超过一半的环境错误被静默修复**
- 用户的第一反应不是"这个工具不错"，而是"我的 agent 怎么突然不停了"
- **卸载后的落差是最好的传播**——用户自己会去推荐

### 诚实文案合约

- 文案中的 pattern 数量 = 实际通过 reproduction 验证的数量，不凑整
- 文案中的生态数量 = 实际覆盖且 recall ≥ 60% 的生态数量
- 不用 "10,000+" 除非实际 ≥ 10,000
- 不用 "verified" 除非符合 PLATFORM3_PLAN 中钉死的定义

---

## 第二部分：现状评估

### 架构状态（全绿）

| Phase | 门控 | 状态 |
|-------|------|------|
| 3A 分片引擎 | 5/5 | ✅ |
| 3B Hint 扩展 | 7/7 | ✅ |
| 3C 经验库 | 10/10 | ✅ (但 fixture 是自产自销) |
| 3D 贡献管线 | 14/14 | ✅ |
| 3E 显示层 | 6/6 | ✅ |

### 经验库状态（致命短板）

- 8 个生态，42 条 records
- 每个 error_class 基本只有 1 条 pattern
- 没有野外 stderr fixture 验证首次命中率
- 距离"一鸣惊人"差两个数量级

### 核心判断

**架构已就绪，引擎已就绪，管线已就绪。当前最可能的瓶颈是经验库的厚度。**

但"最可能"不等于"一定"。如果扩库后命中率增长停滞，瓶颈可能在 stderr
归一化、error_class 路由、匹配排序或 hint 表达力——此时继续加 pattern
是在错误方向上使劲。计划必须包含止损机制（见 Step 2 falsification gate）。

3C 的门控在技术上是通过的，但门控的 fixture 是和 pattern 一起写的——
这不是真正的首次命中率验证。我们需要：

1. 用**独立于 pattern 编写过程**的野外真实 stderr 来测试命中率
2. 每个生态的 pattern 从 ~5 条扩到足以覆盖该生态 60%+ 的常见环境错误
3. 每条新 pattern 都有 reproduction case 且实际执行验证通过

---

## 第三部分：工程计划

### 唯一任务：经验库扩容到发布标准

架构不动。引擎不动。管线不动。**只做一件事：把库补到足够厚。**

### Step 1：建立野外 stderr fixture 语料库（dev set + blind holdout）

**目的**：独立于 pattern 编写过程的测试集，用来真实度量首次命中率。

**方法**：
- 从公开来源（GitHub Issues、Stack Overflow、CI 日志示例）收集每个生态
  的真实 stderr snippet
- 每个生态 ≥ 30 条（覆盖高频和中频 error class）
- 按 error_class 标注（人工）
- 存放在 `experience-packs/fixtures/` 下，和 pattern 文件物理隔离
- 收集的 stderr 移除路径、用户名、token 等 PII 痕迹

**dev / holdout 拆分**：
- 先按来源去重：同一 GitHub issue / SO thread / CI 日志来源的多条 stderr
  视为同一组，**同组 snippet 只能落在同一侧**，防止近重复泄漏
- 去重后按 error_class 分层抽样，再按 2:1 拆分
- `fixtures/{ecosystem}/dev/` — 开发时可见，用于调试 regex、检查覆盖盲区
- `fixtures/{ecosystem}/holdout/` — **扩库前冻结，开发全程不可见**
- 最终发布判定的首次命中率只看 holdout
- dev set 的命中率仅作过程参考，不作为发布依据

> 注：holdout 的价值不是防止"过拟合"（regex 匹配不存在梯度优化），
> 而是暴露 dev set 没覆盖到的错误变体和格式差异。

**产出**：`experience-packs/fixtures/{ecosystem}/dev/` 和 `holdout/` 目录，
每个生态 dev ≥ 20 条 + holdout = 10 条真实 stderr，附带 error_class 标注
和来源标记（用于去重分组）。

**验收**：fixture 来源可追溯，不能是从 pattern 的 stderr_pattern 反向生成的。

### Step 2：按生态分批扩容 pattern

**优先级排序**（按用户基数 × 环境错误频率）：

| 优先级 | 生态 | 目标 pattern 数 | 理由 |
|--------|------|-----------------|------|
| P0 | python | ≥ 25 | agent 最常用语言 |
| P0 | node | ≥ 25 | 前端/全栈/工具链 |
| P0 | docker | ≥ 20 | CI/CD 场景 |
| P1 | go | ≥ 15 | 后端/CLI 工具 |
| P1 | rust | ≥ 15 | 构建错误频繁 |
| P1 | java | ≥ 15 | 企业级用户 |
| P2 | terraform | ≥ 10 | DevOps 场景 |
| P2 | ruby | ≥ 10 | Rails 生态 |

**总目标**：≥ 135 条 pattern（保守）。实际以 holdout fixture 命中率 ≥ 60% 为准。

**Falsification gate（止损机制）**：
每生态新增 10 条 pattern 后，度量 dev set 新增命中数（绝对计数）。
如果 **新增命中 < 2 条**（即 10 条新 pattern 在 ≥ 20 条 dev fixture
中只多命中了 0 或 1 条），**暂停扩库**，排查以下可能的引擎/表示层瓶颈：
- stderr 归一化是否丢失了关键信息
- error_class 路由是否把 stderr 分到了错误的 shard
- regex 匹配优先级是否导致正确 pattern 被跳过
- 8 种 hint kind 是否无法表达某类修复（需要新 kind）

确认瓶颈不在引擎后才继续扩库。如果瓶颈确实在引擎，"不动架构"
这条约束在此处解除——修引擎比堆无效 pattern 重要。

**每条 pattern 必须包含**：
```json
{
  "ecosystem": "...",
  "error_class": "...",
  "stderr_pattern": "...(regex)...",
  "avoidance_hints": [{"kind": "...", ...}],
  "description": "...",
  "source": "prebuilt",
  "reproduction": {
    "command": "...",
    "trigger_env": {},
    "expected_stderr_match": "...",
    "fix_env": {},
    "expected_fix_outcome": "different_error_or_success"
  }
}
```

**每条 pattern 的质量标准**：
1. stderr_pattern 在 dev fixture 上 precision ≥ 80%（pack 级 query 结果口径，
   即 `query()` 对该 stderr 返回的 error_class 是否正确，不是单条 regex 级）
2. avoidance_hints 的 kind 在 8 种允许范围内
3. reproduction case **必须实际执行通过**：trigger 触发错误，fix 改变结果
4. **发布包不允许 manual_only pattern**——reproduction 不可执行的 pattern
   只作为开发中间态，不入库、不计入文案数字。要么补齐 reproduction，要么不发。

### Step 3：真实首次命中率验证

**首次命中率的精确定义**：对一条 stderr，`query()` 返回结果 **且** 返回的
hint kind 未被安全检查 reject。不要求运行时验证"fix 是否实际修好了"——
那是 reproduction case 在构建时已经证明的事。

**方法**：新增 `scripts/verify-firsthit.sh`
- 分两轮：先跑 dev set（开发过程参考），最终跑 **holdout set**（发布判定）
- 对每条 fixture stderr，走 `query()` 逻辑查命中
- 输出：每生态的 recall / precision（pack 级 query 结果口径）
- kill gate：**P0 生态（python/node/docker）holdout 10 条中命中 < 6 条 → 不发布**
- P1/P2 生态：holdout 10 条中命中 ≥ 6 条计入覆盖生态数；< 6 条不计入，
  但不阻塞发布。文案中的生态数量只写实际达标的数量。
- 离散判定规则：holdout = 10 条，60% = 6/10，无歧义。

### Step 4：reproduction case 全量执行验证

**方法**：新增 `scripts/verify-reproductions.sh`
- 遍历所有 pattern 的 reproduction 字段
- 执行 trigger → 验证 stderr 匹配
- 应用 fix → 验证结果改变
- kill gate：任何 reproduction 失败 → 该 pattern 不入库

**执行环境**：优先本地直接执行。需要特定运行时的（java、rust、go 等）
在有该运行时的环境中执行。

**发布包零 manual_only 合约**：reproduction 不可执行的 pattern 不得入库。
如果某个生态的运行时在当前环境不可用，先安装运行时再验证，或构造不依赖
该运行时的等效 reproduction（如用 shell 模拟错误输出）。无论如何，进入
发布包的每一条 pattern 都必须有实际执行通过的 reproduction。

### Step 5：更新门控和 index

- 更新 `index.json` 反映实际 pattern 数量
- 更新 3C regression 用新 fixture 替代自产自销的 fixture
- **在最终 pack 规模下重跑 3A benchmark**（成功路径 overhead < 5ms，
  查询 < 2ms，内存 < 1MB），不沿用 42 条时的结果
- 跑全量 96 门控

### Step 6：发布判定

三个条件全过：
1. ✅ 首次命中率 ≥ 60%（**holdout fixture 验证，P0 生态 kill gate**）
2. ✅ 成功路径 < 5ms（**最终 pack 规模下重新验证**）
3. ✅ 贡献全链路走通（3D 已验证）

全过 → 锁定文案数字（pattern 数 = 实际入库数，生态数 = holdout recall ≥ 60% 的生态数）→ 发布到 ClawHub。

---

## 第四部分：工作分工

| 角色 | 职责 |
|------|------|
| Claude（我） | Step 1-5 全部工程执行：fixture 收集、pattern 编写、reproduction case、验证脚本、门控更新 |
| Codex | 每个 Step 完成后审阅：pattern 质量、reproduction 有效性、门控覆盖、安全合约 |
| 用户（你） | 发布判定测试：拿你自己真实的开发环境跑 Polaris，验证体感是否达到"一鸣惊人" |

### 审阅节奏

**一次性总审**：Step 1-5 全部完成后，一次性交由 Codex 按 release review 口径审阅：
- fixture 质量与隔离（来源去重、dev/holdout 分组、无泄漏）
- pattern / reproduction 质量（每条实际执行通过、零 manual_only）
- first-hit 数据（holdout recall 数字、P0 kill gate 是否通过）
- falsification gate 触发记录（是否触发、触发后排查结论）
- 3A 终态性能（最终 pack 规模下 benchmark 结果）
- 全量门控（96 门全绿）
- 文案数字是否与事实一致

Codex 最终给出正式结论：**可发布** 或 **有阻塞项，不可发布**。
中途不做分段审阅，全链条跑完再交。

### 预期交付物清单

```
experience-packs/
  fixtures/                      # 野外 stderr fixture（Step 1）
    python/  node/  docker/  go/  rust/  java/  terraform/  ruby/
  python/                        # 扩容后的 pattern（Step 2）
    missing_dependency.json      # 从 1 条 → 5-8 条 pattern
    syntax_error.json
    permission_denial.json
    file_not_found.json
    encoding_error.json
    resource_exhaustion.json     # 新增
    version_conflict.json        # 新增
    network_error.json           # 新增
    ...
  node/ docker/ go/ rust/ java/ terraform/ ruby/  # 同上
  index.json                     # 更新

scripts/
  verify-firsthit.sh             # 首次命中率验证（Step 3）
  verify-reproductions.sh        # reproduction 全量验证（Step 4）
```

---

## 第五部分：不做的事

1. **默认不动架构** — 3A/3B/3D/3E 全绿，默认不碰；但如果 falsification gate
   触发且瓶颈确认在引擎/表示层，此约束解除
2. **不追求 10K** — 目标是首次命中率 ≥ 60%，135 条能达到就是 135 条，不凑数字
3. **不为了数量牺牲质量** — 每条 pattern 都要 reproduction 实际执行通过，
   发布包零 manual_only，宁可少 10 条也不放一条假的
4. **不做营销** — 发布文案等数字锁定后再写
5. **不多加生态** — 8 个生态足够，先打深再打宽

---

## 签核

本计划经 Codex 审阅后由我（Claude）拍板，用户确认后开工。

开工后本计划不可变更产品定位（第一部分）。
工程计划（第三部分）可根据 Codex 审阅意见调整细节，但不可降低发布标准。
