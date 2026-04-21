# Platform 2 — Product Survival Plan

**审计链**: P1 Claude 分析 → Codex 敌对审查 → P1 Claude 修正 → Codex 确认收敛
**目标**: 从"技术可靠"到"用户愿意主动选择"
**时间基线**: 激进，以天计
**模拟策略**: 全部回归通过构造数据 + 断言验证，不依赖真实用户行为

---

## Phase A — 分发入口 + 可感知价值（2 天）

### A1: `polaris run` 顶层 CLI 入口
**时间**: 1 天
**Gate**: `polaris run "npm test"` 一行调用完成完整生命周期（init → execute → result），无需手动设任何环境变量
**交付件**:
- `polaris_cli.py` — 顶层入口，解析 `polaris run <command> [--goal] [--profile] [--runtime-dir]`
- 内部自动处理: runtime dir 创建、state init、fingerprint 计算、adapter 选择、执行、经验记录
- 默认值: profile=micro, runtime_dir=`/tmp/polaris-<hash>`
- 注: `--output-mode` 在 A1 审计中移除（死参数），输出模式由 orchestrator 内部控制
- SKILL.md 更新: 调用示例从 20 行环境变量降到 1 行命令

**等价性合约**: CLI 入口内部调用与环境变量入口完全相同的模块路径（orchestrator.run → state.init → adapters.select → shell.execute → report.emit），不引入任何绕过或替代逻辑。验证方式：同一命令分别通过 CLI 和环境变量入口执行，产生的 execution-state.json diff 为空（除 run_id 和时间戳外）。

**模拟回归脚本**: `regression-platform2-A1.sh`
```bash
#!/usr/bin/env bash
set -euo pipefail
PASS=0; FAIL=0; TOTAL=0

assert_eq() { TOTAL=$((TOTAL+1)); if [ "$1" = "$2" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: expected='$2' got='$1' — $3"; fi; }
assert_contains() { TOTAL=$((TOTAL+1)); if echo "$1" | grep -qF "$2"; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: output missing '$2' — $3"; fi; }
assert_file_exists() { TOTAL=$((TOTAL+1)); if [ -f "$1" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: file not found '$1' — $2"; fi; }

# --- Test 1: 成功命令，完整生命周期 ---
RTDIR=$(mktemp -d)
OUT=$(python3 Polaris/scripts/polaris_cli.py run "echo hello-polaris" --runtime-dir "$RTDIR" 2>&1) || true
EXIT=$?
assert_eq "$EXIT" "0" "A1-T1: echo command should exit 0"
assert_file_exists "$RTDIR/execution-state.json" "A1-T1: state file must exist"
STATUS=$(python3 -c "import json; print(json.load(open('$RTDIR/execution-state.json'))['status'])")
assert_eq "$STATUS" "completed" "A1-T1: final status must be completed"
rm -rf "$RTDIR"

# --- Test 2: 失败命令，failure_record 写入 ---
RTDIR=$(mktemp -d)
OUT=$(python3 Polaris/scripts/polaris_cli.py run "false" --runtime-dir "$RTDIR" 2>&1) || true
EXIT=$?
assert_eq "$((EXIT != 0 ? 1 : 0))" "1" "A1-T2: false command should exit non-zero"
assert_file_exists "$RTDIR/failure-records.json" "A1-T2: failure records must exist"
FCOUNT=$(python3 -c "import json; d=json.load(open('$RTDIR/failure-records.json')); print(len(d.get('records',[])))")
assert_eq "$((FCOUNT > 0 ? 1 : 0))" "1" "A1-T2: at least one failure record"
rm -rf "$RTDIR"

# --- Test 3: standard profile 完整流程 ---
RTDIR=$(mktemp -d)
OUT=$(python3 Polaris/scripts/polaris_cli.py run "echo standard-test" --profile standard --runtime-dir "$RTDIR" 2>&1) || true
PROFILE=$(python3 -c "import json; print(json.load(open('$RTDIR/execution-state.json')).get('runtime',{}).get('execution_profile',''))")
assert_eq "$PROFILE" "standard" "A1-T3: profile must be standard"
rm -rf "$RTDIR"

# --- Test 4: 等价性 — CLI 入口 vs 环境变量入口产生一致 state ---
RTDIR_CLI=$(mktemp -d)
RTDIR_ENV=$(mktemp -d)
python3 Polaris/scripts/polaris_cli.py run "echo equiv-test" --runtime-dir "$RTDIR_CLI" --profile micro 2>&1 || true
POLARIS_GOAL="echo equiv-test" POLARIS_RUNTIME_DIR="$RTDIR_ENV" POLARIS_EXECUTION_PROFILE=micro \
  python3 Polaris/scripts/polaris_orchestrator.py 2>&1 || true
# 比较 state（排除 run_id, 时间戳）
CLI_STATE=$(python3 -c "
import json
s=json.load(open('$RTDIR_CLI/execution-state.json'))
for k in ['run_id','updated_at','started_at']: s.pop(k,None)
s.get('runtime',{}).pop('started_at',None)
print(json.dumps(s, sort_keys=True))
")
ENV_STATE=$(python3 -c "
import json
s=json.load(open('$RTDIR_ENV/execution-state.json'))
for k in ['run_id','updated_at','started_at']: s.pop(k,None)
s.get('runtime',{}).pop('started_at',None)
print(json.dumps(s, sort_keys=True))
")
assert_eq "$CLI_STATE" "$ENV_STATE" "A1-T4: CLI and ENV entry must produce equivalent state"
rm -rf "$RTDIR_CLI" "$RTDIR_ENV"

# --- Test 5: 无参数调用应报错 ---
OUT=$(python3 Polaris/scripts/polaris_cli.py run 2>&1) || true
EXIT=$?
assert_eq "$((EXIT != 0 ? 1 : 0))" "1" "A1-T5: run without command should fail"
assert_contains "$OUT" "usage" "A1-T5: should print usage hint"

echo "=== A1 Results: $PASS/$TOTAL passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
```

**Codex 审计要求**:
- 等价性测试（T4）是硬门：CLI 入口不能引入任何 state 差异
- 验证 polaris_cli.py 没有绕过 orchestrator 的任何子模块直接操作 state

---

