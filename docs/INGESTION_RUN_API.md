# Ingestion Run API

## 为什么需要

Source Registry API 解决“允许哪些来源被采集”。P2 Ingestion Run API 解决“什么时候执行一次采集、执行结果是什么、是否产生了事件 cluster”。两者分开后，来源配置、采集执行和后续 CrisisEvent 事件库不会被耦合在同一个接口里。

## API

### 触发运行

```http
POST /api/ingestion/run
Content-Type: application/json
```

请求示例：

```json
{
  "source_ids": ["example_rss"],
  "live_fetch": false,
  "max_items_override": 3,
  "dry_run": false
}
```

字段说明：

- `source_ids`：为空时使用 registry 中全部来源；填写后只运行指定来源；
- `live_fetch`：默认 `false`；只有显式为 `true` 才允许调用 RSS/article adapter；
- `max_items_override`：不能超过来源自身 `max_items`；
- `dry_run`：只返回将运行的 source 结果，不写入 run store。

### 查询运行列表

```http
GET /api/ingestion/runs?limit=20
```

`limit` 默认 20，最大 100。

### 查询运行详情

```http
GET /api/ingestion/runs/{run_id}
```

详情包含 source results、raw_count、deduped_count、cluster_count、clusters 和 `automatic_publish=false`。

## Run Storage

第一版使用独立 JSON 文件：

```text
data/ingestion_runs.runtime.json
```

可以通过 `INGESTION_RUN_STORE_PATH` 指向测试临时文件。文件不存在时从空列表开始，测试不会污染真实 data 目录。本阶段不引入 PostgreSQL，也不创建 CrisisEvent 表。

## 状态语义

Run 状态：

- `completed`：所有来源没有失败，`no_match` 也属于正常完成；
- `partial`：部分来源 `failed` 或 `skipped_by_robots`；
- `failed`：live fetch 下全部来源失败或请求不合法；
- `dry_run`：请求使用 `dry_run=true`，不会写入 store。

Source result 状态继续沿用 ingestion 层：

- `collected`：成功获取并匹配到条目；
- `no_match`：完成获取，但没有匹配关键词；
- `failed`：请求、解析或处理失败；
- `skipped_by_robots`：robots 检查禁止抓取；
- `disabled`：来源被禁用，或本次使用默认非联网模式。

`no_match` 不等于 `failed`。前者说明采集动作完成但没有匹配内容，后者说明采集过程本身没有成功。

## Live Fetch 安全边界

默认 `live_fetch=false` 时，API 不调用任何网络 adapter，即使 registry 中存在 `enabled=true` 的来源。该模式是安全的配置运行，不会伪装成真实采集结果；来源结果会记录为 `disabled`，原因是 `live_fetch_disabled`。

只有显式 `live_fetch=true` 才会调用现有 RSS/article adapter，并继续复用：

- source allowlist；
- HTTPS 校验；
- robots；
- timeout；
- rate limit；
- max_items。

普通 pytest 不使用 `live_fetch=true`，不访问外部网络，也不调用真实 LLM。`automatic_publish` 固定为 `false`，采集结果不会自动生成或发布声明。

## 与现有 pipeline 的关系

API 层只负责选择 source、调用现有 adapter 和 pipeline、保存 run summary。normalize、deduplicate、cluster 和 risk analyze 继续由现有 ingestion pipeline 负责。

```text
Source Registry
    -> Ingestion Run API
    -> RSS/article adapter
    -> normalize
    -> deduplicate
    -> cluster
    -> risk analyze
    -> run record
```

## 下一步：P3 CrisisEvent

当前 run 里的 `clusters` 仍然属于该次运行的结果，不是独立事件库。P3 将把稳定的 `ClusteredCrisisEvent` 持久化为可查询的 CrisisEvent，并增加事件详情、Agent 运行和 trace 关联。

## 面试讲解版

我在 Source Registry API 之后增加了 Ingestion Run API，但没有把它直接做成实时爬虫接口。它通过 `source_ids` 选择白名单来源，默认 `live_fetch=false`，只有显式开启才会调用已有 adapter，并保存每次运行的来源状态、原始条数、去重条数和 cluster 结果。`collected`、`no_match`、`failed` 和 `skipped_by_robots` 分开记录，避免把“没有匹配舆情”和“采集失败”混淆。当前 run 结果仍保存在 JSON 中，P3 再把 cluster 提升为独立 CrisisEvent 事件库。
