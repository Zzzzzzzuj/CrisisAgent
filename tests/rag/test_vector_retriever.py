from backend.rag.factory import get_retriever
from backend.rag.keyword_retriever import KeywordRetriever
from backend.rag.schemas import RetrievalResult
from backend.rag.vector_retriever import VectorRetriever


class SpyEmbeddingModel:
    def __init__(self):
        self.inputs = []

    def embed(self, text: str) -> list[float]:
        self.inputs.append(text)
        if "食品" in text or "过期" in text or "监管" in text:
            return [1.0, 0.0, 0.0]
        if "定责" in text or "责任" in text:
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]


def test_vector_retriever_embeds_query():
    embedding_model = SpyEmbeddingModel()
    retriever = VectorRetriever(embedding_model=embedding_model)

    retriever.retrieve("食品安全监管", top_k=2)

    assert "食品安全监管" in embedding_model.inputs


def test_vector_retriever_returns_results():
    retriever = VectorRetriever()

    result = retriever.retrieve("食品品牌使用过期原料，监管介入", top_k=3)

    assert isinstance(result, RetrievalResult)
    assert result.context
    assert result.sources
    assert result.chunks


def test_vector_retriever_result_shape_matches_keyword_retriever():
    vector_result = VectorRetriever().retrieve("避免提前定责，使用条件式责任表达", top_k=2)
    keyword_result = KeywordRetriever().retrieve("避免提前定责，使用条件式责任表达", top_k=2)

    assert set(vector_result.to_dict().keys()) == set(keyword_result.to_dict().keys())
    assert {"context", "chunks", "sources"} == set(vector_result.to_dict().keys())


def test_vector_retriever_top_k_limits_results():
    retriever = VectorRetriever()

    result = retriever.retrieve("危机回应", top_k=1)

    assert len(result.chunks) == 1
    assert len(result.sources) == 1


def test_factory_can_return_vector_retriever_without_changing_default():
    assert isinstance(get_retriever(), KeywordRetriever)
    assert isinstance(get_retriever("vector"), VectorRetriever)
