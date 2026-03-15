# Claude Self-Assessment of Polaris Platform 0

Date: 2026-03-15

Verbatim archive follows.

---
自审报告：Polaris Skill Platform-0 真实水平评估

一、Polaris 到底是什么

7094 行代码，20 个 Python/Shell 脚本。核心身份是一个本地任务编排状态机，不是执行器，不是 AI agent，不是 ML 系统。它做的事情是：

1. 把一个多步骤本地任务拆成 planning → ready → executing → validating → completed 的显式状态机
2. 每一步的决策（选哪个 adapter、用哪条 rule、走哪个修复路径）都落盘为 JSON
3. 失败时做有限诊断（stderr 分类 + 探针树），而不是无限重试
4. 成功时捕获模式（sequence + confidence + lifecycle），下次跑同类任务时复用

二、必须诚实承认的结构性事实

实际执行层极薄。 全部 7094 行里：

| 层 | 行数 | 占比 |
| --- | ---: | ---: |
| 编排 + 状态机 | ~2350 | 33% |
| 存储（patterns/rules/adapters） | ~1130 | 16% |
| 测试 + 兼容性 | ~1700 | 24% |
| 基础设施（bootstrap/report/compat） | ~700 | 10% |
| 真正执行用户任务的代码 | ~250 | 3% |

`polaris_task_runner.py` 是 mock 执行器，写假 JSON、注入模拟错误。`polaris_file_analysis.py`（46 行）和 `polaris_file_transform.py`（29 行）是唯二做真实工作的脚本。也就是说：97% 的代码在管理一个 3% 代码量的执行层。

"学习"不是机器学习。success patterns 是启发式记账，"上次这个组合成功了，confidence 从 70 涨到 74"。没有特征提取、没有模型、没有泛化。是 labeled examples + 手写晋升规则。

计划不是任务特定的。`polaris_planner.py` 对所有 goal 生成几乎相同的 4-5 步模板（planning → ready → executing → validating → completed）。goal 参数只影响 deep profile 下是否多加一个 architecture step。plan 不会根据"部署数据库"和"分析文件"产生不同的步骤。

修复是探针，不是修复。`polaris_repair_actions.py` 生成 `ls`、`which`、`python -c "import X"` 这类诊断命令。它收集证据，但不执行修复。设计上就是 probe-only。

三、与市面工具的坦诚对比

维度: 任务编排  
Polaris: 显式状态机 + JSON 落盘 + 分支/恢复  
市面工具: Airflow/Prefect/Temporal: 生产级 DAG 调度  
评价: Polaris 在"单机 CLI 编排"这个细分位上设计干净，但缺乏 DAG 并行、依赖解析、分布式调度。不在同一重量级。

维度: 失败恢复  
Polaris: 分类 stderr → 有限探针 → hard/soft 规则路由  
市面工具: Temporal: 自动重试 + 超时 + 补偿逻辑；Kubernetes Job: backoff + resource limits  
评价: Polaris 的显式分类（"这个错不能重试" vs "这个错可以探针后重试"）比 Temporal 的盲重试更有语义。这是 Polaris 真正的差异化点。

维度: Agent 框架  
Polaris: 不是 agent，是状态机编排  
市面工具: LangChain/CrewAI/AutoGen: LLM-in-the-loop agent  
评价: Polaris 没有 LLM 调用、没有 tool use、没有 reasoning loop。不是同一品类。

维度: 经验复用  
Polaris: confidence-scored patterns + 三层 rules  
市面工具: 无直接对标物；最近的是 MLflow experiment tracking  
评价: 概念有意思但数据量小（单机累积几十条）。价值在多次重复同一任务时才显现。

维度: 兼容性工程  
Polaris: v5↔v6 双向状态迁移 + 幂等 bootstrap + asset versioning  
市面工具: 大多数开源工具：schema migration via Alembic/Flyway  
评价: Platform-0 做的兼容性工程相对于项目规模而言是过度的，7000 行的工具拥有了企业级数据库才需要的 schema migration 纪律。但如果这个工具要长期演进，这个投资是正确的。

维度: 测试覆盖  
Polaris: 40+ 场景、1358 行回归脚本  
市面工具: 行业标准  
评价: 测试与代码比约 1:5。覆盖率高。这是 Polaris 的强项之一。

四、在我最高认知水平里的判断

Polaris 的真实定位：它是一个设计过度但执行不足的编排框架原型。

过度设计的地方：

- 7000 行管理 250 行的真实执行层
- 三层 rule store + lifecycle 晋升系统，为一个单机 CLI 工具
- 完整的 v5↔v6 schema migration，为一个没有外部用户的内部工具
- adapter selection + ranking + sticky cache + fallback + trust level，为 5 个预注册 adapter

不足的地方：

- 没有真实的任务执行能力，runner 是 mock，file_transform 只能追加一行文本
- 计划器是模板，不根据任务语义变化
- 修复不执行修复
- 没有外部集成（没有 API、没有 webhook、没有消息队列）
- 没有并行执行能力
- 没有 LLM-in-the-loop（作为 skill 被调用，但自身不调用 LLM）

但真正有价值的核心洞见是：

1. 显式失败分类 > 盲重试。"这个错误是 permission denial，不应该重试" 这个判断比 "重试 3 次然后放弃" 有本质区别。市面上几乎所有编排工具都在盲重试。
2. 状态机 > 隐式循环。每一步决策落盘，任何时候可以从 JSON 恢复。这个设计原则比大多数 agent 框架的 "内存中跑完" 更稳健。
3. hard/soft/experimental 三层规则是一个好的抽象。把 "绝不重试" 和 "通常可以修" 分开存、分开选，避免启发式规则互相覆盖。

五、结论

如果拿 Polaris 去和 Airflow/Temporal/LangChain 比，它什么都不是。  
不在同一重量级，不在同一品类，也不该这样比。

如果把 Polaris 看成一个"AI skill 应该如何管理自己的多步执行"的设计实验，它有三个洞见值得认真对待（失败分类、显式状态机、三层规则），但离产品化差了两个数量级，执行层需要从 mock 变成真实能力，计划器需要从模板变成任务感知，经验系统需要从记账变成真正的泛化。

Platform-0 做的事情本质上是对的，在没有稳固的 schema 和兼容性合约之前就扩展能力，结果是每次重构都破坏之前的状态。但 Platform-0 的投资回报只有在 Polaris 真正成长到需要跨版本升级的时候才能兑现。现在它更像是"为一栋还没盖起来的楼打了一个很好的地基"。

地基的工程质量是高的。楼还没开始盖。
