# P25 Harness Runtime Integration

P25 将已启用的 HarnessSpec 接入 CrisisAgent 的真实运行路径。它不是自动优化器，也不改变固定 Agent 顺序、Prompt 主语义或 RAG 核心算法。

## 生效范围

新 Run 启动时，Dynamic Runtime 只允许选择 `active` HarnessSpec；默认仍使用 `crisisagent-default@1.0.0`。`APPROVED`、`EVALUATED` 或 `DRAFT` 版本不能直接进入新 Run。

Executor 在执行开始时根据 `AgentState.metadata["harness_spec"]` 创建不可变的 `HarnessRuntimeContext`。Context 保存完整快照，同时向 Trace 提供 `harness_id`、`harness_version`、`spec_hash` 和非敏感策略摘要。

## 真实读取路径

- Legal Agent 从本次 payload 的 Harness 快照读取 `min_score`、`min_rerank_score`、`max_context_pollution_rate` 和 Evidence Gate 人工审核开关。
- Human Review Policy 从同一份 AgentState 快照读取 `review_policy.triggers`。
- ToolRunner 已支持从 Harness 快照读取工具超时、重试和 execution budget；当前 ToolRunner 仍主要用于实验/工具路径，固定六 Agent 主链路没有凭空增加工具调用。
- Checkpoint、AgentRun 和 Report 延续保存完整 `harness_spec` 快照；Trace 只保存短引用和策略摘要。

## 运行一致性

运行开始后，Executor、Agent adapter 和策略判断都不重新查询当前 active Harness。即使随后启用了另一个版本，已创建的 State/Checkpoint 仍使用原快照，resume 也继续使用该快照。

## 默认兼容

未传 `harness_id` / `harness_version` 时仍解析默认 `crisisagent-default@1.0.0`。固定 `/api/crisis/run` 的请求和原有 trace 字段保持兼容；Dynamic Runtime 的 Harness 引用沿用现有 `execution_trace[*].harness` 结构。

## 当前边界

当前真实主流程已经接入 Harness 选择、快照、Legal Evidence Gate 和 Human Review trigger。完整 ToolRunner 多步调用尚未接入固定 Executor，因为主链路当前没有将工具调用改造成新的 Agent 节点。Golden Case Comparison 仍是离线评测；完整 Replay Runner 和自动配置优化仍未完成。

## 面试讲解版

我把 HarnessSpec 从“记录配置”推进到“运行时策略来源”。新任务只接受 active 版本，Executor 在开始时冻结一份 HarnessRuntimeContext，Legal RAG 和 Human Review 都从这份快照读取策略。后续即使切换 active 版本，已经启动的任务和 resume 仍不会被影响；Trace 记录版本和 hash，Run、Checkpoint、Report 保存完整快照。这样保证了实验配置可追溯、可回滚，同时没有破坏原有 Agent 流程。
