# RAG Bad Case Loop

This project keeps RAG failures as first-class data instead of only showing successful demos.

## Data File

Bad cases are tracked in:

```text
data/rag_bad_cases.json
```

Each item records:

- `bad_case_id`
- `crisis_event`
- `query`
- `expected_source_category`
- `actual_source_category`
- `failure_type`
- `root_cause`
- `suggested_fix`
- `status`
- `linked_test_case`

The current seed cases come from the Phase 14 retrieval evaluation, especially low-hit categories such as false advertising, labor dispute, product recall, financial rumor and executive scandal.

## Failure Types

- `no_retrieval`: no useful chunk was returned.
- `wrong_source`: retrieval returned an unrelated source category.
- `low_score`: the expected source appeared but with weak score.
- `stale_document`: retrieval depended on outdated knowledge.
- `disabled_document_hit`: disabled knowledge appeared in retrieval.
- `rerank_misorder`: reranker placed weaker evidence above stronger evidence.
- `insufficient_evidence`: category matched, but chunk text did not provide enough evidence.
- `fallback_only`: result came only from fallback, not managed knowledge.

## Root Cause Labels

- `query_rewrite`: the rewritten query broadened or shifted intent.
- `knowledge_gap`: the knowledge base lacks the needed document or section.
- `chunking_issue`: evidence exists but was split poorly.
- `embedding_issue`: semantic retrieval ranked the wrong topic higher.
- `reranker_issue`: reranker failed to promote the right evidence.
- `metadata_filter_issue`: document status/category/version metadata caused wrong filtering or evaluation.

## Analysis Script

Run:

```powershell
python scripts\analyze_rag_bad_cases.py
```

It generates:

```text
reports/rag_bad_cases_report.md
```

The report groups bad cases by failure type, root cause and status, then lists suggested knowledge updates.

## How Bad Cases Flow Back

1. Run retrieval evaluation and identify misses.
2. Add a bad case with the observed source category and root cause.
3. Decide whether the fix belongs to knowledge coverage, chunking, embedding, reranker or metadata filtering.
4. Add or update knowledge documents only when the root cause is a knowledge gap.
5. Run knowledge ingestion regression before trusting the updated corpus.
6. Re-run retrieval evaluation and keep both successes and failures in reports.

This loop is intentionally small and offline. It does not call a real LLM and does not require pgvector.
