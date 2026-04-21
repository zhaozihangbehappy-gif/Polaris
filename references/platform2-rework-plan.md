# Platform 2 返工 — Gate Contract

**审计链**: P1 Claude 实现 → Codex 敌对审查 → P1 Claude 修正 → Codex 确认收敛
**目标**: 装上 Polaris 前后，任何层次的用户都能感受到 agent 明显变聪明了
**核心卖点**: 经验在 LLM 之外运行，不占 context，不增加 tokens，只让决策变好
**可见性契约**: 每个 Phase 的 gate 必须同时验证"技术正确"和"用户能看到变化"

---

## 执行顺序

R0 → R1 → R2 → R5 → R3 → R4a

R4b（pip/npm install 等外部依赖安装）不进 Platform 2。

---

## R0: 经验库契约层

**时间**: 0.5 天
**目的**: 定义经验存储的底层规则，后续 R1-R5 全部基于此层，不允许绕过。

### 三件事

#### 1. Store path 解析

```
优先级（高 → 低）:
  1. --runtime-dir 显式传入 → runtime-dir 作为工作区
  2. POLARIS_HOME 环境变量 → $POLARIS_HOME/experience/
  3. 默认 → ~/.polaris/experience/

全局库路径 = resolve(POLARIS_HOME 或 ~/.polaris) / experience/
运行库路径 = runtime-dir / (failure-records.json, success-patterns.json)
```

#### 2. 双库合并策略

```
写入时:
  - 运行库写入（当次运行状态）
  - 全局库同步写入（持久化）
  - 运行库记录携带 session_id，全局库按 matching_key 去重

读取时:
  - 先查运行库（当次 session 的新鲜记录）
  - 再查全局库（跨 session 积累）
  - 合并结果按既有优先级排序: user_correction > auto > prebuilt
  - 去重: 同一 matching_key + 同一 avoidance_hint → 取最高优先级来源

冲突规则:
  - 运行库记录 > 全局库同 matching_key 记录（当次更新更新鲜）
  - stale/rejected 状态同步: 运行库标记 stale → 写回全局库
```

#### 3. 原子写入 / 并发安全

```
写入方式:
  - write-to-temp + rename（原子替换）
  - Platform 2 按单 writer 假设实现
  - 并发写检测: 写入前读取文件 mtime，写入时校验 mtime 未变；
    若 mtime 已变（说明有并发写）→ fail closed，拒绝写入，stderr 报错，
    不允许静默覆盖
  - 写入失败（磁盘满/权限/并发冲突）→ 降级为 runtime-only，stderr 警告，不崩溃

损坏恢复:
  - 全局库 JSON 解析失败 → 重命名为 .bak，重建空库，stderr 警告
  - 运行库 JSON 解析失败 → 同上
  - 任何降级都不影响当次执行（最差情况 = 无经验的裸跑）
```

### Gate 验证

| # | 断言 | 锚点 |
|---|------|------|
| R0-1 | `POLARIS_HOME=/custom polaris run ...` → 经验写入 `/custom/experience/` | path 解析 |
| R0-2 | 默认无 POLARIS_HOME → 经验写入 `~/.polaris/experience/` | 默认路径 |
| R0-3 | runtime-dir 和全局库都有同一 matching_key 的记录 → query 返回运行库的（更新鲜） | 合并策略 |
| R0-4 | 全局库 JSON 损坏 → stderr 含 warning，执行正常完成，损坏文件重命名为 .bak | 损坏降级 |
| R0-5 | 写入过程中模拟失败（磁盘满）→ 降级为 runtime-only，stderr 警告 | 原子写入 |
| R0-7 | 模拟并发写（写入前 mtime 被改变）→ fail closed，拒绝写入，stderr 报 concurrent write 错误 | 并发安全 |
| R0-6 | 运行库标记 stale → 全局库同 matching_key 记录也被标记 stale | 状态同步 |

### 回归脚本

`regression-platform2-R0.sh`

---

## R1: 全局经验库

**时间**: 1 天
**依赖**: R0
**目的**: 经验跨 session 自动积累，用户不需要做任何事。

### 交付件

- `polaris_cli.py` 修改:
  - run 子命令在执行前从全局库加载经验
  - 执行后将新记录同步到全局库
  - `--runtime-dir` 仅控制当次运行工作区，不影响全局库读写
- `polaris_experience_store.py` 新模块:
  - `resolve_paths()` → 返回 (global_store_path, runtime_store_path)
  - `merge_query()` → 合并两库查询结果
  - `sync_to_global()` → 运行库 → 全局库同步
  - `atomic_write()` → temp + rename 原子写入
  - `safe_load()` → 损坏降级加载

### 可见性要求

经验命中时 stderr 必须体现来源:
```
[polaris] ↻ applied 3 avoidance hints (2 from prior sessions, 1 from current run)
[polaris] ↻ experience source: global library (last seen 2 days ago)
```

