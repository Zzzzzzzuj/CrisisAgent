# Code Knowledge Agent and Cross-module Error Tracing

This project includes a lightweight static code index to explain how a code knowledge agent could support debugging.

## Static Code Index

Run:

```powershell
python scripts\index_project_knowledge.py
```

Output:

```text
data/code_knowledge_index.json
```

The index scans:

- `backend/core`
- `backend/rag`
- `backend/agents`
- `backend/skills`

It extracts:

- file path
- module responsibility
- class names
- function names
- imports

It does not use embeddings, LLMs, Redis, PostgreSQL or pgvector.

## How It Helps Error Tracing

A code knowledge agent can combine:

- error message
- file path
- module responsibility
- Agent trace
- RAG evidence
- runtime metrics

to narrow down the likely source of a cross-module issue.

## Example 1: RAG Evidence Missing `retrieval_backend`

Likely modules:

- `backend/agents/legal_agent.py`
- `backend/rag/vector_retriever.py`
- `backend/core/executor.py`

Reasoning:

- Legal Agent creates RAG metadata.
- Retriever determines backend metadata.
- Executor copies metadata into Agent trace.

## Example 2: RQ Worker Failure

Likely modules:

- `backend/core/runtime_tasks.py`
- `scripts/run_rq_worker.py`
- `backend/observability/readiness.py`

Reasoning:

- Runtime tasks submit and execute queued jobs.
- Worker script starts the RQ worker.
- Readiness reports whether async runtime dependencies are available.

## Example 3: pgvector Fallback

Likely modules:

- `backend/rag/pgvector_store.py`
- `backend/rag/vector_backend.py`
- `backend/rag/knowledge_repository.py`

Reasoning:

- vector backend config decides whether pgvector is enabled.
- pgvector store handles similarity search or failure.
- knowledge repository writes JSON embeddings and optional pgvector rows.

## Example 4: Guardrail Not Triggered

Likely modules:

- `backend/guardrails/`
- `backend/core/policy.py`
- `backend/core/guardrail_runtime.py`

Reasoning:

- guardrail modules detect input/output risks.
- guardrail runtime writes results into AgentState metadata.
- policy decides whether Human Review is required.

## Difference From a Real Code Agent

Current scope:

- static index
- documentation
- manual interpretation

Not implemented:

- semantic code search
- automatic patch generation
- autonomous tool execution
- multi-repo dependency graph

This is intentionally a lightweight interview/demo layer, not a full coding agent platform.
