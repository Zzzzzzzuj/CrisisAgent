# CrisisEvent Agent Run API

## 1. 目标

P3 将 ingestion cluster 沉淀为 `CrisisEvent`。P4 在不改变原有 `/api/dynamic/run` 语义的前提下，增加事件级入口，让用户可以从事件运行 CrisisAgent，并查询该事件的 Agent Run、Trace 和 Human Review 状态。

## 2. API

```http
POST /api/events/{event_id}/run
GET  /api/events/{event_id}/run
GET  /api/events/{event_id}/trace
GET  /api/events/{event_id}/review
```

运行请求默认是离线 mock：

```json
{
  "mode": "mock",
  "runtime_mode": "sync",
  "force_rerun": false
}
```

同一事件已有 Agent Run 时，默认返回最近一次运行；只有显式 `force_rerun=true` 才会重新运行。已归档事件不能运行 Agent。

## 3. Runtime 复用方式

事件路由只负责读取事件、拼接 event 文本、注入 metadata 和保存运行摘要，实际执行复用现有：

```text
CrisisEvent
  -> run_dynamic_sync_with_metadata
  -> Planner / Executor / AgentState
  -> Sentiment / Writer / RedTeam / Legal / WriterV2 / Decision
  -> Evaluation / Human Review Policy
  -> Checkpoint
```

事件中的 `source_items`、`source_count`、`risk_level`、`fact_status`、`event_status`、`human_review_required` 和 `event_fingerprint` 会写入 `AgentState.metadata["ingestion"]`，因此既有 ingestion trigger 仍然可以触发 Human Review。

## 4. Trace 与 Review

Trace 查询返回 Agent 顺序、每个 Agent 的 trace、RAG metadata、evaluation、ingestion metadata 和 policy triggers。Review 查询返回当前运行状态、是否需要人工审核、触发原因和允许动作。

如果事件本身是高风险、事实未确认、事件状态不确定或运行过程中触发其他策略，事件会被标记为 `waiting_human`。`automatic_publish` 始终为 `false`，本阶段不提供自动发布能力。

## 5. 当前边界

- 默认 `mode=mock`，普通测试不调用真实 LLM；
- P4 只支持同步运行，不新增队列；
- 不重新采集网络数据；
- 不修改 `/api/crisis/run` 和 `/api/dynamic/run`；
- 不修改 Agent 顺序、Prompt 或 RAG 算法；
- AgentRun 使用 JSON storage，路径由 `EVENT_AGENT_RUN_STORE_PATH` 配置；
- 报告导出留到后续阶段。

## 6. 面试讲解版

我没有把事件级入口重新实现一套 Agent，而是把 CrisisEvent 转换成现有 Dynamic Runtime 能理解的 event 文本，并把采集来源和事实状态放进 `AgentState.metadata["ingestion"]`。这样既复用了原有 Planner、Executor、Trace 和 Human Review Policy，又保持 `/api/dynamic/run` 的兼容性。事件运行记录单独保存 `agent_run_id` 和 `session_id`，方便后续按事件查询 Trace、审核状态和导出报告。