### Gate 验证

| # | 断言 |
|---|------|
| R1-1 | 第一次 `polaris run "npm test"` 失败 → 关终端 → 新终端 `polaris run "npm test"` → experience_hints 命中上次失败记录 |
| R1-2 | `~/.polaris/experience/failure-records.json` 存在且包含第一次的记录 |
| R1-3 | `POLARIS_HOME=/tmp/test-home polaris run ...` → 经验写入 `/tmp/test-home/experience/` |
| R1-4 | 全局库损坏 → 降级运行 → stderr 含 `[polaris] warning` → 执行正常完成 |
| R1-5 | 同 matching_key 在全局库已有记录 → 新 session 命中 → experience_hints 来自全局库而非旧 runtime-dir 残留 |
| R1-6 | 传 `--runtime-dir` 时全局库仍被写入（双写） |
| R1-7 | 不传 `--runtime-dir` 时全局库被写入，临时 runtime-dir 在 /tmp 下自动创建 |
| R1-8 | stderr 经验摘要显示来源（global / current session） |

### 回归脚本

`regression-platform2-R1.sh`

---

## R2: 成功经验主动复用

**时间**: 1 天
**依赖**: R1（全局库持久化）
**目的**: 成功路径不只是被记录，而是主动复用——agent 下次遇到同类任务直接走已验证的路径。

### 交付件

- `polaris_success_patterns.py` 扩展:
  - `record()` 写入时自动提取 strategy_hints:
    - 命令成功时的 adapter 选择
    - 生效的环境变量和参数
    - 执行耗时（用于 set_timeout 推荐）
  - strategy_hints.experience_hints_prefer 必须非空（有具体可复用的策略）
- `polaris_orchestrator.py` 扩展:
  - experience hints assembly 阶段: 查询 success_patterns，提取 prefer hints
  - prefer hints 注入到 execution_contract
  - 复用成功 → confidence 递增（上限 0.95）
  - 复用失败 → confidence 递减，连续失败 3 次 → stale
- `polaris_adapter_shell.py`:
  - apply_hints 同时处理 prefer 和 avoid

### 可见性要求

```
[polaris] ↻ reusing verified strategy from 3 successful runs (confidence: 0.85)
[polaris] ↻ skipped 2 known-bad paths, applying proven approach directly
```

### Gate 验证

| # | 断言 |
|---|------|
| R2-1 | 第一次成功 → success-patterns.json 中对应记录包含非空 `strategy_hints.experience_hints_prefer`（硬门：空 = 不算记录成功经验） |
| R2-2 | 第二次运行同类命令 → execution_contract 或 execution_contract_diff 中必须能看见 prefer hints 被实际注入（硬门：记录了但没注入 = 不通过） |
| R2-3 | execution-state.json artifacts.experience_hints.prefer 非空，且内容与 success-patterns 中的 strategy_hints 一致 |
| R2-4 | 连续 5 次成功复用 → confidence 递增但不超过 0.95 |
| R2-5 | 复用后失败 → confidence 递减 |
| R2-6 | 连续 3 次复用失败 → 记录标记 stale，不再被复用 |
| R2-7 | prefer hints 和 avoid hints 同时存在时不冲突（avoid 优先） |
| R2-8 | stderr 摘要显示"复用已验证策略"及 confidence |

### 回归脚本

`regression-platform2-R2.sh`

---

## R5: 经验收益可观测

**时间**: 0.5 天
**依赖**: R1 + R2
**目的**: 用户一眼看到 Polaris 帮了多少忙，数字必须真实。

### 交付件

- `polaris_stats.py` 扩展:
  - 经验命中次数（total hits）
  - 直接命中次数（首次执行即成功，无 repair 循环）
  - 跳过 repair 次数（因经验规避了已知失败路径）
  - 平均 repair 轮次（有经验 vs 无经验时期对比）
  - tokens saved 作为派生估算字段（每次跳过 repair ≈ 节省 1 轮 LLM 调用），不做主判据
- 每次 run 结束的 stderr 摘要增强:
  - 成功 + 有经验命中: `[polaris] ✓ succeeded on first try (experience hit: avoided <error_class>)`
  - 成功 + 无经验: `[polaris] ✓ succeeded (no prior experience for this task)`
  - 失败 + 有经验命中但仍失败: `[polaris] ✗ failed despite experience hints (recording for improvement)`

### 可见性要求（核心 Phase）

这个 Phase 的全部意义就是可见性。用户跑 `polaris stats` 看到的应该是:

