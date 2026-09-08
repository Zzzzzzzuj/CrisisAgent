# CrisisEvent API

## 为什么需要事件库

Ingestion Run 记录一次采集执行，里面的 cluster 是这次运行产生的结果。它还不是一个可以长期查询、修改状态和关联后续 Agent 处理的业务对象。CrisisEvent 事件库把 cluster 提升为稳定的危机事件，作为后续 Agent 运行、Human Review 和报告查询的入口。

当前 P3 只做事件保存和管理，不重新采集、不调用 Agent、不调用 LLM，也不自动发布。

## 存储

第一版使用独立 JSON storage：

```text
data/crisis_events.runtime.json
```

可通过 `CRISIS_EVENT_STORE_PATH` 指向测试临时文件。文件不存在时从空列表开始，不使用 PostgreSQL，也不会修改 ingestion run storage。

## 从 Ingestion Run 创建事件

```http
POST /api/events/from-ingestion-run
Content-Type: application/json
```

请求：

```json
{
  "run_id": "run-uuid",
  "cluster_id": "cluster-uuid",
  "title": "可选的事件标题",
  "event_summary": "可选的事件摘要"
}
```

接口会从已保存的 run cluster 复制公司、风险等级、公众情绪、事实状态、事件状态、来源、时间范围和 fingerprint。P3 不重新运行 ingestion pipeline。

如果相同的 `run_id + cluster_id` 已经创建过事件，接口返回已有事件，并返回：

```json
{
  "created": false
}
```

这保证了重复点击或重复请求不会产生重复 CrisisEvent。

## 查询和管理

```http
GET   /api/events?status=new&risk_level=high&limit=20
GET   /api/events/{event_id}
PATCH /api/events/{event_id}
POST  /api/events/{event_id}/archive
```

PATCH 第一版只允许修改：

- `title`；
- `event_summary`；
- `status`。

当前支持的 status：

- `new`：刚从 ingestion cluster 创建；
- `ready_for_agent`：后续可以交给 Agent 运行；
- `archived`：不再作为当前工作事件展示。

未来可以扩展 `running`、`waiting_human`、`completed` 和 `rejected`，但本阶段不启动 Agent，因此不会生成这些运行状态。

## 主要字段

事件详情保留：

- `event_id`、`cluster_id`、`source_run_id`；
- `title`、`event_summary`、`company`；
- `risk_level`、`public_emotion`、`fact_status`、`event_status`；
- `human_review_required`；
- `source_count`、`source_items`；
- `first_published_at`、`last_published_at`；
- `event_fingerprint`；
- `created_at`、`updated_at`。

这样可以追溯事件来自哪次采集、哪个 cluster，以及为什么需要人工审核。

## 当前边界与下一步

P3 只建立 CrisisEvent 事件库，不做：

- 重新采集；
- 自动合并不同 run 的事件；
- Agent 运行；
- Trace 查询；
- Human Review 执行；
- 报告导出；
- 自动发布。

下一阶段可以增加：

```text
POST /api/events/{event_id}/run
GET  /api/events/{event_id}/trace
GET  /api/events/{event_id}/review
```

届时事件才会关联 CrisisAgent session、Agent trace、RAG evidence 和 Human Review 状态。

## 面试讲解版

我把 ingestion run 和 CrisisEvent 分成两个层次：run 表示一次采集执行，cluster 表示这次执行发现的一组相关舆情；CrisisEvent 则是可以长期管理的业务事件。P3 只允许从已保存的 run cluster 创建事件，通过 `run_id + cluster_id` 做幂等，避免重复创建。当前事件库只负责保存来源、风险和事实状态，下一阶段才会把事件交给 Agent，并关联 trace 和 Human Review。
