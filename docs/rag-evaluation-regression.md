# RAG Evaluation Regression

## Why Build a Baseline

Legal RAG changes can improve one case while silently hurting another. A fixed baseline gives the project a repeatable regression check after changing the knowledge base, query rewrite, chunking, reranker, embedding, or retriever settings.

This baseline is not a public benchmark and does not represent online production quality. It is a small project-owned fixed evaluation set used to detect obvious regressions.

## Fixed Evaluation Set

The evaluation data lives in:

```powershell
data\rag_retrieval_eval_cases.json
```

Each case records:

- `case_id`
- `event`
- `expected_need_retrieval`
- `expected_source_category`
- `expected_keywords`
- `expected_human_review`
- `notes`

The current set covers:

- `food_safety`
- `data_privacy`
- `service_outage`
- `false_advertising`
- `labor_dispute`
- `product_recall`
- `financial_rumor`
- `executive_scandal`

## Metrics

- `top1_source_hit_rate`: whether the expected source category appears at rank 1.
- `top3_source_hit_rate`: whether the expected source category appears in the top 3 retrieved chunks.
- `keyword_hit_rate`: whether all expected keywords appear in the returned evidence text.
- `fallback_rate`: percentage of cases where retrieval fallback is used. Gate skip is not counted as fallback.
- `average_score`: average retrieval score across top chunks.
- `average_rerank_score`: average rerank score across top chunks.
- `context_pollution_rate`: average wrong-category ratio in the final top chunks when source categories are available.
- `backend_distribution`: count of evidence chunks by retrieval backend.

## Regression Rules

The regression script compares current metrics against:

```powershell
reports\rag_baseline.json
```

Current conservative thresholds:

- `top3_source_hit_rate` must not fall below `baseline - 0.1`.
- `fallback_rate` must not rise above `baseline + 0.1`.
- `context_pollution_rate`, when available, must not rise above `baseline + 0.15`.

If no baseline exists, the script still generates the current report and exits successfully. That mode is useful when first creating a baseline.

## How To Run

```powershell
python scripts\run_rag_regression.py
```

Outputs:

```powershell
reports\rag_regression_report.json
reports\rag_regression_report.md
```

The report includes current metrics, baseline metrics, pass/fail checks, failed cases, and likely causes such as:

- `knowledge_gap`
- `query_rewrite_issue`
- `chunk_issue`
- `rerank_issue`
- `source_category_mismatch`
- `low_score`

## Bad Case Loop

When a case fails regression, it should be added or linked to:

```powershell
data\rag_bad_cases.json
```

The bad case record should explain the failure type, root cause, suggested fix, and linked test case. After knowledge changes, run:

```powershell
python scripts\analyze_rag_bad_cases.py
python scripts\run_knowledge_ingestion_regression.py
python scripts\run_rag_regression.py
```

## Limitations

- The fixed evaluation set is small.
- It is not a public benchmark.
- It does not call a real LLM.
- It measures retrieval evidence quality, not final answer quality.
- It is intended for project regression checks, not production SLA claims.
