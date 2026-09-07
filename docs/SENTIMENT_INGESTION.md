# Sentiment Ingestion

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

## Interview explanation

I did not send raw web content directly to an LLM. I first normalized source text, removed duplicates, clustered related reports into an event, and preserved current/historical/uncertain and verified/unverified/conflicting status. The resulting event text is then passed into the existing CrisisAgent runtime. This adds a realistic upstream input boundary without changing the existing Agent order, RAG logic, Prompt semantics, or API contract. Phase 1 uses offline fixtures; real RSS or platform ingestion would require separate source permissions, rate limiting, retry, idempotency, and privacy controls.
