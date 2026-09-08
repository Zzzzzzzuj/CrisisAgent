# CrisisEvent Report API

## 1. 目标

P5 为已有 `CrisisEvent` 和 `AgentRun` 增加危机处理报告导出。报告只读取已经保存的事件和最近一次 AgentRun，不重新运行 Agent、不重新检索 RAG，也不访问网络。

## 2. API

```http
GET /api/events/{event_id}/report
GET /api/events/{event_id}/report?format=json
GET /api/events/{event_id}/report?format=markdown
```

默认返回 JSON 结构。Markdown 以稳定的 JSON envelope 返回：

```json
{
  "format": "markdown",
  "event_id": "...",
  "markdown_content": "# CrisisAgent 危机处理报告...",
  "automatic_publish": false
}
```

事件不存在返回 404；事件尚未有 AgentRun 返回 400，并提示先运行 CrisisAgent。

## 3. 报告内容

报告分为：

- 事件概览；
- 舆情来源和时间范围；
- 风险与事实状态；
- AgentRun 摘要、评分和声明草稿预览；
- Agent 顺序和 output 摘要；
- Legal RAG evidence 摘要；
- RedTeam issues；
- Human Review 状态和 policy triggers；
- 安全边界。

报告中的声明明确标记为“最终声明草稿”，不表示已经发布。`automatic_publish` 始终为 `false`。

## 4. 摘要提取

报告生成器只读取 `AgentRun.trace`、`AgentRun.metadata`、`AgentRun.evaluation` 和已保存的事件字段：

- Legal RAG 从 Legal trace 的 `rag` metadata 提取；
- RedTeam 从 Agent output 的 `issues` 提取；
- Human Review 从 AgentRun 的 `human_review_required` 和 `policy_triggers` 提取；
- 缺少 RAG 或 RedTeam 字段时返回 `not_available` 或空列表，不让报告接口失败。

## 5. 当前边界

- 不生成 PDF；
- 不重新运行 Agent；
- 不重新采集、不访问网络；
- 不调用真实 LLM；
- 不自动发布声明；
- 当前报告使用本地 JSON Storage；
- 前端 Report 页面留到后续阶段。

## 6. 面试讲解版

报告导出不是再次执行 Agent，而是把已经保存的 CrisisEvent、AgentRun、Trace、Evaluation 和 Human Review 信息组织成可读结果。这样可以保证报告是对既有执行结果的审计视图，不会因为重复生成导致结果变化，也不会绕过人工审核或自动发布边界。
