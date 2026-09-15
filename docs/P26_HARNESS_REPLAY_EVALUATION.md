# P26 Harness-aware Main Workflow Replay Evaluation

P26 新增独立的离线主流程重放评测。它在隔离的 `AgentState` 中使用固定 Replay Case、fake Agent/Tool 和现有 Evidence Quality Gate、Human Review Policy，按真实固定六步的依赖顺序执行，不写正式 checkpoint、session 或运行存储。

## 两种对比模式

- `golden`：沿用 P22.2 的 Golden Case Evaluation，只验证既有契约，不代表执行了主流程。
- `main_workflow_replay`：读取 baseline/candidate 的完整 HarnessSpec，在同一组固定 fixture 上重放六步编排，保存逐 Case 策略、Trace 摘要、failure tags 和审核决定。

调用 Harness Comparison 时传入 `mode: "main_workflow_replay"` 即可。两种模式单独记录，不能把 Golden Case 结果称为 Replay 结果。

## 覆盖范围

固定数据集覆盖低置信证据、证据冲突、上下文污染、工具超时/重试、审核触发和恢复快照标识。Replay 使用 `HarnessRuntimeContext` 固定 `harness_id`、版本和 `spec_hash`，不会在运行中重新查询 active Harness，也不会自动启用 Candidate。

报告保留任务完成率、Evidence Quality、工具失败率、人工审核触发率、`policy_decision_accuracy`、失败标签分布和每条 Case 的差异。人工审核率只是观察指标，不能单独作为优化目标；候选是否启用仍需 P22.2 的门槛和人工审批。

## 当前边界

Replay 证明的是离线策略生效和可重复性，不代表真实线上模型、真实新闻、真实数据库或生产 SLA。它不访问网络、LLM、Redis、PostgreSQL 或 BGE，不修改 Agent 顺序、Prompt 或 RAG 算法，也不属于自动自优化。

## 面试讲解版

我把 Golden Case 和主流程 Replay 分开：Golden Case 检查契约，Replay 则把 baseline 和 candidate 放到同一批固定 fixture 中，按真实六步依赖执行，并记录每个策略导致的行为变化。这样只有 Harness 真正影响 ToolRunner、Evidence Gate 或 Human Review 时，指标才会变化；评测结果只能作为人工审批依据，不能自动上线。
