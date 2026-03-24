# Trialogue v4: Alpha → Fully Hardened Final 升级清单

基线：v4 alpha / engineering release — 393/393 tests passing, 14 test files
目标：fully hardened final — 可对外交付的安全网关
**状态：已完成 — 483/483 tests passing, 18 test files (2026-03-24)**

---

## 阻塞层 (Blockers) — 不过则不能叫 hardened

### V4-B1: audit_mode=strict（审计失败阻断管道）

**现状**：审计链写入失败时，管道仍返回清洗后内容（best-effort）。`audit_status: "failed"` 仅作为元数据字段。

**目标**：新增 `audit_mode=strict`。strict 模式下审计写入失败 → 管道返回错误，不吐内容。

**锚点**：
- `pipeline.py` 218–231 行：audit wiring `except Exception` 分支
- `config.py` DEFAULTS：添加 strict 到 audit_mode 文档
- `trialogue-v4.conf.example`：说明三态（local / strict / disabled）

**验收**：
- [ ] `audit_failure_test.py` 扩展：strict 模式 + 不可写 chain dir → pipeline_fetch 返回 error，无 cleaned_text
- [ ] strict 模式 + 正常 chain → 正常返回
- [ ] MCP server 在 strict 模式下正确返回 error response

**工期**：0.5 天

---

### V4-B2: Hook allowlist 冲突检测

**现状**：`trialogue guard on` 注入 PreToolUse hooks，但不检查 WebFetch/WebSearch 是否在用户的 Claude Code allowlist 中。已知 bug：如果工具在 allowlist，hook deny 决策被 Claude Code 忽略。

**目标**：`guard on` 时读取 `~/.claude/settings.json` 和项目级 `.claude/settings.json` 的 `permissions.allow` 列表。如果 WebFetch/WebSearch 在 allowlist 中：
- 默认行为：**guard on 失败（非零退出）**，打印具体冲突条目
- `--fix` flag：自动从 allowlist 移除冲突条目，然后继续 guard on
- 理由：allowlist 冲突 = hook deny 被 Claude Code 忽略 = guard 形同虚设。"成功但警告"不配叫 blocker，必须硬失败

**锚点**：
- `trialogue` CLI `_inject_guard()` 函数
- Claude Code settings 路径：`~/.claude/settings.json`、`.claude/settings.json`

**验收**：
- [ ] `trialogue_cli_test.py` 扩展：模拟 allowlist 包含 WebFetch → guard on 非零退出 + 错误信息指明冲突
- [ ] `--fix` flag：自动移除冲突条目 → guard on 成功
- [ ] allowlist 无冲突时：guard on 正常成功，无额外输出

**工期**：0.5 天

---

## 核心层 (Core) — hardened 的成色取决于此

### V4-C1: 多命令绕过防御 — 网络出口控制

**现状**：curl/wget 拦截靠 bash 参数 pattern matching。已知绕法：`bash -c "curl ..."`、变量拼接、`python3 -c "urllib..."`、`nc`/`socat` 等——pattern 追不完。

**目标**：网络层出口控制。分两步：先解决运行身份分离（前置），再写规则。

#### 前置：运行身份分离

**问题**：当前 `mcp-server.py` / `pipeline.py` 以调用者身份运行（与 agent 同一 UID）。iptables `--uid-owner` 无法区分 guard 流量和 agent 流量——它们是同一个用户。

**方案（三选一，需在实施前拍板）**：

**S1 — 专用系统用户 `_trialogue`**：
- `guard on --egress` 创建 `_trialogue` 用户（`useradd --system --no-create-home`）
- MCP server 通过 `sudo -u _trialogue` 启动（Claude Code MCP config 的 command 改为 `sudo -u _trialogue python3 mcp-server.py`）
- iptables 规则：`--uid-owner _trialogue` ACCEPT，其余 REJECT 出站 80/443
- 需要 root 做初始化（创建用户 + 写 sudoers rule）
- 优势：最干净的内核级隔离
- 代价：部署复杂度高，需 root

**S2 — cgroup + iptables cgroup match**：
- `guard on` 创建 cgroup `trialogue.slice`
- MCP server 启动时 `systemd-run --slice=trialogue.slice` 或手动 `cgexec`
- iptables `-m cgroup --cgroup <classid>` match
- 优势：不需要额外用户
- 代价：依赖 cgroup v2 + iptables cgroup match 模块，兼容性窄

**S3 — network namespace（最强隔离）**：
- `guard on` 创建 netns `trialogue_ns`，veth pair 桥接到主机
- MCP server 在 netns 内运行（`ip netns exec trialogue_ns python3 mcp-server.py`）
- 主机侧 iptables 只允许 veth 出站
- 优势：agent 进程完全无法触及外部网络
- 代价：最复杂，DNS/路由需要额外配置

