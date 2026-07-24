from backend.rag.base import BaseRetriever
from backend.rag.hybrid_retriever import HybridRetriever
from backend.rag.keyword_retriever import KeywordRetriever
from backend.rag.pipeline_retriever import RagPipelineRetriever
from backend.rag.vector_retriever import VectorRetriever


def get_retriever(retriever_type: str = "keyword") -> BaseRetriever:
    if retriever_type == "pipeline":
        return RagPipelineRetriever()
    if retriever_type == "hybrid":
        return HybridRetriever()
    if retriever_type == "vector":
        return VectorRetriever()
    if retriever_type == "keyword":
        return KeywordRetriever()
    raise ValueError(f"Unsupported retriever type: {retriever_type}")
