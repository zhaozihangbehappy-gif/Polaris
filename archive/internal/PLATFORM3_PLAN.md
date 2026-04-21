# Polaris Platform 3

---

## 这一版要解决的问题

现在全球最强的 agent——Claude、Codex、OpenClaw——在执行本地任务时有一个
共同的软肋：**遇到环境错误就停。**

`ModuleNotFoundError`，agent 停了，问用户要不要装包。
`EACCES: permission denied`，agent 停了，建议用户检查权限。
`heap out of memory`，agent 停了，说"资源不足请调整"。

这些不是 agent 的智力问题。它们读得懂 stderr，它们知道怎么修。但它们没有
**预编译的环境修复经验**，每次都要临时推理、问用户确认、等几秒钟消耗几千
token，然后可能还修不对。

Polaris 要做的事：**把这些已知环境错误的修复方案，编译成确定性查表，
让 agent 在同一次执行内、在用户察觉之前、零 token 消耗地修好。**

装了 Polaris 的 agent 和没装的 agent，执行同一批任务的体验落差：

| | 没有 Polaris | 有 Polaris |
|---|---|---|
| `ModuleNotFoundError` | agent 停下，问用户，等 5s+ | 0.08s 自动修复，继续执行 |
| `EACCES: permission denied` | agent 停下，建议检查权限 | 0.06s 切换 cwd，继续执行 |
| `heap out of memory` | agent 停下，建议调整配置 | 0.1s 设 NODE_OPTIONS，继续执行 |
| 连续 10 个任务 | 3-5 次中断，用户反复介入 | 0 次中断，全程流畅 |

**这个落差就是 Polaris 的产品价值。** 不是"命令不失败"，是"你的 agent
装了这个 skill 之后，处理环境错误的能力从临时推理变成了即时反射。"

用户的上瘾体验不来自 Polaris 本身，来自**卸载 Polaris 之后 agent 突然
变笨了**——明明同一个顶配模型，怎么又开始动不动停下来问我了？

---

## Platform 3 的终点：三个判定条件，全部满足才发布

Platform 3 完成时，以下三个条件必须**同时满足**。任何一个不满足，
不发布到 ClawHub，不对外宣传任何承诺。没有 preview、没有 beta、没有折中。

### 条件 1：首次命中率

从发布时实际覆盖的生态系统中，每个生态取 10 条真实 stderr（全新用户，
无本地历史），Polaris 仅凭 prebuilt pack 命中并自动修复的比例：

**≥ 60%**

注意：发布文案中的数字必须和实际门控结果一致。如果最终覆盖 12 个生态、
7,200 条 pattern，文案就写 "7,200+ patterns across 12 ecosystems"。
不写还没达到的数字。

### 条件 2：用户无感

成功命令（不触发 failure store）的端到端 overhead：

**< 5ms**

### 条件 3：贡献全链路

`polaris experience contribute` → 中央 CI 验证 → 合并到 pack →
`clawhub update` → 其他用户命中该 pattern。

**全链路走通，有端到端测试证明。**

---

## "verified" 的定义——在用到这个词之前先把它钉死

这是 Blocking 3 要求回答的问题。Polaris 对外说的每一个"verified"都必须
有明确的证据口径，否则就是虚假宣传。

### 两种来源，两种验证标准

**Prebuilt pattern（3C 产出，随 skill 发布）：**

"verified" = 通过以下全部检查：
1. stderr_pattern 在 fixture corpus 上 precision ≥ 80%（regex 匹配正确的 error_class）
2. avoidance_hint 的 kind + 参数经过人工安全审核
3. hint 在构造的 reproduction case 上实际执行成功（不是只写了 regex 能匹配，
   而是这个 hint 应用到一个真实会报这个错的命令上，命令变成功了）

第 3 条是关键。每条 prebuilt pattern 必须附带一个 `reproduction` 字段：

```json
{
  "stderr_pattern": "ModuleNotFoundError: No module named '([^']+)'",
  "avoidance_hints": [{"kind": "set_env", "vars": {"PYTHONPATH": ".:src"}}],
  "reproduction": {
    "command": "python3 -c \"import nonexistent_local_module\"",
    "env_before": {},
    "expected_error": "ModuleNotFoundError",
    "env_after": {"PYTHONPATH": ".:src"},
    "expected_outcome": "success_or_different_error"
  }
}
```

