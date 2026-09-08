# Source Registry API

## 为什么需要

此前白名单舆情源主要通过 JSON 文件维护。P1 增加一个最小后端 API，让系统可以在不修改代码的情况下新增、查看和启停 RSS 或单篇文章来源，为后续 Ingestion Run API 做准备。

本阶段只管理来源配置，不执行真实采集。

## 存储与关系

API 使用独立的 JSON runtime storage：

```text
data/source_registry.runtime.json
```

文件不存在时从空列表开始。它不会覆盖 `data/source_registry.example.json`，也不使用不应提交的 `data/source_registry.local.json`。测试通过 `SOURCE_REGISTRY_RUNTIME_PATH` 指向临时文件。

## 支持的 source type

当前只支持：

- `rss`：白名单 RSS feed；
- `article_url`：白名单单篇文章 URL。

不支持任意域名递归、不支持站内深度爬取，也不支持通过 API 开启 live-fetch。

## API

### 查询来源

```http
GET /api/sources
```

### 新增来源

```http
POST /api/sources
Content-Type: application/json
```

示例：

```json
{
  "source_id": "example_rss",
  "source_name": "Example RSS",
  "source_type": "rss",
  "url": "https://example.com/rss.xml",
  "enabled": false,
  "company_keywords": ["示例公司"],
  "risk_keywords": ["投诉", "监管"],
  "respect_robots": true,
  "rate_limit_seconds": 3,
  "timeout_seconds": 10,
  "max_items": 3
}
```

### 修改来源

```http
PATCH /api/sources/{source_id}
```

第一版允许修改名称、启用状态、关键词、robots、限速、超时和最大条数，不允许修改 `url` 或 `source_type`。如果来源地址或类型需要改变，应创建新的 source。

### 配置测试

```http
POST /api/sources/{source_id}/test
```

该接口只检查：来源是否存在、类型、HTTPS、关键词和数值配置。返回 `config_valid` 或 `config_invalid`，并明确 `live_fetch_triggered=false`。它不会访问 RSS，也不会抓取文章。

## 安全校验

- `source_id` 不能重复；
- `source_type` 只能是 `rss` 或 `article_url`；
- URL 必须是 HTTPS；
- `company_keywords` 和 `risk_keywords` 不能同时为空；
- `rate_limit_seconds >= 0`；
- `timeout_seconds > 0`；
- `max_items > 0`；
- `enabled` 默认是 `false`。

默认关闭 live source 是为了避免“注册来源”被误解成“立即联网采集”。真实抓取仍然需要已有脚本的显式 `--live-fetch`，未来再由 P2 Ingestion Run API 以显式任务参数控制。

## 当前边界与下一步

P1 只解决 Source Registry 的配置管理，不记录采集运行状态，也不保存 CrisisEvent。下一步 P2 才会增加：

```text
POST /api/ingestion/run
GET  /api/ingestion/runs
GET  /api/ingestion/runs/{run_id}
```

P2 需要继续区分 `collected`、`no_match`、`failed`、`skipped_by_robots` 和 `disabled`，并把结果送入现有 normalize、deduplicate、cluster 和 Human Review 流程。

## 面试讲解版

我先没有把真实采集直接塞进 API，而是先做 Source Registry API。它只负责管理白名单来源和采集约束，例如 HTTPS、robots、timeout、rate limit 和 max_items，默认 `enabled=false`。配置测试接口也只做本地校验，不联网。这样先把数据源治理边界建立起来，再在 P2 中增加可追踪的 ingestion run，避免一个 API 同时承担配置、联网、事件入库和 Agent 执行，降低误采集和不可审计的风险。