### A2: 首次价值可见化
**时间**: 0.5 天
**Gate**: 每次 run 结束后，stderr 包含人类可读的经验摘要行（不污染 stdout JSON）
**依赖**: A1（通过 CLI 入口的 stderr 输出）
**交付件**:
- 执行成功时: `[polaris] ✓ learned: success pattern captured (fingerprint: <key>, adapter: <name>)`
- 执行失败时: `[polaris] ✗ learned: <error_class> → avoidance hints [<hint_kinds>] stored for next run`
- 经验命中时: `[polaris] ↻ applied <N> avoidance hints from previous failures`
- 无经验命中时: `[polaris] first run for this task, no prior experience`
- 输出位置: orchestrator 的 emit 路径末端，写入 stderr（不污染 stdout 的 JSON 输出）

**模拟回归脚本**: `regression-platform2-A2.sh`
```bash
#!/usr/bin/env bash
set -euo pipefail
PASS=0; FAIL=0; TOTAL=0

assert_contains() { TOTAL=$((TOTAL+1)); if echo "$1" | grep -qF "$2"; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: output missing '$2' — $3"; fi; }
assert_not_contains() { TOTAL=$((TOTAL+1)); if echo "$1" | grep -qF "$2"; then FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: output should NOT contain '$2' — $3"; else PASS=$((PASS+1)); fi; }

# --- Test 1: 首次成功 → learned 输出 ---
RTDIR=$(mktemp -d)
OUT=$(python3 Polaris/scripts/polaris_cli.py run "echo first-success" --runtime-dir "$RTDIR" 2>&1)
assert_contains "$OUT" "[polaris]" "A2-T1: must have [polaris] prefix"
assert_contains "$OUT" "learned" "A2-T1: must indicate learning happened"
assert_contains "$OUT" "success pattern captured" "A2-T1: success pattern message"
rm -rf "$RTDIR"

# --- Test 2: 首次失败 → learned + hint 类型 ---
RTDIR=$(mktemp -d)
OUT=$(python3 Polaris/scripts/polaris_cli.py run "false" --runtime-dir "$RTDIR" 2>&1) || true
assert_contains "$OUT" "[polaris]" "A2-T2: must have [polaris] prefix"
assert_contains "$OUT" "learned" "A2-T2: must indicate learning happened"
assert_contains "$OUT" "stored for next run" "A2-T2: must indicate persistence"
rm -rf "$RTDIR"

# --- Test 3: 第二次运行同命令（复用同一 runtime dir）→ 经验命中 ---
RTDIR=$(mktemp -d)
# 第一次：故意失败，写入经验
python3 Polaris/scripts/polaris_cli.py run "python3 -c 'import nonexistent_module_xyz'" --runtime-dir "$RTDIR" 2>&1 || true
# 第二次：同命令同目录，应命中经验
OUT2=$(python3 Polaris/scripts/polaris_cli.py run "python3 -c 'import nonexistent_module_xyz'" --runtime-dir "$RTDIR" 2>&1) || true
assert_contains "$OUT2" "applied" "A2-T3: must indicate experience was applied"
assert_contains "$OUT2" "avoidance hints" "A2-T3: must mention avoidance hints"
rm -rf "$RTDIR"

# --- Test 4: 首次运行无历史经验 → 明确提示 ---
RTDIR=$(mktemp -d)
OUT=$(python3 Polaris/scripts/polaris_cli.py run "echo brand-new-task" --runtime-dir "$RTDIR" 2>&1)
assert_contains "$OUT" "first run" "A2-T4: must indicate no prior experience"
rm -rf "$RTDIR"

echo "=== A2 Results: $PASS/$TOTAL passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
```

**Codex 审计要求**:
- 经验摘要必须写入 stderr，不能混入 stdout 的 JSON 结构化输出
- 摘要内容必须与实际写入的 failure_records / success_patterns 一致（不能声称 learned 但没写入）

---

### A3: `polaris stats`
**时间**: 0.5 天
**Gate**: `polaris stats [--runtime-dir]` 输出经验库概览，数值与底层文件一致
**依赖**: A1（使用同一 runtime-dir 约定）
**交付件**:
- `polaris_stats.py` — 读取 failure-records.json + success-patterns.json + event-log.jsonl
- 输出格式（人类可读 + 可解析）:
```
Experience Store Summary
========================
Failure Records:  12 total (3 missing_dependency, 5 permission_denial, 4 unknown)
  Oldest: 2026-03-10  Newest: 2026-03-16
Success Patterns: 8 total (2 experimental, 4 validated, 2 preferred)
  By adapter: shell-command: 6, file-analysis: 2
Experience Hits:  45 queries, 28 hits (62.2% hit rate)
Top Tasks:
  1. npm test          — 12 hits
  2. python -m pytest  — 8 hits
  3. go test ./...     — 5 hits
```
- `--json` 标志输出 JSON 格式（供 OpenClaw agent 解析）

**模拟回归脚本**: `regression-platform2-A3.sh`
```bash
#!/usr/bin/env bash
set -euo pipefail
PASS=0; FAIL=0; TOTAL=0

assert_eq() { TOTAL=$((TOTAL+1)); if [ "$1" = "$2" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: expected='$2' got='$1' — $3"; fi; }
assert_contains() { TOTAL=$((TOTAL+1)); if echo "$1" | grep -qF "$2"; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: output missing '$2' — $3"; fi; }

# --- Test 1: 空经验库 ---
RTDIR=$(mktemp -d)
mkdir -p "$RTDIR"
OUT=$(python3 Polaris/scripts/polaris_stats.py --runtime-dir "$RTDIR" 2>&1)
assert_contains "$OUT" "no experience recorded yet" "A3-T1: empty store message"
rm -rf "$RTDIR"

# --- Test 2: 构造已知数量的记录，验证统计一致 ---
RTDIR=$(mktemp -d)
mkdir -p "$RTDIR"
python3 -c "
import json, datetime
now = datetime.datetime.utcnow().isoformat() + 'Z'
records = []
for i in range(5):
    records.append({
        'task_fingerprint': {'raw_descriptor': f'cmd-{i}', 'normalized_descriptor': f'cmd-{i}', 'matching_key': f'key{i:04x}'},
        'command': f'cmd-{i}',
        'error_class': 'missing_dependency' if i < 3 else 'permission_denial',
        'stderr_summary': 'err',
        'repair_classification': 'unknown',
        'avoidance_hints': [{'kind': 'set_env', 'vars': {'X': '1'}}],
        'recorded_at': now,
        'asset_version': 2
    })
json.dump({'schema_version': 1, 'records': records}, open('$RTDIR/failure-records.json', 'w'), indent=2)

patterns = []
for i in range(3):
    patterns.append({
        'pattern_id': f'pat-{i}',
        'fingerprint': f'pat-{i}',
        'summary': f'pattern {i}',
        'trigger': 'auto',
        'sequence': ['step1'],
        'outcome': 'ok',
        'evidence': [],
        'adapter': 'shell-command',
        'tags': [],
        'modes': ['standard'],
        'confidence': 80,
        'lifecycle_state': 'validated' if i < 2 else 'preferred',
        'best_lifecycle_state': 'preferred',
        'selection_count': 1,
        'validation_count': 1,
        'evidence_count': 1,
        'promotion_count': 0,
        'last_validated_at': now,
        'last_selected_at': now,
        'asset_version': 2
    })
json.dump({'schema_version': 1, 'patterns': patterns}, open('$RTDIR/success-patterns.json', 'w'), indent=2)
"
OUT=$(python3 Polaris/scripts/polaris_stats.py --runtime-dir "$RTDIR" 2>&1)
assert_contains "$OUT" "5 total" "A3-T2: failure records count must be 5"
assert_contains "$OUT" "3 total" "A3-T2: success patterns count must be 3"
assert_contains "$OUT" "missing_dependency" "A3-T2: must show error class breakdown"
assert_contains "$OUT" "permission_denial" "A3-T2: must show error class breakdown"
assert_contains "$OUT" "validated" "A3-T2: must show lifecycle breakdown"
rm -rf "$RTDIR"

# --- Test 3: --json 输出可解析 ---
RTDIR=$(mktemp -d)
mkdir -p "$RTDIR"
echo '{"schema_version":1,"records":[]}' > "$RTDIR/failure-records.json"
echo '{"schema_version":1,"patterns":[]}' > "$RTDIR/success-patterns.json"
OUT=$(python3 Polaris/scripts/polaris_stats.py --runtime-dir "$RTDIR" --json 2>&1)
python3 -c "import json; json.loads('''$OUT''')" 2>/dev/null
assert_eq "$?" "0" "A3-T3: --json output must be valid JSON"
rm -rf "$RTDIR"

echo "=== A3 Results: $PASS/$TOTAL passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
```