门控 3C-G9 会实际执行每条 reproduction case，验证 hint 确实改变了执行结果。
**这是 prebuilt pattern 敢称 "verified" 的证据。**

不过，prebuilt pattern 没有来自真实用户的 applied_count 数据。所以：
- prebuilt pattern 命中时显示：`(from community knowledge base)`
- **不显示虚构的数字**

**Contributed pattern（3D 产出，用户贡献回流）：**

"verified" = 贡献者本地 `applied_count ≥ 1, applied_fail_count == 0` +
中央 CI 的 regex/precision/reproduction 检查全部通过。

- contributed pattern 命中时显示：`(verified in N deployments)`
- N = 该 pattern 在中央库中聚合的 applied_count（来自所有贡献者的真实数据）

### 显示规则

```
# prebuilt 命中——诚实标注来源，不伪造计数
[polaris] ⚡ auto-fix: set LC_ALL="C.UTF-8" (from community knowledge base)
[polaris] ✓ auto-fixed in 0.08s

# contributed 命中——有真实验证数据时才显示计数
[polaris] ⚡ auto-fix: set DOCKER_HOST="..." (verified in 2,341 deployments)
[polaris] ✓ auto-fixed in 0.06s

# 用户自己的贡献被命中
[polaris] ⚡ auto-fix: set DOCKER_HOST="..." (your contribution, verified in 2,341 deployments)
[polaris] ✓ auto-fixed in 0.06s
```

随着贡献回流积累，prebuilt pattern 也会被用户的 applied_count 数据"加固"，
从 `community knowledge base` 自然升级为 `verified in N deployments`。
这个升级是数据驱动的，不是时间驱动的。

---

## Polaris 最终是什么样子

### Agent 视角：有 Polaris vs 没有 Polaris

**没有 Polaris 的 Claude/Codex/OpenClaw：**

```
> Agent: 执行 python3 train.py
  ModuleNotFoundError: No module named 'numpy'
> Agent: 看起来缺少 numpy。我来安装它。
> Agent: pip install numpy
> Agent: 安装完成，重新执行...
> Agent: python3 train.py
  ✓ 执行成功

耗时: 8-15 秒 (推理 + 安装 + 重试)
Token 消耗: 2000-5000 (读 stderr + 推理 + 执行安装命令)
用户介入: 可能需要确认安装
```

**装了 Polaris 的同一个 Agent：**

```
> Agent: polaris run "python3 train.py"
  ModuleNotFoundError: No module named 'numpy'
  [polaris] ⚡ auto-fix: set PYTHONPATH=".:src:lib" (from community knowledge base)
  [polaris] ✓ auto-fixed in 0.08s

耗时: 0.08 秒
Token 消耗: 0
用户介入: 无
```

**落差**: 同一个顶配模型，同一个任务，一个需要 8 秒 + 5000 token + 可能打断用户，
另一个 80 毫秒静默修好。

### 人类用户视角：三个场景

**场景 1：首次安装，首次命中**

```
$ polaris run "npm run build"

  FATAL ERROR: Reached heap limit Allocation failed

[polaris] ⚡ auto-fix: set NODE_OPTIONS="--max-old-space-size=4096" (from community knowledge base)
[polaris] ✓ auto-fixed in 0.12s
```

用户什么都没配。什么都没经历过。**第一次就修好了。**

**场景 2：本地经验积累**

```
$ polaris run "terraform plan"

  Error: No valid credential sources found for AWS Provider

[polaris] ⚡ auto-fix: set AWS_PROFILE="default" (from previous failure)
[polaris] ✓ auto-fixed in 0.05s
```

第一次遇到这个错误时 Polaris 没命中（prebuilt 没覆盖到），走了正常的 blocked
流程。但这次失败被记录了。第二次遇到时——自动修复。

**场景 3：贡献经验**

```
$ polaris experience contribute
[polaris] 筛选通过: 3 条 (已验证，可贡献)
  ✓ docker/permission_denial: /var/run/docker.sock (验证 8 次, 0 失败)
  ✓ terraform/auth_error: AWS credentials (验证 3 次, 0 失败)
  ✓ rust/build_error: linker cc not found (验证 5 次, 0 失败)
[polaris] 已导出。提交后将惠及所有 Polaris 用户。
```

三个月后：

```
$ polaris experience status
[polaris] 你的贡献:
  docker/permission_denial → verified in 2,341 deployments
  terraform/auth_error     → verified in 1,187 deployments
  rust/build_error         → verified in 876 deployments
```

