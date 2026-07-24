from backend.rag.schemas import RetrievalResult, RetrievedChunk
from evaluation.rewrite_evaluator import evaluate_rewrite_effect


class StubRetriever:
    def retrieve(self, query: str, top_k: int = 3):
        if query == "食品事件":
            sources = ["crisis_response.md"]
        else:
            sources = ["food_safety.md"]

        chunks = [
            RetrievedChunk(
                chunk_id=source,
                text=f"{source} text",
                source=source,
                title=source,
                score=1.0,
            )
            for source in sources
        ]
        return RetrievalResult(
            context="context",
            chunks=chunks,
            sources=[{"source": chunk.source, "title": chunk.title, "score": chunk.score} for chunk in chunks],
        )


def test_rewrite_evaluation_compares_recall_and_mrr(monkeypatch):
    cases = [
        {
            "id": "case-1",
            "query": "食品事件",
            "expected_sources": ["food_safety.md"],
            "top_k": 3,
        }
    ]

    class FakePipeline:
        def __init__(self):
            self.stub = StubRetriever()

        def retrieve(self, query, top_k=3):
            from backend.rag.query_rewriter import rewrite_query

            all_sources = []
            for rewritten_query in rewrite_query(query):
                result = self.stub.retrieve(rewritten_query, top_k=top_k)
                all_sources.extend(result.sources)
            return RetrievalResult(
                context="context",
                chunks=[],
                sources=all_sources[:top_k],
            )

    class FakeSingleQuery:
        def __init__(self):
            self.stub = StubRetriever()

        def retrieve(self, query, top_k=3):
            return self.stub.retrieve(query, top_k=top_k)

    monkeypatch.setattr("evaluation.rewrite_evaluator.RagPipelineRetriever", FakePipeline)
    monkeypatch.setattr("evaluation.rewrite_evaluator.SingleQueryPipelineRetriever", FakeSingleQuery)

    result = evaluate_rewrite_effect(cases)

    assert result["baseline"]["summary"]["recall_at_k"] == 0.0
    assert result["rewrite"]["summary"]["recall_at_k"] == 1.0
    assert result["delta"]["recall_at_k"] == 1.0
    assert result["delta"]["mrr"] > 0