**Codex 审计要求**:
- 统计数值必须与底层 JSON 文件实际条目数一致，不允许估算或采样
- `--json` 输出必须是合法 JSON，字段名与人类可读版本语义对齐

---

## Phase B — 经验质量保障（2 天）

### B1: failure_records TTL + 降权
**时间**: 1 天
**Gate**: 过期记录不再注入，连续失败的 hints 自动降权
**依赖**: A1（CLI 入口用于端到端验证）
**交付件**:
- `failure-records.json` schema v2: 新增字段
  - `applied_count` (int): 该记录的 hints 被应用的总次数
  - `applied_fail_count` (int): 应用后任务仍失败的次数
  - `stale` (bool): 是否已降权
  - `rejected_by` (str|null): 如被用户拒绝，记录来源（"user"|null）
  - `source` (str): "auto"|"prebuilt"|"user_correction"（为 Phase C 预留）
- TTL: 默认 30 天，基于 `recorded_at`，可通过 `--ttl-days` 覆盖
- 降权逻辑:
  1. shell adapter 每次 apply hints 后，orchestrator 调用 `failure_records.update_applied(matching_key, success=True|False)`
  2. `applied_count++` 无论成功失败
  3. 如果 `success=False`: `applied_fail_count++`
  4. 如果 `applied_fail_count >= 3`: `stale=true`
- `query()` 过滤: 跳过 `stale=true` 和 `recorded_at + TTL < now()`
- schema v1 → v2 迁移: 检测 schema_version=1 时自动 backfill 新字段默认值