### 竞品对比

| | self-improving-agent (243K 下载) | Polaris |
|---|---|---|
| 智能来源 | LLM 每次读 markdown 笔记推理 | 确定性查表，零 token |
| 首次命中 | 不可能（需先失败让 LLM 记笔记） | 第一次就修（集体经验在库中） |
| 修复速度 | 3-5s (LLM 推理) | < 200ms (regex 命中 → 直接应用) |
| 给 agent 的价值 | agent 多了个笔记本 | agent 多了环境修复反射弧 |
| 离线 | 不行（没 LLM = 空壳） | 完整运行 |
| 网络效应 | 无（经验锁在本地 markdown） | 有（贡献回流中央库） |

一句话差异：**它给 agent 一个笔记本，我们给 agent 一套肌肉记忆。**

---

## ClawHub 发布描述

以下文案只有在三个判定条件全部满足后才能使用。
文案中的所有数字必须和实际门控结果一致——写多少就是多少，不凑整。

```yaml
name: polaris
version: "3.0"
platform: 3
```

### Tagline

**Give your agent an immune system against environment errors.**

### Description

Polaris is an execution skill that turns known environment failures into
automatic recoveries.

When your agent runs a command and hits `ModuleNotFoundError`,
`EACCES: permission denied`, `heap out of memory`, or any of {ACTUAL_COUNT}
cataloged error patterns, Polaris identifies the error, applies a proven fix,
and retries — within the same execution, in under 200 milliseconds, consuming
zero LLM tokens.

**The difference it makes:**

Without Polaris, your agent stops on a missing module error, reasons about it
for 5 seconds, burns 3,000 tokens, and asks you to confirm an install.
With Polaris, the same error is resolved in 80ms and the agent continues
without breaking stride.

After a week of using Polaris, turn it off. Watch your agent stumble on errors
it used to handle silently. That's the gap.

**What's in the box:**
- {ACTUAL_COUNT} error patterns across {ACTUAL_ECO_COUNT} ecosystems
  (Python, Node, Go, Rust, Java, Docker, Terraform, and more)
- 8 fix types: env vars, working directory, timeouts, locale, flags,
  directories, retry, package install (opt-in only)
- Sub-200ms deterministic auto-fix — no LLM calls, works offline
- Full audit trail — every fix is traceable and explainable

**Where patterns come from:**

Every prebuilt pattern is tested against a reproduction case that proves
the fix changes the outcome. Community-contributed patterns carry real
deployment verification counts. The library grows with every user who
contributes back.

**What it won't do:**
- Won't install packages unless you explicitly allow it
- Won't modify your source code
- Won't call any external API
- Won't guess — every fix traces back to a cataloged pattern

`polaris experience contribute` — share your verified fixes with the community.
Your experience, anonymized and tested, helps every Polaris user after you.

**Key numbers:**
- {ACTUAL_COUNT} cataloged error patterns
- {ACTUAL_ECO_COUNT} ecosystems
- < 200ms auto-fix
- 0 tokens per fix
- {ACTUAL_GATE_COUNT} automated quality gates
- 100% offline capable

*{ACTUAL_COUNT}, {ACTUAL_ECO_COUNT}, {ACTUAL_GATE_COUNT} are filled from
the actual gate results at release time. No rounding up, no aspirational
numbers.*

---

## 工程计划

以上是 Platform 3 必须交付的产品状态和对外承诺。以下是达到这个状态的
工程路径。

每个 Phase 的门控合约是对上述承诺的逐项兑现。
如果门控全绿但产品承诺没兑现——门控设计失败。
如果产品承诺兑现但有门控没过——工程纪律失败。
两者都不可接受。

### 前置条件

Platform 2 全部门控通过 (R0 18/18, R2 20/20, R3 7/7, R4a 10/10, R5 8/8)，
commit `16c7e3b`。

### 核心约束

- 成功路径 overhead < 5ms → 兑现"用户无感"
- 失败路径查询 < 2ms → 兑现"亚秒修复"
- 内存 < 1MB / 单次查询 → 兑现"只加载命中分片"
- 磁盘 < 10MB → 兑现 ClawHub 可分发
- 不动状态机 / 门控合约 / adapter 接口 → 兑现"不回归"

---

### Phase 3A — 查询引擎重构：两级分片

**兑现**: "< 200ms auto-fix"、"用户无感"