**推荐路径**：S1 作为默认，S3 作为高安全选项。S2 兼容性太窄暂不做。

#### 规则层

身份分离就位后，规则本身简单：
```
# guard on --egress 写入：
iptables -A OUTPUT -p tcp --dport 80  -m owner --uid-owner _trialogue -j ACCEPT
iptables -A OUTPUT -p tcp --dport 443 -m owner --uid-owner _trialogue -j ACCEPT
iptables -A OUTPUT -p tcp --dport 80  -j REJECT --reject-with tcp-reset
iptables -A OUTPUT -p tcp --dport 443 -j REJECT --reject-with tcp-reset
# guard off 清除：
iptables -D ... (逆序)
```

#### 降级模式

无 root 时：
- 身份分离不可用 → iptables 规则不可用
- 回退到 pattern matching 层（现有 `intercept-curl.sh`）
- `guard on` 输出 WARNING："network egress control requires root — falling back to pattern matching only"
- `trialogue status` 显示 `egress_control: pattern_only`（而非 `kernel`）

**锚点**：
- `hooks/intercept-curl.sh`：现有 pattern 层保留（降级模式的唯一防线）
- 新增 `egress.py`：身份分离 + iptables 规则管理
- `trialogue` CLI：`guard on --egress` 触发（或自动检测 root 后提示）
- `mcp-server.py` 启动入口：需支持 `sudo -u _trialogue` 方式调用

**验收**：
- [ ] 无 root 时：pattern 层生效 + WARNING + status 显示 `pattern_only`
- [ ] 有 root 时：创建 `_trialogue` 用户 + iptables 规则生效
- [ ] 有 root 时：agent 进程 `curl https://...` 被 REJECT
- [ ] 有 root 时：agent 进程 `python3 -c "urllib.request.urlopen('https://...')"` 被 REJECT
- [ ] 有 root 时：MCP server（_trialogue 身份）正常 fetch
- [ ] `guard off` 清除 iptables 规则（不删用户——用户可复用）
- [ ] 跨发行版：Debian/Ubuntu + RHEL/Fedora + Alpine 基本兼容

**工期**：3–5 天（含身份分离设计 + 实现 + 降级路径 + 跨发行版测试）

**这是 7 条中最重的一条。** 不只是"写 iptables 规则"——前置的身份分离是真正的工程量。Pattern matching 是猫鼠游戏，内核级身份隔离才是终局。

---

### V4-C2: Remote audit anchor（远程审计锚点）

**现状**：`audit.py` 仅本地 JSONL 链。docstring 已明确声明 remote 未实现。

**目标**：实现 `publish_ingestion_anchor()` — 将链头 hash 定期推送到外部 sink（S3、webhook、或 append-only log 服务）。

**设计约束**：
- anchor 发布失败不应阻断管道（除非 audit_mode=strict）
- 发布频率：每 N 条 ingestion 或定时（可配置）
- sink 类型通过 config 指定：`remote_anchor_sink=s3|webhook|file`

**锚点**：
- `audit.py`：新增 `publish_ingestion_anchor()`
- `config.py` DEFAULTS：新增 `remote_anchor_sink`、`remote_anchor_url`、`remote_anchor_interval`
- `pipeline.py`：audit wiring 后触发 anchor check

**验收**：
- [ ] webhook sink：POST chain summary 到指定 URL
- [ ] file sink：append 到指定路径（跨机器共享目录场景）
- [ ] 发布失败 → 日志 + `anchor_status: "failed"` 元数据
- [ ] strict 模式 + 发布失败 → 阻断

**工期**：1.5–2 天

---

## 证明层 (Proof) — 证明它在真实场景下 work

### V4-P1: Codex 端到端验证

**现状**：`codex_mcp_test.py` 只验证 `codex mcp add/list/remove`（注册层）。Codex 缺少 PreToolUse hooks，无法强制路由。

**目标**：
1. 验证 Codex 通过 MCP 调用 `trialogue_fetch` 的完整路径
2. 文档化 Codex 的限制：无强制路由，agent 必须自愿使用 MCP 工具
3. 如果 Codex 未来支持 hooks → 预留扩展点

**验收**：
- [ ] Codex MCP 端到端测试：注册 → 启动 Codex → 调用 trialogue_fetch → 验证返回清洗后内容
- [ ] 测试脚本可在 Codex 未安装时 skip（现有模式）

**工期**：0.5–1 天（取决于 Codex 测试环境可用性）

---

### V4-P2: Search endpoint 集成

**现状**：`search_endpoint` 配置项存在但为空。WebSearch hook 在无 endpoint 时 passthrough。pipeline_search() 存在但依赖外部 API。

