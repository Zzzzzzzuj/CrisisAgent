# Live Monitoring

P18 adds a small Watchlist-driven monitoring layer. A user registers a company, brand, product, or organization with aliases and risk terms; the system builds bounded queries for configured GDELT DOC, NewsAPI, or RSS providers.

## Flow

```text
Watchlist -> Query Builder -> configured provider adapter -> Public Signal
          -> existing ingestion normalization/cluster -> optional CrisisEvent
          -> Alert / reviewed CrisisAgent run
```

This is near-real-time monitoring, not unlimited web crawling. It does not recursively discover URLs, bypass robots, use login sessions, collect cookies or personal data, or publish a statement automatically.

Watchlists are stored in `data/watchlists.runtime.json` and disabled by default. Query construction is deterministic and does not call an LLM. Provider URLs still come from the existing allowlisted Source Registry.

`POST /api/live-monitor/run` supports bounded entity/provider selection, a lookback window, `max_items_per_entity`, `background`, and `live_fetch`. `live_fetch` remains false by default and requires `ENABLE_API_LIVE_FETCH=true`; background runs reuse the existing Redis/RQ queue seam.

Collected items retain only title, URL, summary/preview, timestamps, hashes, entity/provider metadata and matched terms. High-risk term matches create an alert for human acknowledgement; `no_match` does not. Alerts never run an Agent or publish a response automatically.

The offline Monitoring Eval in `backend/api/monitoring_eval.py` uses local golden cases to expose relevance mismatches, false alerts, missed risks, and duplicates without calling an LLM or a provider.

## Interview version

> 我把手动 source 采集扩展成 Watchlist 驱动的准实时监测，但没有放开任意 URL。企业先配置公司、品牌、别名和风险词，系统用确定性 Query Builder 生成有限查询，再复用白名单 provider adapter。结果作为 Public Signal 保存摘要和来源，风险词命中生成需要人工确认的 Alert；默认不联网、不自动运行 Agent、不自动发布。
