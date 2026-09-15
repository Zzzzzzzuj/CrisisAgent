# P22.2 Harness Candidate

P22.2 为 HarnessSpec 增加受控候选版本流程。它不是自动优化器，而是让人工创建的候选配置在离线固定评测集上与 baseline 对比，门槛通过后再由人工审批和启用。

## 哪些字段真正生效

P21 中的 workflow、prompts、context_policy 以及 retrieval/review 的描述性字段主要用于版本快照。P22.2 只开放三类运行时策略覆盖：

- `skills_tools`：每工具 `timeout_ms`、`max_retries`，以及 `execution_budget` 的四个预算字段；ToolRunner 实际读取这些值。
- `retrieval_policy`：Evidence Gate 的分数、重排分数、污染率阈值，以及是否允许该 Gate 触发人工审核；Legal Agent 实际读取这些值。
- `review_policy`：`evidence_low_confidence`、`evidence_conflict`、`tool_timeout` 等触发开关；Human Review Policy 实际读取已配置的开关。

固定 Agent 顺序、Prompt 主语义和 RAG 检索算法不在可变范围内。每次运行仍保存完整 Harness 快照，Trace 只保存 `harness_id`、版本和 `spec_hash`。

## 生命周期

`DRAFT -> EVALUATED -> APPROVED / REJECTED -> ACTIVE -> ROLLED_BACK`

候选通过 P21 copy API 创建，修改时只提交允许字段，并保存 `parent_version`、`change_summary`、`changed_fields`。评测保存 comparison 和 gate result；审批记录 comparison、审批人、时间、原因和门槛结果。未到 `APPROVED` 的版本不能通过 API 启用。回滚保留历史版本，不删除旧快照。

## 离线门槛

Candidate 必须同时满足：任务完成率不低于 baseline、Evidence Quality 不下降、严重 failure tag 数量不增加、工具失败率不增加。Human Review 触发率只作为观察指标，不以“审核更少”为优化目标。

当前 comparison 复用 Eval Center 的离线 Golden Cases，不调用 LLM、网络或外部存储；完整 Replay Runner 尚未实现。因此指标相同是有效结果，不能包装成候选改进。门槛结果会进入 JSON comparison 和 Harness metadata，供人工决定是否 approve。

## API 形态

- `PATCH /api/harnesses/{harness_id}/{version}/candidate`：修改允许的候选字段。
- `POST /api/harnesses/{harness_id}/{version}/evaluate`：以指定 baseline 离线评测并生成门槛结果。
- `POST /api/harnesses/{harness_id}/{version}/approve`：人工审批通过的 comparison。
- `POST /api/harnesses/{harness_id}/{version}/reject`：记录拒绝原因。
- 原有 `enable` 仍保留，但只有 `APPROVED` 候选能通过 API 启用。

## 面试讲法

我没有把 Harness 做成自动改配置的 Meta-Agent，而是先做版本化和人工审批。候选只允许调整工具预算、证据阈值和审核触发规则；先在同一批离线 Case 上和 baseline 对比，完成率、证据质量、严重失败和工具失败率都不能变差，之后由人工审批才可启用。这样把“改策略”变成可回滚、可审计、可解释的工程流程。