**交付物**: `polaris_failure_records.py` 支持分片加载，成功路径零 failure-store 开销。

#### 分片存储格式

```
experience-packs/
  index.json                      # 路由表 (~2KB)
  python/
    missing_dependency.json       # 该 error_class 的全部 records
    syntax_error.json
    ...
  node/ go/ rust/ ...             # 每生态一个目录
```

`index.json`:
```json
{
  "schema_version": 3,
  "ecosystems": {
    "python": {
      "error_classes": ["missing_dependency", "syntax_error", ...],
      "total_records": 500,
      "pack_version": "3.0"
    }
  }
}
```

向后兼容: 检测旧格式自动降级为线性扫描，不破坏 Platform 2 R3。

#### 分片查询路径

```
query(store, matching_key, ecosystem, error_class, stderr_text)
  │
  ├─ Tier 1: exact (matching_key) → 只扫描本地 records
  ├─ Tier 2: command_key fallback → 只扫描本地 records
  └─ Tier 3: ecosystem →
       ├─ 3a: 已知 error_class → 加载 ecosystem/error_class.json (30-50 条)
       ├─ 3b: 未知 error_class → 加载该 ecosystem 全部分片 (≤500 条)
       └─ 3c: 未知 ecosystem → 跳过
```

#### 成功路径零开销

当前: 成功也加载 failure store。
目标: 成功路径不加载 failure store，不加载 index.json，不做任何 failure
相关 I/O。experience hints 中的 avoid 部分只在失败路径构建；prefer 部分
来自 success_patterns.py（已有），和 failure store 无关。

改动点 — `polaris_orchestrator.py`：
- 只在 `exec_rc != 0 or not execution_ok` 之后才加载 failure store
- 成功路径的 experience_hints 只包含 prefer（来自 success patterns），
  不包含 avoid（来自 failure store）

#### 3A 门控

| ID | 断言 | 兑现 |
|----|------|------|
| 3A-G1 | 成功命令不加载 failure store (代码路径验证) | 用户无感 |
| 3A-G2 | 500 records/shard 查询 < 2ms (benchmark) | 亚秒修复 |
| 3A-G3 | Platform 2 R3 全部通过 | 不回归 |
| 3A-G4 | 单次查询内存 < 1MB (tracemalloc) | 分片有效 |
| 3A-G5 | index.json 损坏时降级为全量加载 | 不崩溃 |

**改动范围**:
- `polaris_failure_records.py`: load_store / query 重构 (~100 行)
- `polaris_orchestrator.py`: failure store 加载移入失败路径 (~10 行)
- 新增: `scripts/regression-platform3-3A.sh`

---

### Phase 3B — Hint Kind 扩展

**兑现**: "8 fix types: env vars, working directory, timeouts, locale, flags,
directories, retry, package install (opt-in only)"

**交付物**: hint kind 从 3 种扩展到 8 种。

#### Hint Kind 清单

| kind | 触发 | 应用 | 安全 |
|------|------|------|------|
| `set_env` | ✅ 已有 | 设环境变量 | safe |
| `rewrite_cwd` | ✅ 已有 | 切换 cwd | safe |
| `set_timeout` | ✅ 已有 | 调整超时 | safe |
| `append_flags` | 缺确认标志 | 追加参数 | safe — **allowlist 合约见下** |
| `set_locale` | encoding 错误 | LC_ALL/LANG | safe |
| `create_dir` | ENOENT on 目录 | mkdir -p | safe — **scoping 合约见下** |
| `retry_with_backoff` | 网络超时/429 | 等待重试 | safe |
| `install_package` | 缺包 | pip/npm install | **需用户 opt-in** |

#### append_flags allowlist 合约

`append_flags` 只允许以下预定义标志，不接受任意字符串：

```python
SAFE_APPEND_FLAGS = {
    "--yes", "-y",              # 确认提示
    "--force", "-f",            # 覆盖已有
    "--no-interactive",         # 禁用交互
    "--non-interactive",
    "--batch",                  # 批处理模式
    "--quiet", "-q",            # 减少输出
    "--no-color",               # 禁用颜色
    "--no-progress",            # 禁用进度条
}
```

adapter `apply_hints` 收到不在此集合内的 flag 时直接 reject。
门控 3B-G5 验证：构造一个含非 allowlist flag 的 hint，assert rejected。

#### create_dir scoping 合约