**模拟回归脚本**: `regression-platform2-B1.sh`
```bash
#!/usr/bin/env bash
set -euo pipefail
PASS=0; FAIL=0; TOTAL=0
SCRIPTS=Polaris/scripts

assert_eq() { TOTAL=$((TOTAL+1)); if [ "$1" = "$2" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: expected='$2' got='$1' — $3"; fi; }

# --- Test 1: 过期记录被跳过 ---
RTDIR=$(mktemp -d)
python3 -c "
import json, datetime
old = (datetime.datetime.utcnow() - datetime.timedelta(days=60)).isoformat() + 'Z'
now = datetime.datetime.utcnow().isoformat() + 'Z'
records = [
    {'task_fingerprint': {'matching_key': 'aaa'}, 'command': 'cmd1', 'error_class': 'unknown',
     'stderr_summary': '', 'repair_classification': 'unknown',
     'avoidance_hints': [{'kind': 'set_env', 'vars': {'X': '1'}}],
     'recorded_at': old, 'asset_version': 2,
     'applied_count': 0, 'applied_fail_count': 0, 'stale': False, 'rejected_by': None, 'source': 'auto'},
    {'task_fingerprint': {'matching_key': 'aaa'}, 'command': 'cmd1', 'error_class': 'unknown',
     'stderr_summary': '', 'repair_classification': 'unknown',
     'avoidance_hints': [{'kind': 'set_env', 'vars': {'Y': '2'}}],
     'recorded_at': now, 'asset_version': 2,
     'applied_count': 0, 'applied_fail_count': 0, 'stale': False, 'rejected_by': None, 'source': 'auto'}
]
json.dump({'schema_version': 2, 'records': records}, open('$RTDIR/failure-records.json', 'w'))
"
RESULT=$(python3 "$SCRIPTS/polaris_failure_records.py" query --matching-key aaa --store "$RTDIR/failure-records.json" --ttl-days 30 2>&1)
HINT_COUNT=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('avoidance_hints',[])))")
assert_eq "$HINT_COUNT" "1" "B1-T1: only fresh record hints returned (expired skipped)"
rm -rf "$RTDIR"

# --- Test 2: stale 记录被跳过 ---
RTDIR=$(mktemp -d)
python3 -c "
import json, datetime
now = datetime.datetime.utcnow().isoformat() + 'Z'
records = [
    {'task_fingerprint': {'matching_key': 'bbb'}, 'command': 'cmd2', 'error_class': 'unknown',
     'stderr_summary': '', 'repair_classification': 'unknown',
     'avoidance_hints': [{'kind': 'set_env', 'vars': {'X': '1'}}],
     'recorded_at': now, 'asset_version': 2,
     'applied_count': 5, 'applied_fail_count': 3, 'stale': True, 'rejected_by': None, 'source': 'auto'},
    {'task_fingerprint': {'matching_key': 'bbb'}, 'command': 'cmd2', 'error_class': 'unknown',
     'stderr_summary': '', 'repair_classification': 'unknown',
     'avoidance_hints': [{'kind': 'append_flags', 'flags': ['--verbose']}],
     'recorded_at': now, 'asset_version': 2,
     'applied_count': 1, 'applied_fail_count': 0, 'stale': False, 'rejected_by': None, 'source': 'auto'}
]
json.dump({'schema_version': 2, 'records': records}, open('$RTDIR/failure-records.json', 'w'))
"
RESULT=$(python3 "$SCRIPTS/polaris_failure_records.py" query --matching-key bbb --store "$RTDIR/failure-records.json" 2>&1)
HINT_COUNT=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('avoidance_hints',[])))")
assert_eq "$HINT_COUNT" "1" "B1-T2: only non-stale record hints returned"
rm -rf "$RTDIR"

# --- Test 3: update_applied 降权触发 ---
RTDIR=$(mktemp -d)
python3 -c "
import json, datetime
now = datetime.datetime.utcnow().isoformat() + 'Z'
records = [
    {'task_fingerprint': {'matching_key': 'ccc'}, 'command': 'cmd3', 'error_class': 'unknown',
     'stderr_summary': '', 'repair_classification': 'unknown',
     'avoidance_hints': [{'kind': 'set_env', 'vars': {'X': '1'}}],
     'recorded_at': now, 'asset_version': 2,
     'applied_count': 0, 'applied_fail_count': 2, 'stale': False, 'rejected_by': None, 'source': 'auto'}
]
json.dump({'schema_version': 2, 'records': records}, open('$RTDIR/failure-records.json', 'w'))
"
# 再失败一次，应该触发 stale
python3 "$SCRIPTS/polaris_failure_records.py" update-applied --matching-key ccc --success false --store "$RTDIR/failure-records.json" 2>&1
STALE=$(python3 -c "import json; r=json.load(open('$RTDIR/failure-records.json'))['records'][0]; print(r['stale'])")
assert_eq "$STALE" "True" "B1-T3: record should be stale after 3rd failure"
FAIL_COUNT=$(python3 -c "import json; r=json.load(open('$RTDIR/failure-records.json'))['records'][0]; print(r['applied_fail_count'])")
assert_eq "$FAIL_COUNT" "3" "B1-T3: applied_fail_count should be 3"
rm -rf "$RTDIR"

# --- Test 4: schema v1 → v2 自动迁移 ---
RTDIR=$(mktemp -d)
python3 -c "
import json
records = [
    {'task_fingerprint': {'matching_key': 'ddd'}, 'command': 'cmd4', 'error_class': 'unknown',
     'stderr_summary': '', 'repair_classification': 'unknown',
     'avoidance_hints': [{'kind': 'set_env', 'vars': {'X': '1'}}],
     'recorded_at': '2026-03-16T00:00:00Z', 'asset_version': 2}
]
json.dump({'schema_version': 1, 'records': records}, open('$RTDIR/failure-records.json', 'w'))
"
RESULT=$(python3 "$SCRIPTS/polaris_failure_records.py" query --matching-key ddd --store "$RTDIR/failure-records.json" 2>&1)
# 迁移后应该能正常 query
HINT_COUNT=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('avoidance_hints',[])))")
assert_eq "$HINT_COUNT" "1" "B1-T4: v1 record migrated and queryable"
# 验证迁移后文件有 v2 字段
HAS_FIELDS=$(python3 -c "
import json
r=json.load(open('$RTDIR/failure-records.json'))['records'][0]
print('applied_count' in r and 'stale' in r and 'source' in r)
")
assert_eq "$HAS_FIELDS" "True" "B1-T4: migrated record has v2 fields"
rm -rf "$RTDIR"

echo "=== B1 Results: $PASS/$TOTAL passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
```

**Codex 审计要求**:
- schema v1 → v2 迁移必须无损（原有字段全部保留）
- `stale` 标记是单向的：一旦 stale=true，除非用户通过 feedback 命令显式恢复，否则不可自动复活
- TTL 计算必须基于 UTC，不受本地时区影响

---

### B2: fingerprint 分层匹配
**时间**: 1 天
**Gate**: failure_records 支持 exact match + command-only fallback
**依赖**: B1（使用 schema v2 的 failure_records）
**交付件**:
- `polaris_task_fingerprint.py` 扩展:
  - 新增 `command_key` = SHA-256(normalized_command + "\0" + optional_task_name)，不含 cwd
  - 输出 JSON 新增 `command_key` 字段
  - `matching_key` 不变（保持向后兼容）
- `polaris_failure_records.py` 扩展:
  - `record()`: 同时写入 `task_fingerprint.command_key`
  - `query()` 两级匹配:
    1. exact: `matching_key` 完全匹配 → `match_tier: "exact"`, `confidence_discount: 1.0`
    2. fallback: `command_key` 匹配但 `matching_key` 不匹配 → `match_tier: "command_only"`, `confidence_discount: 0.6`
    3. 无匹配 → 空结果
  - `build_avoidance_hints()`: hints 携带 `confidence_discount` 字段
- `polaris_adapter_shell.py` 扩展:
  - `apply_hints()`: 跳过 `confidence_discount < 0.5` 的 hints（预留未来可调阈值）