```
Polaris Experience Summary
===========================
Global Library:  47 failure records, 23 success strategies
Experience Hits: 156 queries → 89 hits (57.1%)
  Direct hits (first-try success): 34
  Error avoidance hits:            55
Repair Efficiency:
  With experience:    avg 0.8 repair rounds
  Without experience: avg 2.3 repair rounds
  Estimated savings:  ~42 repair cycles avoided

Top Experienced Tasks:
  1. npm test           — 28 hits, 19 direct successes
  2. python3 -m pytest  — 15 hits, 8 direct successes
  3. go test ./...      — 11 hits, 7 direct successes
```

### Gate 验证

| # | 断言 |
|---|------|
| R5-1 | 经验命中 + 首次成功 → hit counter 递增 + direct_hit counter 递增 |
| R5-2 | 经验命中 + 仍失败 → hit counter 递增 + direct_hit 不递增 |
| R5-3 | 无经验命中 + 成功 → hit counter 不递增 |
| R5-4 | stats 输出的命中次数 = event-log 中 experience_hit 事件数 |
| R5-5 | stats --json 输出合法 JSON，包含 hits/direct_hits/repair_rounds_avg 字段 |
| R5-6 | stderr 摘要在每次 run 后准确反映经验命中状态 |
| R5-7 | tokens_saved 字段存在但标注为 estimate |

### 回归脚本

`regression-platform2-R5.sh`

---

## R3: 经验包增厚

**时间**: 1 天
**依赖**: R0（store 契约）
**目的**: 预置经验从"教科书建议"变成"真实高命中率 hints"。

### 交付件

- 每条 prebuilt 记录结构强化:
  ```json
  {
    "ecosystem": "node",
    "error_class": "missing_dependency",
    "stderr_pattern": "Cannot find module '([^']+)'",
    "avoidance_hints": [{"kind": "set_env", "vars": {"NODE_PATH": "./node_modules"}}],
    "description": "Node.js module resolution failure in non-standard directory layout",
    "source": "prebuilt",
    "pack_version": "2.0"
  }
  ```
- 每条必须有: ecosystem + error_class + stderr_pattern + avoidance_hints
- stderr_pattern 用正则匹配，classify 时精确命中
- 先做每生态 5 个高频真实模式（Phase 1）
- 用 stderr fixture corpus 跑 precision/recall
  - precision ≥ 80%（命中的 hints 中有多少是有效的）
  - recall ≥ 60%（真实错误中有多少被命中）
- 达标后扩到 15+（Phase 2，可在后续 Platform 迭代中做）

### 每生态 5 个高频模式（Phase 1 最小集）

**Node.js**:
1. `Cannot find module` — MODULE_NOT_FOUND
2. `ENOENT: no such file or directory, open 'package.json'` — 项目根目录错误
3. `EACCES: permission denied` — npm cache 权限
4. `JavaScript heap out of memory` — V8 内存限制
5. `ERR_MODULE_NOT_FOUND` — ESM import 失败

**Python**:
1. `ModuleNotFoundError: No module named` — 缺依赖
2. `SyntaxError: invalid syntax` — Python 版本不匹配
3. `PermissionError: [Errno 13]` — 写权限
4. `FileNotFoundError: [Errno 2]` — 路径错误
5. `UnicodeDecodeError` — 编码问题

**Go**:
1. `cannot find module providing package` — go mod 未同步
2. `build constraints exclude all Go files` — CGO/平台问题
3. `missing go.sum entry` — go.sum 不完整
4. `cannot find package` — GOPATH 问题
5. `permission denied` — 构建缓存权限

### Gate 验证

| # | 断言 |
|---|------|
| R3-1 | 每条 prebuilt 记录包含 ecosystem + error_class + stderr_pattern + avoidance_hints |
| R3-2 | stderr_pattern 为合法正则表达式 |
| R3-3 | fixture corpus（每生态 10 个真实 stderr 片段）→ classify → query → 命中率 ≥ 60% |
| R3-4 | 命中的 hints 与 stderr 语义匹配（不返回无关 hints）→ precision ≥ 80% |
| R3-5 | 每个生态至少 5 条记录 |
| R3-6 | pack_version 升级到 "2.0"，旧版本 prebuilt 记录在 reset-prebuilt 后可清除 |

### 回归脚本

`regression-platform2-R3.sh`

---

## R4a: 本地安全自动修复

**时间**: 1 天
**依赖**: R1 + R2
**目的**: 对安全的本地修复类型，Polaris 自动执行而非只生成报告。

### 范围限定（硬约束）

**允许自动执行的 hint kinds**:
- `rewrite_cwd` — 切换工作目录
- `set_env` — 设置环境变量
- `set_timeout` — 调整超时

**不允许自动执行的**:
- `pip install` / `npm install` / `go get` — 外部依赖安装
- 任何修改文件系统内容的操作
- 任何需要网络请求的操作

**这条线不可逾越**: Polaris 是经验系统，不是会乱改环境的 agent。

### 交付件