`create_dir` 的 `target` 路径必须满足：
1. 是相对路径（不能 mkdir /etc/xxx）
2. resolve 后在 cwd 子树内（不能 mkdir ../../../tmp/xxx）
3. 深度 ≤ 3 级（不能 mkdir a/b/c/d/e/f）

不满足时 reject。门控 3B-G7 验证。

#### install_package 合约

对应产品承诺 "Won't install packages unless you explicitly allow it"：
- 默认 rejected
- 只有 `--allow-install` CLI flag 显式启用
- 包名只能从 stderr regex capture group 提取，不接受 hint 中硬编码的包名
- 不进 `_SAFE_AUTOFIX_KINDS`，R4a 永不自动安装包

#### 3B 门控

| ID | 断言 | 兑现 |
|----|------|------|
| 3B-G1 | HINT_KINDS 包含 8 种 | 8 fix types |
| 3B-G2 | adapter 每种 kind 有应用逻辑 | 全部可执行 |
| 3B-G3 | install_package standard profile rejected | 不装包除非 opt-in |
| 3B-G4 | R4a safe set = 7 种，不含 install | 安全默认 |
| 3B-G5 | 非 allowlist flag 被 reject | append_flags 合约 |
| 3B-G6 | Platform 2 R4a 全部通过 | 不回归 |
| 3B-G7 | cwd 外路径 / 绝对路径 / 过深路径被 reject | create_dir 合约 |

**改动范围**:
- `polaris_failure_records.py`: HINT_KINDS 扩展 (1 行)
- `polaris_adapter_shell.py`: apply_hints 新增 5 种 kind (~100 行，含 allowlist/scoping)
- `polaris_orchestrator.py`: _SAFE_AUTOFIX_KINDS 扩展 (1 行)
- `polaris_orchestrator.py`: _build_failure_avoidance_hints 新增模式 (~40 行)
- 新增: `scripts/regression-platform3-3B.sh`

---

### Phase 3C — 经验库扩容

**兑现**: "{ACTUAL_COUNT} cataloged error patterns across {ACTUAL_ECO_COUNT}
ecosystems"、"首次命中率 ≥ 60%"、"every fix traces back to a cataloged pattern"

**交付物**: experience-packs 扩容 + reproduction case 验证体系。

#### 生态系统清单

| 批次 | 生态 | 依据 |
|------|------|------|
| 已有 | python, node, go | Platform 2 |
| 第一批 | rust, java, ruby, docker, terraform | GitHub CI 失败频率 |
| 第二批 | php, dotnet, swift, kotlin, scala | 语言覆盖 |
| 第三批 | k8s, ansible, gradle, maven, cmake, make | 构建/部署工具 |

#### error_class 分类体系 (~15 个/生态)

`missing_dependency`, `syntax_error`, `permission_denial`, `file_not_found`,
`encoding_error`, `resource_exhaustion`, `network_error`, `version_conflict`,
`build_error`, `config_error`, `auth_error`, `rate_limit`, `timeout`,
`disk_full`, `port_conflict`

#### 每条 prebuilt pattern 的完整结构

```json
{
  "error_class": "missing_dependency",
  "stderr_pattern": "ModuleNotFoundError: No module named '([^']+)'",
  "avoidance_hints": [{"kind": "set_env", "vars": {"PYTHONPATH": ".:src"}}],
  "description": "Python import failure — add project dirs to PYTHONPATH",
  "reproduction": {
    "setup": "mkdir -p /tmp/polaris-repro && cd /tmp/polaris-repro",
    "command": "python3 -c \"import mylocal\"",
    "trigger_env": {},
    "expected_stderr_match": "ModuleNotFoundError",
    "fix_env": {"PYTHONPATH": ".:src"},
    "fix_command": null,
    "expected_fix_outcome": "different_error_or_success"
  }
}
```

`reproduction` 字段定义了这条 pattern 的可执行验证：
- `trigger_env` + `command` → 必须触发匹配 `expected_stderr_match` 的错误
- `fix_env` 应用后重跑 → 结果必须不同于原错误 (`different_error_or_success`)

这是 prebuilt pattern 称 "cataloged" 而非 "guessed" 的证据。

#### 生成流程

```
1. 从公开语料提取 stderr snippet
2. 归类 ecosystem/error_class
3. 编写 stderr_pattern (regex)
4. 编写 avoidance_hints (映射到 8 种 kind)
5. 编写 reproduction case
6. 自动执行 reproduction → 验证 hint 改变结果
7. R3 门控 (recall ≥ 60%, precision ≥ 80%)
8. 写入分片文件
```

