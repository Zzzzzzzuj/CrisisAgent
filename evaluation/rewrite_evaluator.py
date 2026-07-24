from backend.rag.pipeline_retriever import RagPipelineRetriever
import backend.rag.pipeline_retriever as pipeline_module
from evaluation.embedding_metrics import calculate_case_metrics, summarize_embedding_results


class SingleQueryPipelineRetriever(RagPipelineRetriever):
    def retrieve(self, query: str, top_k: int = 3):
        original_rewrite_query = pipeline_module.rewrite_query
        try:
            pipeline_module.rewrite_query = lambda value: [value]
            return super().retrieve(query, top_k=top_k)
        finally:
            pipeline_module.rewrite_query = original_rewrite_query


def evaluate_rewrite_effect(cases: list[dict], top_k: int = 3) -> dict:
    baseline = _evaluate_with_retriever(SingleQueryPipelineRetriever(), cases, top_k)
    rewritten = _evaluate_with_retriever(RagPipelineRetriever(), cases, top_k)
    return {
        "baseline": baseline,
        "rewrite": rewritten,
        "delta": {
            "recall_at_k": round(
                rewritten["summary"]["recall_at_k"] - baseline["summary"]["recall_at_k"],
                4,
            ),
            "mrr": round(rewritten["summary"]["mrr"] - baseline["summary"]["mrr"], 4),
        },
    }


def _evaluate_with_retriever(retriever, cases: list[dict], top_k: int) -> dict:
    case_results = []
    for case in cases:
        result = retriever.retrieve(case["query"], top_k=case.get("top_k", top_k))
        retrieved_sources = [source["source"] for source in result.sources]
        metrics = calculate_case_metrics(case.get("expected_sources", []), retrieved_sources)
        case_results.append(
            {
                "id": case["id"],
                "retrieved_sources": retrieved_sources,
                **metrics,
            }
        )

    return {
        "summary": summarize_embedding_results(case_results),
        "case_results": case_results,
    }
