# Knowledge Ingestion Regression

Knowledge ingestion regression checks whether Legal RAG knowledge remains importable, governable and safe to retrieve after corpus updates.

It is different from retrieval evaluation:

- Ingestion regression asks: can documents be imported and filtered correctly?
- Retrieval evaluation asks: does a query retrieve the expected source and evidence?
- RAG ablation asks: does RAG evidence change Legal Agent and final response outputs?

## Script

Run:

```powershell
python scripts\run_knowledge_ingestion_regression.py
```

The script uses an offline SQLite-backed repository fixture, so ordinary local checks do not require real PostgreSQL, pgvector or a real LLM.

## Checks

The regression validates:

- document count
- chunk count
- non-empty `chunk_id`
- `document_version`
- `source_category`
- `document_status`
- `is_enabled`
- published + enabled documents are retrievable
- draft documents are not retrievable
- disabled documents are not retrievable
- embedding metadata exists
- Markdown / JSON fallback remains available
- pgvector remains optional

## Why This Matters

Legal RAG evidence needs to be auditable. A document can exist in the repository but still be unsafe to retrieve if it is draft, disabled or stale. The regression keeps that governance behavior visible and repeatable.

## Current Scope

This is a productionization regression, not a retrieval-quality benchmark. It does not prove that all future legal questions retrieve the best evidence. For quality, run:

```powershell
python scripts\evaluate_rag_retrieval.py
python scripts\analyze_rag_bad_cases.py
```