**模拟回归脚本**: `regression-platform2-B2.sh`
```bash
#!/usr/bin/env bash
set -euo pipefail
PASS=0; FAIL=0; TOTAL=0
SCRIPTS=Polaris/scripts

assert_eq() { TOTAL=$((TOTAL+1)); if [ "$1" = "$2" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: expected='$2' got='$1' — $3"; fi; }

# --- 预计算 fingerprint ---
FP_DIR_A=$(python3 "$SCRIPTS/polaris_task_fingerprint.py" compute --command "npm test" --cwd "/project-a" 2>&1)
FP_DIR_B=$(python3 "$SCRIPTS/polaris_task_fingerprint.py" compute --command "npm test" --cwd "/project-b" 2>&1)
FP_OTHER=$(python3 "$SCRIPTS/polaris_task_fingerprint.py" compute --command "go test" --cwd "/project-a" 2>&1)

MK_A=$(echo "$FP_DIR_A" | python3 -c "import sys,json; print(json.load(sys.stdin)['matching_key'])")
MK_B=$(echo "$FP_DIR_B" | python3 -c "import sys,json; print(json.load(sys.stdin)['matching_key'])")
CK_A=$(echo "$FP_DIR_A" | python3 -c "import sys,json; print(json.load(sys.stdin)['command_key'])")
CK_B=$(echo "$FP_DIR_B" | python3 -c "import sys,json; print(json.load(sys.stdin)['command_key'])")
CK_OTHER=$(echo "$FP_OTHER" | python3 -c "import sys,json; print(json.load(sys.stdin)['command_key'])")

# --- Test 1: 同命令不同目录 → matching_key 不同，command_key 相同 ---
assert_eq "$((MK_A != MK_B ? 1 : 0))" "1" "B2-T1: different cwd → different matching_key"
assert_eq "$CK_A" "$CK_B" "B2-T1: same command → same command_key"

# --- Test 2: 不同命令 → command_key 不同 ---
assert_eq "$((CK_A != CK_OTHER ? 1 : 0))" "1" "B2-T2: different command → different command_key"

# --- Test 3: exact match 优先 ---
RTDIR=$(mktemp -d)
python3 -c "
import json, datetime
now = datetime.datetime.utcnow().isoformat() + 'Z'
records = [
    {'task_fingerprint': {'matching_key': '$MK_A', 'command_key': '$CK_A'},
     'command': 'npm test', 'error_class': 'missing_dependency',
     'stderr_summary': '', 'repair_classification': 'unknown',
     'avoidance_hints': [{'kind': 'set_env', 'vars': {'FROM': 'exact'}}],
     'recorded_at': now, 'asset_version': 2,
     'applied_count': 0, 'applied_fail_count': 0, 'stale': False, 'rejected_by': None, 'source': 'auto'}
]
json.dump({'schema_version': 2, 'records': records}, open('$RTDIR/failure-records.json', 'w'))
"
# 用 matching_key_A 查询（exact match）
RESULT=$(python3 "$SCRIPTS/polaris_failure_records.py" query --matching-key "$MK_A" --command-key "$CK_A" --store "$RTDIR/failure-records.json" 2>&1)
TIER=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('match_tier',''))")
assert_eq "$TIER" "exact" "B2-T3: same cwd → exact match"

# --- Test 4: command_only fallback ---
# 用 matching_key_B 查询（不同目录，但 command_key 相同）
RESULT=$(python3 "$SCRIPTS/polaris_failure_records.py" query --matching-key "$MK_B" --command-key "$CK_B" --store "$RTDIR/failure-records.json" 2>&1)
TIER=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('match_tier',''))")
DISCOUNT=$(echo "$RESULT" | python3 -c "import sys,json; h=json.load(sys.stdin).get('avoidance_hints',[]); print(h[0].get('confidence_discount',1.0) if h else 'none')")
assert_eq "$TIER" "command_only" "B2-T4: different cwd → command_only fallback"
assert_eq "$DISCOUNT" "0.6" "B2-T4: confidence discount must be 0.6"

# --- Test 5: 完全不同命令 → 无匹配 ---
MK_X=$(echo "$FP_OTHER" | python3 -c "import sys,json; print(json.load(sys.stdin)['matching_key'])")
RESULT=$(python3 "$SCRIPTS/polaris_failure_records.py" query --matching-key "$MK_X" --command-key "$CK_OTHER" --store "$RTDIR/failure-records.json" 2>&1)
HINT_COUNT=$(echo "$RESULT" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('avoidance_hints',[])))")
assert_eq "$HINT_COUNT" "0" "B2-T5: different command → no match"
rm -rf "$RTDIR"

echo "=== B2 Results: $PASS/$TOTAL passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
```

**Codex 审计要求**:
- `command_key` 不能包含 cwd 的任何信息（验证：不同 cwd 同命令的 command_key 必须相等）
- fallback 结果的 confidence_discount 必须在 query 返回值中显式标记，不能只在内部使用
- 旧的 failure_records（无 command_key 字段）必须能被正常 query（exact match 仍然工作，fallback 降级为不可用而非报错）

---

## Phase C — 预置经验 + 用户修正（2 天）

### C1: 预置经验包
**时间**: 1 天
**Gate**: `polaris run` 首次执行时自动加载生态经验包，可禁用、可回滚
**依赖**: A1（CLI 入口）, B1（schema v2 的 source 字段）
**交付件**:
- `Polaris/experience-packs/` 目录:
  - `node.json` — 常见 Node.js 失败模式
    - MODULE_NOT_FOUND → `set_env: {NODE_PATH: "./node_modules"}`
    - EACCES on npm install → `append_flags: ["--no-optional"]`
    - heap OOM → `set_env: {NODE_OPTIONS: "--max-old-space-size=4096"}`
    - ENOENT package.json → 提示 `rewrite_cwd` 到包含 package.json 的目录
    - 每条: `source: "prebuilt", pack_version: "1.0", ecosystem: "node"`
  - `python.json` — 常见 Python 失败模式
    - ModuleNotFoundError → `set_env: {PYTHONPATH: "."}`
    - venv not activated → `set_env: {VIRTUAL_ENV: ".venv", PATH: ".venv/bin:$PATH"}`
    - UnicodeDecodeError → `set_env: {PYTHONIOENCODING: "utf-8"}`
    - 每条: `source: "prebuilt", pack_version: "1.0", ecosystem: "python"`
  - `go.json` — 常见 Go 失败模式
    - go mod tidy 失败 → `append_flags: ["-v"]` + `set_env: {GOFLAGS: "-mod=mod"}`
    - CGO_ENABLED 问题 → `set_env: {CGO_ENABLED: "0"}`
    - 每条: `source: "prebuilt", pack_version: "1.0", ecosystem: "go"`
- 加载逻辑（在 `polaris_cli.py` 的 run 子命令中）:
  1. 检测命令中的关键词: `npm|node|npx|yarn|pnpm` → node, `python|pip|pytest|poetry` → python, `go ` → go
  2. 检查 failure-records.json 中是否已有该 ecosystem 的 prebuilt 记录
  3. 如无 → 加载对应 pack，merge 到 failure-records.json，标记 `source: "prebuilt"`
  4. 如已有 → 跳过（幂等）
- 禁用: `--no-prebuilt` 标志 或 `POLARIS_NO_PREBUILT=1`
- 回滚: `polaris experience reset-prebuilt [--ecosystem node|python|go]` 删除所有 `source=prebuilt` 的记录

