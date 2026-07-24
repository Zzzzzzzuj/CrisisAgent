from backend.rag.factory import get_retriever


def retrieve(query: str, top_k: int = 3) -> dict:
    return get_retriever("pipeline").retrieve(query, top_k).to_dict()