- repair 路径扩展:
  - classify → 匹配到安全修复类型 → 自动应用 hint → 重试原命令
  - 重试成功 → 记录为成功经验（R2 闭环）
  - 重试失败 → 记录失败，不再自动重试（最多 1 次自动修复）
- 重试预算: 自动修复最多 1 次，防止循环
- 不安全类型（permission_denial, approval_denial）保持 report-only

### 可见性要求

```
[polaris] ⚡ auto-fix: set NODE_OPTIONS="--max-old-space-size=4096" (from experience)
[polaris] ⚡ retrying with fix applied...
[polaris] ✓ succeeded after auto-fix (recording as verified strategy)
```

或:
```
[polaris] ⚡ auto-fix: rewrite_cwd to ./packages/core (from experience)
[polaris] ⚡ retrying with fix applied...
[polaris] ✗ still failed after auto-fix (recording for review)
```

### Gate 验证

| # | 断言 |
|---|------|
| R4a-1 | 命令失败 + 经验匹配到 set_env hint → 自动应用 → 重试 |
| R4a-2 | 自动修复成功 → success-patterns 中记录新策略 |
| R4a-3 | 自动修复失败 → 不再自动重试（最多 1 次） |
| R4a-4 | 自动修复只限 rewrite_cwd / set_env / set_timeout，不执行任何安装命令 |
| R4a-5 | permission_denial 类型 → 不自动修复，只报告 |
| R4a-6 | stderr 显示自动修复的具体动作和结果 |
| R4a-7 | 自动修复后成功 → R5 stats 中 "auto-fix success" 计数递增 |

### 回归脚本

`regression-platform2-R4a.sh`

---

## 可见性贯穿规范

每个 Phase 的 stderr 输出必须让用户感受到 Polaris 在工作。完整的单次 run stderr 输出示例:

### 首次运行（无经验）
```
[polaris] first run for this task — no prior experience
[polaris] ✗ failed: missing_dependency (Cannot find module 'lodash')
[polaris] ✗ learned: avoidance hint [set_env] stored for next run
```

### 第二次运行（经验命中）
```
[polaris] ↻ found 2 relevant experiences (1 from 3 days ago, 1 prebuilt)
[polaris] ↻ applying: set_env NODE_PATH=./node_modules (confidence: 0.85)
[polaris] ✓ succeeded on first try — experience hit saved 1 repair cycle
```

### 经验丰富后
```
[polaris] ↻ found 5 relevant experiences (3 verified strategies, 2 avoidance hints)
[polaris] ↻ reusing proven strategy (7 prior successes, confidence: 0.92)
[polaris] ✓ succeeded — Polaris has helped this task succeed 8 times
```

### stats 输出
```
Polaris Experience Summary
===========================
Global Library: 47 failure records, 23 success strategies
Session:        3 new records added this run

Experience Impact:
  Total queries:      156
  Hits:               89 (57.1%)
  Direct successes:   34 (first-try, no repair needed)
  Errors avoided:     55
  Auto-fixes applied: 12 (10 succeeded)

Efficiency:
  Avg repair rounds (with experience):    0.8
  Avg repair rounds (without experience): 2.3
  Estimated repair cycles saved:          ~42
```

---

## 禁止项

- 全局库路径不可硬编码，必须通过 R0 的 resolve 逻辑
- 经验同步不可丢数据（原子写入）
- stats 数字必须与 event-log 精确一致，不允许估算（tokens_saved 除外，已标注 estimate）
- 自动修复不可执行安装命令（pip/npm/go get）
- stderr 输出不可污染 stdout 的 JSON 结构
- 可见性文案必须反映真实状态（不可声称"applied"但实际没应用）
- prefer hints confidence 上限 0.95，不可为 1.0（保留不确定性）

---

## 时间线

| Phase | 内容 | 天数 | 累计 | 硬依赖 |
|-------|------|------|------|--------|
| R0 | 经验库契约层 | 0.5 | 0.5 | 无 |
| R1 | 全局经验库 | 1 | 1.5 | R0 |
| R2 | 成功经验主动复用 | 1 | 2.5 | R1 |
| R5 | 经验收益可观测 | 0.5 | 3 | R1+R2 |
| R3 | 经验包增厚 | 1 | 4 | R0 |
| R4a | 本地安全自动修复 | 1 | 5 | R1+R2 |

**总计: 5 天，每个 Phase 独立可交付，每个 Gate 可被 Codex 独立审计。**

---

## 不进 Platform 2

- R4b: 外部依赖安装（pip/npm install）— 需要 opt-in 机制设计，留 Platform 3
- 经验包扩到 15+/生态 — R3 Phase 1 做 5 个高频，达标后再扩
- 跨机器经验同步 — Platform 3+
- 经验社区共享 — Platform 3+
- Adapter learned ranking — Platform 3，依赖 D1 数据积累