**目标**：
1. 接入至少一个真实搜索 API（Brave Search / SearXNG / 自建）
2. 验证 pipeline_search → sanitize → audit → return 全路径
3. WebSearch hook 在有 endpoint 时 deny + 返回清洗后搜索结果

**验收**：
- [ ] 配置 search_endpoint 后 pipeline_search 返回清洗后结果
- [ ] WebSearch hook 正确拦截并返回清洗后搜索结果
- [ ] 搜索结果中的注入内容被 tsan 剥离

**工期**：1 天

---

### V4-P3a: 组件级端到端测试

**现状**：测试覆盖各组件（pipeline、MCP protocol、hooks、CLI、audit），但没有把它们串成一条完整路径。

**目标**：一个测试脚本在进程内串联所有组件：
1. 启动 fixture HTTP server（含注入内容）
2. 启动 MCP server（stdio subprocess）
3. 发送 MCP `tools/call` for `trialogue_fetch`
4. 验证返回内容已清洗
5. 验证 audit chain 已追加
6. 验证 hook 脚本对同一 URL 的 deny + reason 内容与 MCP 结果一致

**证明强度**：证明 hook + MCP + pipeline + audit 组件组合一致。不证明 Claude Code harness 是否真的执行 hook deny 语义。

**锚点**：
- `tests/fetch_injection_test.py`：已有 FixtureServer，可复用
- `tests/mcp_protocol_test.py`：已有 MCP 协议测试框架

**验收**：
- [ ] 单命令运行：`python3 tests/e2e_component_test.py`
- [ ] 覆盖 fetch + search（有 endpoint 时）
- [ ] 覆盖 audit 三态（local / strict / disabled）

**工期**：1 天

---

### V4-P3b: 真实 harness 端到端测试

**现状**：无。没有测试验证真实 Claude Code session 中 guard on → WebFetch → hook intercept → deny → agent 收到 reason 这条路径。

**目标**：在真实 Claude Code headless/session 环境中验证完整流程。

**方案**：
1. `claude --headless` 模式（如果支持 non-interactive execution）发送包含 WebFetch 调用的 prompt
2. 验证 hook 被触发（检查 stderr/日志）
3. 验证 agent 收到 deny reason（包含清洗后内容）
4. 验证 audit chain 被追加

**难点 & 诚实约束**：
- Claude Code 目前没有稳定的 headless API 用于自动化测试
- 这可能需要手工验证 + 截图 / 日志录制，而非全自动脚本
- 如果 Claude Code 提供 `--print-events` 或类似 debug 输出，可以解析验证
- Codex 侧同理——缺少自动化测试入口

**验收**：
- [ ] 文档化的手工验证流程（带预期输出）
- [ ] 如果 headless API 可用：自动化脚本 `tests/e2e_harness_test.sh`
- [ ] 至少一次完整的手工验证记录（日志 / 截图 committed）

**工期**：0.5–1 天（手工验证）/ 1–2 天（如果要做自动化）

**注**：P3b 的证明强度取决于 Claude Code 的测试接口。如果 headless 不支持，这条的上限就是"有记录的手工验证"——诚实地说，这不如自动化，但比没有强。

---

## 实施顺序

```
Week 1 (Day 1–5):
  Day 1:   V4-B1 (audit strict) + V4-B2 (allowlist hard fail)   ← 阻塞层清零
  Day 2:   V4-C1 前置：身份分离方案拍板 + _trialogue 用户创建   ← 设计日
  Day 3–4: V4-C1 实现：egress.py + iptables 规则 + 降级路径     ← 最重的一条
  Day 5:   V4-C1 测试：跨发行版验证 + guard on/off 全流程

Week 2 (Day 6–10):
  Day 6:   V4-C2 (remote anchor)                                 ← 核心层收口
  Day 7:   V4-P1 (Codex e2e) + V4-P2 (search endpoint)          ← 证明层
  Day 8:   V4-P3a (组件级 e2e)                                   ← 可自动化
  Day 9:   V4-P3b (真实 harness e2e)                              ← 可能手工
  Day 10:  Buffer / 回归测试 / 文档更新 / README 升级
```

**关键路径**：V4-B1 → V4-C1（含身份分离）→ V4-C2（串行）
**可并行**：V4-B2 与任何 gate 并行；V4-P1/P2 互相并行；V4-P3a/P3b 串行（P3b 依赖 P3a 的 fixture）

---

## 交付标准

全部 7 gates 验收通过后：
- 测试数从 393 → 预估 450+ checks
- README 升级：移除 "honest constraints" 中已解决的条目
- `trialogue-v4.conf.example` 更新：含所有新配置项
- PLAN.md 更新：从 alpha 架构声明升级到 final 架构声明

---

*基线：v4 alpha (2026-03-24) — 393 checks, 14 test files*
*目标：v4 final — 8 gates (P3 拆为 P3a+P3b), 3 tiers, ~450+ checks*
