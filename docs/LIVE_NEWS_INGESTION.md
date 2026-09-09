# Live News Ingestion

P18 adds a Watchlist-driven monitoring layer on top of these controlled connectors. It generates bounded provider queries and stores entity/provider metadata; it does not turn the project into an unrestricted crawler.

## Why Live News Sources

Local JSON/CSV remains useful for deterministic tests, replay, and trace evidence. P17 adds optional live-news connectors so an operator can discover near-real-time public leads from controlled external sources before creating a `CrisisEvent`.

## Connectors

- **RSS / article_url:** allowlisted feeds or individual public pages. RSS/article access respects robots, timeout, rate limit, and source item limits.
- **GDELT DOC:** a query-based public news API connector. It requires no API key and stores only title, URL, source metadata, timestamp, and preview.
- **NewsAPI:** a query-based API connector. The source stores only `api_key_env` such as `NEWSAPI_KEY`; the secret remains in process environment variables and is never stored in registry JSON.

## Near-Real-Time, Not Real-Time Monitoring

GDELT/NewsAPI queries run only when an authorized user manually triggers live-fetch. `lookback_minutes`, source query, timeout, rate limit, and `max_items` bound each request. This is near-real-time polling, not second-level streaming or whole-web coverage.

## Safety Controls

- `live_fetch` defaults to false and the API also requires `ENABLE_API_LIVE_FETCH=true`.
- Sources stay allowlisted, HTTPS-only, and disabled by default.
- The system does not login, retain cookies, bypass robots/CAPTCHA/anti-bot controls, recurse links, use proxies, or collect private data.
- Missing NewsAPI credentials return `missing_api_key`; 403, 429, timeout, and parsing failures return structured source failures.
- No connector calls an LLM, creates a CrisisEvent automatically, runs an Agent automatically, or publishes content.

## Collected Item Store

Only a formal `POST /api/ingestion/run` with `live_fetch=true` writes `CollectedItem` records. A record stores source identity, title, URL, short preview, timestamps, matched keywords, and a content hash. It does not store news full text. `GET /api/collected-items` supports source/run/status filtering.

## Fetch Preview

`POST /api/sources/{source_id}/fetch-preview` checks one source. With `live_fetch=false`, it never contacts the network. With explicit live-fetch and the server switch enabled, it returns short preview items but does not create an IngestionRun, CrisisEvent, Agent run, or CollectedItem record.

## Interview Version

> I did not turn the project into an unrestricted crawler. I added two query-based public-news connectors on top of the existing Source Registry and Ingestion Run path. GDELT needs no secret; NewsAPI reads only an environment-variable name from configuration. Both are manual, bounded, timeout-controlled, and produce source-level failure metadata. Formal ingestion keeps short evidence previews and content hashes for deduplication, then still requires event review and never auto-publishes a statement.