**模拟回归脚本**: `regression-platform2-C1.sh`
```bash
#!/usr/bin/env bash
set -euo pipefail
PASS=0; FAIL=0; TOTAL=0
SCRIPTS=Polaris/scripts

assert_eq() { TOTAL=$((TOTAL+1)); if [ "$1" = "$2" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: expected='$2' got='$1' — $3"; fi; }
assert_contains() { TOTAL=$((TOTAL+1)); if echo "$1" | grep -qF "$2"; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: output missing '$2' — $3"; fi; }

# --- Test 1: npm 命令自动加载 node pack ---
RTDIR=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "npm test" --runtime-dir "$RTDIR" 2>&1 || true
PREBUILT_COUNT=$(python3 -c "
import json
r=json.load(open('$RTDIR/failure-records.json'))['records']
print(len([x for x in r if x.get('source')=='prebuilt' and x.get('ecosystem')=='node']))
")
assert_eq "$((PREBUILT_COUNT > 0 ? 1 : 0))" "1" "C1-T1: node prebuilt records loaded"
rm -rf "$RTDIR"

# --- Test 2: --no-prebuilt 禁止加载 ---
RTDIR=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "npm test" --no-prebuilt --runtime-dir "$RTDIR" 2>&1 || true
PREBUILT_COUNT=$(python3 -c "
import json
try:
    r=json.load(open('$RTDIR/failure-records.json'))['records']
    print(len([x for x in r if x.get('source')=='prebuilt']))
except: print(0)
")
assert_eq "$PREBUILT_COUNT" "0" "C1-T2: no prebuilt records with --no-prebuilt"
rm -rf "$RTDIR"

# --- Test 3: 幂等性 — 第二次运行不重复加载 ---
RTDIR=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "npm test" --runtime-dir "$RTDIR" 2>&1 || true
COUNT1=$(python3 -c "import json; print(len(json.load(open('$RTDIR/failure-records.json'))['records']))")
# 重新初始化 state 模拟第二次 run
python3 "$SCRIPTS/polaris_cli.py" run "npm test" --runtime-dir "$RTDIR" 2>&1 || true
COUNT2=$(python3 -c "import json; print(len(json.load(open('$RTDIR/failure-records.json'))['records']))")
assert_eq "$COUNT1" "$COUNT2" "C1-T3: prebuilt records not duplicated on second run"
rm -rf "$RTDIR"

# --- Test 4: reset-prebuilt 只删 prebuilt ---
RTDIR=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "npm test" --runtime-dir "$RTDIR" 2>&1 || true
# 手动加一条 auto 记录
python3 -c "
import json, datetime
d=json.load(open('$RTDIR/failure-records.json'))
d['records'].append({
    'task_fingerprint': {'matching_key': 'user-rec'},
    'command': 'user-cmd', 'error_class': 'unknown',
    'stderr_summary': '', 'repair_classification': 'unknown',
    'avoidance_hints': [], 'recorded_at': datetime.datetime.utcnow().isoformat()+'Z',
    'asset_version': 2, 'applied_count': 0, 'applied_fail_count': 0,
    'stale': False, 'rejected_by': None, 'source': 'auto'
})
json.dump(d, open('$RTDIR/failure-records.json', 'w'))
"
python3 "$SCRIPTS/polaris_cli.py" experience reset-prebuilt --runtime-dir "$RTDIR" 2>&1
REMAINING=$(python3 -c "
import json
r=json.load(open('$RTDIR/failure-records.json'))['records']
prebuilt=[x for x in r if x.get('source')=='prebuilt']
auto=[x for x in r if x.get('source')=='auto']
print(f'{len(prebuilt)},{len(auto)}')
")
assert_eq "$REMAINING" "0,1" "C1-T4: prebuilt deleted, auto preserved"
rm -rf "$RTDIR"

# --- Test 5: python 命令加载 python pack ---
RTDIR=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "python3 -m pytest" --runtime-dir "$RTDIR" 2>&1 || true
PREBUILT_ECO=$(python3 -c "
import json
r=json.load(open('$RTDIR/failure-records.json'))['records']
ecos=set(x.get('ecosystem','') for x in r if x.get('source')=='prebuilt')
print(','.join(sorted(ecos)))
")
assert_contains "$PREBUILT_ECO" "python" "C1-T5: python prebuilt loaded for pytest command"
rm -rf "$RTDIR"

# --- Test 6: go 命令加载 go pack ---
RTDIR=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "go test ./..." --runtime-dir "$RTDIR" 2>&1 || true
PREBUILT_ECO=$(python3 -c "
import json
r=json.load(open('$RTDIR/failure-records.json'))['records']
ecos=set(x.get('ecosystem','') for x in r if x.get('source')=='prebuilt')
print(','.join(sorted(ecos)))
")
assert_contains "$PREBUILT_ECO" "go" "C1-T6: go prebuilt loaded for go test command"
rm -rf "$RTDIR"

echo "=== C1 Results: $PASS/$TOTAL passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
```

**Codex 审计要求**:
- experience-pack JSON 必须符合 failure-records schema v2（不能是私有格式）
- 预置记录的 avoidance_hints 必须只使用已有的 4 种 hint primitives
- `ecosystem` 字段必须在 record 和 pack 中都有，不能只靠命令检测
- 幂等性是硬门：同一 pack 不能重复加载
- `reset-prebuilt` 不能触碰 source != "prebuilt" 的记录

---

### C2: 用户反馈修正
**时间**: 1 天
**Gate**: 用户可以 reject/correct 经验记录，修正后的优先级正确
**依赖**: B1（schema v2 的 stale/rejected_by/source 字段）
**交付件**:
- `polaris feedback reject <record_index> [--store path]` — 设置 `stale=true, rejected_by="user"`
- `polaris feedback correct <record_index> --hint-kind <kind> --hint-value <json> [--store path]` — 创建新记录:
  - 复制原记录的 task_fingerprint, command, error_class
  - 替换 avoidance_hints 为用户指定的 hint
  - 设置 `source: "user_correction", rejected_by: null, stale: false`
- `polaris feedback list [--store path]` — 列出所有 rejected 和 user_correction 记录
- query 优先级排序（同一 matching_key 下）:
  1. `source: "user_correction"` (最高)
  2. `source: "auto"` 且 `stale: false`
  3. `source: "prebuilt"` 且 `stale: false`
  4. 其余跳过