#### 3C 门控

| ID | 断言 | 兑现 |
|----|------|------|
| 3C-G1 | 总记录数 ≥ 目标 (分批交付) | 文案数字的来源 |
| 3C-G2 | 生态覆盖 ≥ 目标 | 文案数字的来源 |
| 3C-G3 | 每生态 recall ≥ 60% (fixture) | 首次命中率 |
| 3C-G4 | 每生态 precision ≥ 80% | 不误修 |
| 3C-G5 | 全量 regex 0 编译错误 | 工程质量 |
| 3C-G6 | 磁盘 < 10MB | 可分发 |
| 3C-G7 | 分片查询 < 2ms (最大 shard) | 亚秒修复 |
| 3C-G8 | fixture 首次命中率 ≥ 60% | **判定条件 1** |
| 3C-G9 | 全量 reproduction case 通过 | **"cataloged" 的证据** |

3C-G8 和 3C-G9 是 kill gate。G8 不过 = 首次命中率不达标 = 不发布。
G9 不过 = 有 pattern 声称能修但实际不能修 = 不发布。

**改动范围**:
- `experience-packs/` 重构为分片 + reproduction 结构
- `experience-packs/index.json` 新增
- ~300 个 JSON 分片文件
- `scripts/build-packs.py` (语料 → 分片)
- `scripts/verify-reproductions.py` (批量执行 reproduction case)
- `scripts/regression-platform3-3C.sh`

---

### Phase 3D — 贡献回流管道

**兑现**: "The library grows with every user who contributes back"、判定条件 3

**交付物**: `polaris experience contribute` + 中央验证 CI。

#### 本地侧

```bash
polaris experience contribute [--dry-run] [--output FILE]
```

筛选条件——只有被实战验证过的才可贡献：
```python
def _is_contributable(rec: dict) -> bool:
    return (
        rec.get("source") in ("auto", "user_correction")
        and rec.get("applied_count", 0) >= 1
        and rec.get("applied_fail_count", 0) == 0
        and not rec.get("stale", False)
        and rec.get("stderr_pattern")
        and rec.get("avoidance_hints")
        and rec.get("ecosystem")
    )
```

脱敏——绝对不传 stderr 原文、命令、路径、时间：
```python
def _sanitize(rec: dict) -> dict:
    return {
        "ecosystem":        rec["ecosystem"],
        "error_class":      rec.get("error_class", "unknown"),
        "stderr_pattern":   rec["stderr_pattern"],
        "avoidance_hints":  rec["avoidance_hints"],
        "description":      rec.get("description", ""),
        "applied_count":    rec["applied_count"],
        "contributor_hash": sha256(machine_id())[:12],
    }
```

#### 中央侧

GitHub repo `polaris-hub/experience-packs`。CI 自动验证：
1. JSON schema 合法
2. stderr_pattern 编译通过，无 ReDoS 风险
3. hint kind 在允许集合内
4. 去重：和现有 pack 对比
5. 生成 reproduction case 并执行（和 3C-G9 同标准）
6. 人工只审 hint 安全性

合并后自动：路由到分片 → 更新 index.json → 全量 R3 → 发布新版本。

#### 3D 门控

| ID | 断言 | 兑现 |
|----|------|------|
| 3D-G1 | prebuilt 不贡献，未验证不贡献 | 只有实战验证的进库 |
| 3D-G2 | 输出不含 stderr_summary/command/fingerprint | 脱敏 |
| 3D-G3 | 输出符合 contribution schema | 中央可消费 |
| 3D-G4 | --dry-run 不写文件 | 可预览 |
| 3D-G5 | validate.py 拒绝无效 regex/hint | CI 拦截 |
| 3D-G6 | 重复 pattern 被标记 | 不膨胀 |
| 3D-G7 | merge 后全量 R3 通过 | 不降质 |
| 3D-G8 | 贡献→审核→合并→命中 端到端走通 | **判定条件 3** |

---

### Phase 3E — 显示层

**兑现**: 诚实的来源标记、贡献者激励

**交付物**: CLI 输出标记 pattern 来源和验证状态。

3E 分两段完成：
- 3E-a: 基础来源标记（prebuilt / local）——只依赖 3C
- 3E-b: contributed/verified deployment 计数显示——依赖 3D

#### 输出规范

