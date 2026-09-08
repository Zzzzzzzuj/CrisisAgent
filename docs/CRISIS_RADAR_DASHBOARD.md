# Crisis Radar Dashboard

## 目标

Crisis Radar 是 CrisisAgent 工作台的态势读模型。它从已经保存的
`CrisisEvent`、Ingestion Run 和 Event Agent Run 中汇总风险，而不是重新采集、
重新运行 Agent、调用 LLM 或发布声明。

它帮助企业人员先回答三个问题：当前哪些事件最紧急、哪些事件需要人工审核、
哪些白名单来源出现采集问题。

## Crisis Urgency Score

第一版使用可解释规则，分数限制在 0 到 100：

| 信号 | 分数 |
| --- | ---: |
| high / medium / low risk | +40 / +25 / +10 |
| conflicting / unverified fact | +25 / +15 |
| current / uncertain / historical event | +15 / +10 / -20 |
| source count >= 5 / >= 2 | +15 / +8 |
| human review required | +15 |
| waiting_human / failed / completed / archived | +10 / +10 / -10 / -30 |

分级为：`SEV-1` (>=80)、`SEV-2` (>=60)、`SEV-3` (>=35)、`SEV-4` (<35)。
归档事件仍保留历史分数，但不会进入 Top Urgent 或 Review Queue。

规则而非模型的原因是：第一版优先让业务人员看得懂每一个优先级原因；后续有足够
人工标注和处置结果后，才适合评估是否引入学习型排序。

## API

```text
GET /api/dashboard/overview
GET /api/dashboard/severity
GET /api/dashboard/trends
GET /api/dashboard/source-health
GET /api/dashboard/review-queue
```

`overview` 返回事件总数、SEV 分布、待审核数、事实状态统计和 Top Urgent。
`trends` 按事件 `created_at` 的日期聚合。`source-health` 根据已有
`source_results` 统计来源状态；`no_match` 表示本次没有匹配舆情，不计为采集失败。
`failed` 与 `skipped_by_robots` 会进入 failure rate，`disabled` 不进入尝试次数分母。

## 前端展示

Workbench 顶部展示指标卡、最高优先级事件、人工审核队列、来源健康和简单趋势条。
没有引入 ECharts 或其他图表依赖；趋势仅用于展示当前 MVP 的聚合结果。

## 安全边界

- `automatic_publish=false`；
- Dashboard 只读取现有记录，不触发 live-fetch；
- 不调用真实 LLM；
- 不改变 Agent Workflow、Legal RAG 或 Human Review policy；
- 当前 JSON store 适合本地 MVP，不等同于并发生产数据库。

## 面试讲解

> 我没有把 Dashboard 做成只展示漂亮图表，而是把事件风险、事实可信度、来源数量、
> 人工审核状态和 Agent 运行状态编码为可解释的 Crisis Urgency Score。这样运营人员
> 能先看到 SEV-1/2 事件和待审核队列；同时 source-health 会区分“没有匹配到舆情”与
> “采集失败”，避免把数据源故障误判为风险消失。第一版坚持规则评分和只读聚合，
> 不重新调用模型，也不自动发布声明。