**模拟回归脚本**: `regression-platform2-C2.sh`
```bash
#!/usr/bin/env bash
set -euo pipefail
PASS=0; FAIL=0; TOTAL=0
SCRIPTS=Polaris/scripts

assert_eq() { TOTAL=$((TOTAL+1)); if [ "$1" = "$2" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: expected='$2' got='$1' — $3"; fi; }
assert_contains() { TOTAL=$((TOTAL+1)); if echo "$1" | grep -qF "$2"; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: output missing '$2' — $3"; fi; }

# --- 构造测试数据 ---
setup_store() {
    local DIR="$1"
    python3 -c "
import json, datetime
now = datetime.datetime.utcnow().isoformat() + 'Z'
records = [
    {'task_fingerprint': {'matching_key': 'fb-test', 'command_key': 'fb-cmd'},
     'command': 'npm test', 'error_class': 'missing_dependency',
     'stderr_summary': 'Cannot find module X',
     'repair_classification': 'unknown',
     'avoidance_hints': [{'kind': 'set_env', 'vars': {'BAD': 'hint'}}],
     'recorded_at': now, 'asset_version': 2,
     'applied_count': 2, 'applied_fail_count': 2, 'stale': False,
     'rejected_by': None, 'source': 'auto'},
    {'task_fingerprint': {'matching_key': 'fb-test', 'command_key': 'fb-cmd'},
     'command': 'npm test', 'error_class': 'missing_dependency',
     'stderr_summary': 'Cannot find module Y',
     'repair_classification': 'unknown',
     'avoidance_hints': [{'kind': 'set_env', 'vars': {'GOOD': 'hint'}}],
     'recorded_at': now, 'asset_version': 2,
     'applied_count': 1, 'applied_fail_count': 0, 'stale': False,
     'rejected_by': None, 'source': 'auto'}
]
json.dump({'schema_version': 2, 'records': records}, open('$DIR/failure-records.json', 'w'))
"
}

# --- Test 1: reject 标记生效 ---
RTDIR=$(mktemp -d)
setup_store "$RTDIR"
python3 "$SCRIPTS/polaris_cli.py" feedback reject 0 --store "$RTDIR/failure-records.json" 2>&1
REC=$(python3 -c "import json; r=json.load(open('$RTDIR/failure-records.json'))['records'][0]; print(r['stale'], r['rejected_by'])")
assert_eq "$REC" "True user" "C2-T1: record 0 must be stale + rejected_by=user"
rm -rf "$RTDIR"

# --- Test 2: reject 后 query 不返回该记录的 hints ---
RTDIR=$(mktemp -d)
setup_store "$RTDIR"
python3 "$SCRIPTS/polaris_cli.py" feedback reject 0 --store "$RTDIR/failure-records.json" 2>&1
RESULT=$(python3 "$SCRIPTS/polaris_failure_records.py" query --matching-key fb-test --store "$RTDIR/failure-records.json" 2>&1)
# 应该只有第二条记录的 hints
VARS=$(echo "$RESULT" | python3 -c "import sys,json; h=json.load(sys.stdin).get('avoidance_hints',[]); print(','.join(list(h[0].get('vars',{}).keys())) if h else 'none')")
assert_eq "$VARS" "GOOD" "C2-T2: only non-rejected hints returned"
rm -rf "$RTDIR"

# --- Test 3: correct 创建高优先级记录 ---
RTDIR=$(mktemp -d)
setup_store "$RTDIR"
python3 "$SCRIPTS/polaris_cli.py" feedback correct 0 \
    --hint-kind set_env --hint-value '{"CORRECT": "value"}' \
    --store "$RTDIR/failure-records.json" 2>&1
TOTAL_RECS=$(python3 -c "import json; print(len(json.load(open('$RTDIR/failure-records.json'))['records']))")
assert_eq "$TOTAL_RECS" "3" "C2-T3: correction creates new record (total 3)"
LAST_SRC=$(python3 -c "import json; print(json.load(open('$RTDIR/failure-records.json'))['records'][-1]['source'])")
assert_eq "$LAST_SRC" "user_correction" "C2-T3: new record source is user_correction"
rm -rf "$RTDIR"

# --- Test 4: user_correction 优先于 auto ---
RTDIR=$(mktemp -d)
setup_store "$RTDIR"
python3 "$SCRIPTS/polaris_cli.py" feedback correct 0 \
    --hint-kind set_env --hint-value '{"CORRECT": "value"}' \
    --store "$RTDIR/failure-records.json" 2>&1
RESULT=$(python3 "$SCRIPTS/polaris_failure_records.py" query --matching-key fb-test --store "$RTDIR/failure-records.json" 2>&1)
FIRST_VAR=$(echo "$RESULT" | python3 -c "
import sys,json
h=json.load(sys.stdin).get('avoidance_hints',[])
print(list(h[0].get('vars',{}).keys())[0] if h else 'none')
")
assert_eq "$FIRST_VAR" "CORRECT" "C2-T4: user_correction hints come first"
rm -rf "$RTDIR"

# --- Test 5: feedback list 显示修正记录 ---
RTDIR=$(mktemp -d)
setup_store "$RTDIR"
python3 "$SCRIPTS/polaris_cli.py" feedback reject 0 --store "$RTDIR/failure-records.json" 2>&1
python3 "$SCRIPTS/polaris_cli.py" feedback correct 0 \
    --hint-kind set_env --hint-value '{"FIX": "1"}' \
    --store "$RTDIR/failure-records.json" 2>&1
OUT=$(python3 "$SCRIPTS/polaris_cli.py" feedback list --store "$RTDIR/failure-records.json" 2>&1)
assert_contains "$OUT" "rejected" "C2-T5: list shows rejected record"
assert_contains "$OUT" "user_correction" "C2-T5: list shows correction record"
rm -rf "$RTDIR"

echo "=== C2 Results: $PASS/$TOTAL passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
```

**Codex 审计要求**:
- `reject` 是幂等的：对已 rejected 的记录再次 reject 不报错
- `correct` 创建的新记录必须保留原记录的 task_fingerprint（包括 matching_key 和 command_key）
- hint-kind 必须是 4 种合法 primitives 之一，否则拒绝并报错
- query 优先级排序是确定性的：user_correction > auto > prebuilt，不依赖记录写入顺序

---

## Phase D — 观测闭环（1 天）

### D1: adapter selection trace + outcome 记录
**时间**: 1 天
**Gate**: 每次 adapter 选择和执行结果可追溯，`polaris stats` 显示 adapter 维度统计
**依赖**: A1（CLI 入口）, A3（stats 基础）
**交付件**:
- event-log 新增事件类型:
  - `adapter_selected`: `{type, ts, adapter, score, rank_trace, scenario_fingerprint, cache_hit}`
  - `adapter_outcome`: `{type, ts, adapter, success, exit_code, duration_ms, error_class}`
- orchestrator 在 adapter 选择后 emit `adapter_selected`
- orchestrator 在执行完成后 emit `adapter_outcome`
- `polaris_stats.py` 扩展（`--section adapters` 或默认包含）:
```
Adapter Performance
===================
shell-command:  45 calls, 38 success (84.4%), avg 2.3s
file-analysis:  12 calls, 10 success (83.3%), avg 1.1s
Cache hit rate: 72.0% (out of 57 selections)
```
- 数据格式为 Platform 3 learned ranking 预留字段