```
# prebuilt 命中（无用户验证数据）
[polaris] ⚡ auto-fix: set LC_ALL="C.UTF-8" (from community knowledge base)
[polaris] ✓ auto-fixed in 0.08s

# contributed 命中（有真实验证数据）
[polaris] ⚡ auto-fix: set DOCKER_HOST="..." (verified in 2,341 deployments)
[polaris] ✓ auto-fixed in 0.06s

# 自己的贡献被命中
[polaris] ⚡ auto-fix: set DOCKER_HOST="..." (your contribution, verified in 2,341 deployments)
[polaris] ✓ auto-fixed in 0.06s

# 本地经验命中
[polaris] ↻ applied 2 experience hints from previous failures
[polaris] ✓ succeeded on first try (experience hit: avoided missing_dependency)
```

#### 3E 门控

| ID | 断言 | 兑现 |
|----|------|------|
| 3E-G1 | prebuilt hit → "community knowledge base" | 不伪造计数 |
| 3E-G2 | contributed hit → "verified in N deployments" | 真实数据 |
| 3E-G3 | 无 hit 无多余消息 | 不造噪声 |
| 3E-G4 | Platform 2 R5 全部通过 | 不回归 |

**改动范围**: `polaris_cli.py` `_emit_experience_summary` 扩展 (~30 行)

---

## 执行顺序

```
3A (分片引擎) ──────┐
                    ├→ 3C (扩容) ──→ 3E-a (prebuilt/local 显示)
3B (hint 扩展) ─────┘      │
                           ├→ 3D (贡献管道) ──→ 3E-b (verified 计数显示)
                           │
                           └──────────────────→ 发布判定
```

- 3A + 3B 并行
- 3C 依赖 3A (分片) + 3B (新 kind)
- 3D 依赖 3C (有库才有贡献价值)
- 3E-a 依赖 3C (需要 prebuilt/local 来源数据)
- 3E-b 依赖 3D (需要 contributed/verified 计数)
- **发布判定在 3E 之后，三个条件全过才发布**

### 里程碑

| 里程碑 | Phase | 状态 |
|--------|-------|------|
| M1: 引擎就绪 | 3A + 3B | 内部可测试，架构可撑万级 |
| M2: 经验库就绪 | 3C + 3E-a | 内部验收，prebuilt/local 显示可用，不对外发布 |
| M3: 飞轮就绪 | 3D + 3E-b | 贡献全链路走通，verified 计数显示可用 |
| **M4: 发布判定** | 全部 | **三个条件全过 → 发布到 ClawHub** |

M2 不是发布点。M4 才是。M2 到 M4 之间是内部验收期：跑全量 fixture、
执行全量 reproduction、验证贡献管道、确认文案数字。

---

## 全量门控矩阵

| 套件 | 门控数 | 来源 |
|------|--------|------|
| R0 | 18 | Platform 2 |
| R2-merge | 11 | Platform 2 |
| R2-contract | 9 | Platform 2 |
| R3 | 7 → 扩展 | Platform 2 → 3C |
| R4a | 10 | Platform 2 |
| R5 | 8 | Platform 2 |
| 3A | 5 | Platform 3 |
| 3B | 7 | Platform 3 |
| 3C | 9 | Platform 3 |
| 3D | 8 | Platform 3 |
| 3E | 4 | Platform 3 |

**总计 96 个门控。`bash regression-platform3-all.sh` 一键验证。**

---

## 风险和缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| 误修复 | 用户信任崩塌 | reproduction case 验证 + applied_fail ≥ 3 自动 stale |
| install_package 供应链攻击 | 安全事件 | 默认 rejected，不进 R4a safe set |
| 恶意 regex | ReDoS | CI regex 复杂度检查 + 执行超时 |
| 首次命中率 < 60% | 产品无法发布 | 继续扩 pattern 直到达标，不降标准 |
| reproduction case 环境依赖 | 门控不稳定 | Docker 化执行环境，固定版本 |

---

## 不做的事

1. **不接 LLM** — 确定性引擎，零 token，这是定位
2. **不做实时同步** — pull 模型，无 P2P
3. **不做用户系统** — contributor_hash 匿名
4. **不改状态机** — Platform 1 合约不变
5. **不改 adapter 接口** — 只扩展 kind 处理
6. **不在未达标时发布** — 三个条件缺一不发
7. **不在文案中写未达到的数字** — 实际多少写多少
