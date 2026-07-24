from backend.rag.retriever import retrieve
from backend.tools.base import BaseTool


class RegulationSearchTool(BaseTool):
    name = "regulation_search"
    description = "Search crisis response and compliance knowledge base."

    def run(self, params: dict) -> dict:
        query = params.get("query") if isinstance(params, dict) else None
        if not isinstance(query, str) or not query.strip():
            raise ValueError("regulation_search requires a non-empty string param: query")

        top_k = params.get("top_k", 3)
        if not isinstance(top_k, int) or top_k <= 0:
            raise ValueError("regulation_search param top_k must be a positive integer")

        return retrieve(query, top_k=top_k)