**模拟回归脚本**: `regression-platform2-D1.sh`
```bash
#!/usr/bin/env bash
set -euo pipefail
PASS=0; FAIL=0; TOTAL=0
SCRIPTS=Polaris/scripts

assert_eq() { TOTAL=$((TOTAL+1)); if [ "$1" = "$2" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: expected='$2' got='$1' — $3"; fi; }
assert_contains() { TOTAL=$((TOTAL+1)); if echo "$1" | grep -qF "$2"; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL[$TOTAL]: output missing '$2' — $3"; fi; }

# --- Test 1: 执行后 event-log 包含 adapter 事件 ---
RTDIR=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "echo adapter-trace-test" --runtime-dir "$RTDIR" 2>&1 || true
HAS_SELECTED=$(python3 -c "
import json
events=[json.loads(l) for l in open('$RTDIR/event-log.jsonl') if l.strip()]
print(any(e.get('type')=='adapter_selected' for e in events))
")
HAS_OUTCOME=$(python3 -c "
import json
events=[json.loads(l) for l in open('$RTDIR/event-log.jsonl') if l.strip()]
print(any(e.get('type')=='adapter_outcome' for e in events))
")
assert_eq "$HAS_SELECTED" "True" "D1-T1: event-log must contain adapter_selected"
assert_eq "$HAS_OUTCOME" "True" "D1-T1: event-log must contain adapter_outcome"
rm -rf "$RTDIR"

# --- Test 2: adapter_selected 事件结构完整 ---
RTDIR=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "echo structure-test" --runtime-dir "$RTDIR" 2>&1 || true
FIELDS=$(python3 -c "
import json
events=[json.loads(l) for l in open('$RTDIR/event-log.jsonl') if l.strip()]
sel=[e for e in events if e.get('type')=='adapter_selected'][0]
required={'type','ts','adapter','score','scenario_fingerprint','cache_hit'}
print(required.issubset(set(sel.keys())))
")
assert_eq "$FIELDS" "True" "D1-T2: adapter_selected has all required fields"
rm -rf "$RTDIR"

# --- Test 3: adapter_outcome 事件包含 duration ---
RTDIR=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "sleep 0.1 && echo timing-test" --runtime-dir "$RTDIR" 2>&1 || true
DURATION=$(python3 -c "
import json
events=[json.loads(l) for l in open('$RTDIR/event-log.jsonl') if l.strip()]
out=[e for e in events if e.get('type')=='adapter_outcome']
print(out[0].get('duration_ms', -1) if out else -1)
")
assert_eq "$((DURATION > 0 ? 1 : 0))" "1" "D1-T3: duration_ms must be positive"
rm -rf "$RTDIR"

# --- Test 4: stats 显示 adapter 维度 ---
RTDIR=$(mktemp -d)
# 跑两次构造数据
python3 "$SCRIPTS/polaris_cli.py" run "echo stats-1" --runtime-dir "$RTDIR" 2>&1 || true
python3 "$SCRIPTS/polaris_cli.py" run "echo stats-2" --runtime-dir "$RTDIR" 2>&1 || true
OUT=$(python3 "$SCRIPTS/polaris_stats.py" --runtime-dir "$RTDIR" 2>&1)
assert_contains "$OUT" "Adapter Performance" "D1-T4: stats must show adapter section"
assert_contains "$OUT" "calls" "D1-T4: stats must show call counts"
assert_contains "$OUT" "success" "D1-T4: stats must show success rate"
rm -rf "$RTDIR"

# --- Test 5: 失败执行的 outcome 事件正确 ---
RTDIR=$(mktemp -d)
python3 "$SCRIPTS/polaris_cli.py" run "false" --runtime-dir "$RTDIR" 2>&1 || true
SUCCESS_FLAG=$(python3 -c "
import json
events=[json.loads(l) for l in open('$RTDIR/event-log.jsonl') if l.strip()]
out=[e for e in events if e.get('type')=='adapter_outcome']
print(out[0].get('success', True) if out else 'missing')
")
assert_eq "$SUCCESS_FLAG" "False" "D1-T5: failed command → success=false in outcome"
rm -rf "$RTDIR"

echo "=== D1 Results: $PASS/$TOTAL passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
```

**Codex 审计要求**:
- event-log 的 adapter 事件必须遵循现有 event-log 的 output_mode 规则：operator_summary 模式下不暴露 rank_trace
- duration_ms 必须是执行开始到结束的墙钟时间，不是 CPU 时间
- adapter_outcome 的 success 字段必须与 execution-state.json 的最终 status 一致
- stats 的计数必须与 event-log 中的事件数精确匹配

---

## 时间线总览

| Phase | 内容 | 天数 | 累计 | 硬依赖 |
|-------|------|------|------|--------|
| A | CLI 入口 + 可见化 + stats | 2 | 2 | 无 |
| B | TTL/降权 + fingerprint 分层 | 2 | 4 | A1 |
| C | 预置经验包 + 用户反馈 | 2 | 5-6 | A1, B1 |
| D | adapter 观测闭环 | 1 | 6-7 | A1, A3 |

**总计: 7 天激进预期，每个 Phase 独立可交付，每个 Gate 可被 Codex 独立审计。**

**全量回归**: `regression-platform2-all.sh` 顺序执行 A1→A2→A3→B1→B2→C1→C2→D1 全部回归脚本，任一 FAIL 即 exit 1。

---

## 审计协议

- 每个 Phase 完成后提交 Codex 审计
- 回归必须 exit 0（全部测试通过）
- Codex 可以 REJECT 并要求返工，不影响后续 Phase 启动（但 B/C/D 依赖 A1）
- adapter learned ranking（原 #8）不在 Platform 2 范围内，留作 Platform 3 在 D1 数据充足后启动
- 每个回归脚本必须可独立运行（自带 setup/teardown），不依赖其他脚本的副作用
- 所有 tempdir 在测试结束后清理，不留残留状态

---

## 禁止项（Canary）

- `polaris_cli.py` 不得绕过 orchestrator 直接操作 state 文件
- experience-pack 不得包含 4 种合法 hint primitives 之外的 hint kind
- `reset-prebuilt` 不得删除 source != "prebuilt" 的记录
- `feedback reject` 不得物理删除记录，只能标记 stale
- `command_key` 不得包含 cwd 信息
- schema 迁移不得丢失任何已有字段
