# RAG Gate and Reranker Replay Artifact

- run_id: `20260906_162352`
- current_commit: `247ffef`
- branch: `main`
- nature: regression replay on previously used frozen datasets; not a new first holdout.
- LLM calls: none
- BGE fallback: false

## Gate Challenge v3

- historical TP/FN/TN/FP: `19/1/17/3`
- replay TP/FN/TN/FP: `19/1/17/3`
- replay TPR: `0.95`
- replay TNR: `0.85`

## Reranker Retrieval Holdout v1

- historical Old Recall@3: `0.9`
- replay Old Recall@3: `0.9`
- historical v2 Recall@3: `0.9`
- replay v2 Recall@3: `0.9`
- historical Old Pollution: `0.4722`
- replay Old Pollution: `0.4722`
- historical v2 Pollution: `0.3222`
- replay v2 Pollution: `0.3222`
- replay relative pollution reduction: `0.3177`

## Raw Files

- manifest: `reports\eval_raw\rag_gate_reranker_replay_20260906_162352\manifest.json`
- gate jsonl: `reports\eval_raw\rag_gate_reranker_replay_20260906_162352\gate_challenge_v3_cases.jsonl`
- reranker jsonl: `reports\eval_raw\rag_gate_reranker_replay_20260906_162352\reranker_holdout_v1_cases.jsonl`
- summary json: `reports\eval_raw\rag_gate_reranker_replay_20260906_162352\summary.json`
