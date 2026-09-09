# Sentiment Ingestion

> 受控连接器现可扩展到 RSS、单篇 article URL、GDELT DOC 和 NewsAPI；真实请求仍需显式 live-fetch 开关。详见 [Live News Ingestion](LIVE_NEWS_INGESTION.md)。

## Why this layer exists

The original CrisisAgent entry points accept one manually written `event` string. Real enterprise input is more likely to contain multiple news items, forum posts, or media reports with duplicated, incomplete, or conflicting descriptions. The ingestion layer turns those source items into one event-level object before the existing CrisisAgent workflow runs.

## Phase 1 data flow

```text
Local JSON/CSV
  -> normalize
  -> deterministic deduplicate
  -> explainable event cluster
  -> risk and sentiment analysis
  -> ClusteredCrisisEvent
  -> CrisisAgent event text
  -> existing Workflow / Dynamic Runtime
```

This phase intentionally does not crawl websites, call RSS URLs, call a real LLM, or publish a statement.

## Event and fact status

`event_status` distinguishes `current`, `historical`, and `uncertain`. Historical material is not treated as a current incident. Ambiguous timing is marked `uncertain`.

`fact_status` distinguishes `verified`, `unverified`, and `conflicting`. The generated event text uses cautious language such as “据来源显示”“尚待核实” or “多来源存在不一致”; it does not turn an allegation into a confirmed fact.

High-risk, unverified, conflicting, or uncertain events are marked `human_review_required=true`. This is an upstream signal; it does not automatically publish any statement.

## Running the demo

From the repository root:

```powershell
python scripts/run_sentiment_ingestion_demo.py
```

The default command only prints ingestion results. It reads `data/sentiment_ingestion_fixture.json` and does not require LLM, PostgreSQL, Redis, BGE, or RSS access.

To run the first high-risk cluster through the existing mock Dynamic Runtime:

```powershell
python scripts/run_sentiment_ingestion_demo.py --run-workflow
```

The script forces `AGENT_MODE=mock`, `RUNTIME_MODE=sync`, and `CHECKPOINT_STORAGE=json` for this opt-in local verification. It prints the session id, final statement preview, scores, successful agent trace, review requirement, and final runtime status.

The output distinguishes `cluster_human_review_required` from `runtime_policy_required`. In this minimal phase, the existing API still receives only the converted `event` string, so the ingestion object's review flag is preserved as explanatory text rather than added as a new Runtime/API field. This keeps the existing contract unchanged; it also means the demo is an execution compatibility check, not a claim that the current Runtime consumes every ingestion metadata field as a policy trigger.

## Metadata Bridge 与 Human Review

The internal metadata bridge is the next step after the event-string compatibility check. An internal caller can pass the converted event together with:

```python
run_dynamic_sync_with_metadata(
    event_text,
    metadata={"ingestion": clustered_event.to_dict()},
)
```

The bridge stores the structured object under `AgentState.metadata["ingestion"]`. It preserves `source_items`, `source_count`, `event_status`, `fact_status`, `event_fingerprint`, `risk_level`, and `human_review_required`. JSON and PostgreSQL checkpoint repositories already serialize AgentState metadata, so the information survives checkpoint loading and resume.

`evaluate_human_policy` reads this namespace through independent ingestion triggers. High risk, an unverified or conflicting fact status, an uncertain event status, and an explicit `human_review_required` flag produce traceable reasons such as `ingestion_fact_conflicting` or `ingestion_review_required`. This is separate from the existing `high_risk`, RAG evidence, guardrail, evaluation, and LLM fallback checks.

The distinction matters: `cluster_human_review_required` is the ingestion-layer decision, while `runtime_policy_required` is the final Dynamic Runtime policy decision. The first phase only preserved the former in event text. The metadata bridge lets an internal caller pass the structured decision directly without changing `/api/crisis/run` or `/api/dynamic/run`.

No real RSS or crawler is connected yet. A later phase may expose a separate `/api/ingestion/run`, but the internal bridge is intentionally validated first to keep the current API and frontend stable.

## 第一版白名单真实采集

项目现在提供一个默认关闭的、小范围 live ingestion 入口。它只读取 `data/source_registry.example.json` 这类显式注册的 RSS 或单篇文章 URL；示例 source 全部 `enabled=false`，未明确启用时不会发起网络请求。

采集边界包括：只允许 HTTPS 和白名单 URL、检查 robots.txt、使用低频率和超时限制、限制最大条数，不登录、不处理验证码、不使用代理池、不递归抓取、不读取个人隐私或授权内容。真实文章默认标记为 `unverified`，不会自动发布声明。

`FetchResult` 会区分 `collected`、`no_match`、`failed`、`skipped_by_robots` 和 `disabled`。其中 `no_match` 表示请求成功但没有匹配公司或风险关键词，`failed` 表示网络或解析失败，不能把采集失败误判成“没有舆情”。

RSS adapter 优先使用可选 `feedparser`，未安装时可用受限 XML fallback 运行离线测试；article adapter 优先使用可选 `trafilatura`，否则使用受限 HTML fallback。普通 pytest 只使用本地 sample，不访问真实网站。

手动 live demo 必须显式开启：

```powershell
python scripts/run_live_ingestion_demo.py --source-registry data/source_registry.example.json
python scripts/run_live_ingestion_demo.py --live-fetch --source-registry data/source_registry.example.json
```

没有 `--live-fetch` 时脚本只提示，不执行网络访问。即使传入该参数，也只会尝试 registry 中 `enabled=true` 的 source。默认 demo、普通测试和现有 Agent workflow 仍然是离线路径。

### 面试讲解版

我没有把项目做成全网爬虫，而是先实现白名单、低频、可测试的真实采集入口。RSS 或单篇文章先经过 registry、robots 和请求限制，再统一转换成现有 `RawSentimentItem`，复用原来的 normalize、deduplicate、cluster 和 risk analyze。采集失败和没有匹配内容使用不同状态；未经证实或来源冲突的信息继续进入 Human Review。第一阶段只验证受控采集和现有 pipeline 的兼容，不声称实时全网监控或已接入企业生产数据。

## Interview explanation

I did not send raw web content directly to an LLM. I first normalized source text, removed duplicates, clustered related reports into an event, and preserved current/historical/uncertain and verified/unverified/conflicting status. The resulting event text is then passed into the existing CrisisAgent runtime. This adds a realistic upstream input boundary without changing the existing Agent order, RAG logic, Prompt semantics, or API contract. Phase 1 uses offline fixtures; real RSS or platform ingestion would require separate source permissions, rate limiting, retry, idempotency, and privacy controls.
