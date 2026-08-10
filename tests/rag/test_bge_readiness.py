import importlib

from backend.rag.embedding import HashEmbeddingModel, get_embedding_model
from scripts.check_bge_readiness import check_bge_readiness, classify_bge_failure


def test_bge_embedding_module_can_be_imported_directly():
    module = importlib.import_module("backend.rag.embeddings.bge_embedding")

    assert hasattr(module, "BGEEmbeddingModel")


def test_get_embedding_model_hash_behavior_is_unchanged():
    model = get_embedding_model("hash")

    vector = model.embed("食品安全")

    assert isinstance(model, HashEmbeddingModel)
    assert len(vector) == 128
    assert all(isinstance(value, float) for value in vector)


def test_bge_readiness_failure_does_not_fallback_to_hash():
    class FailingBGEEmbeddingModel:
        def __init__(self, model_name):
            raise RuntimeError("Cannot find the requested files in the disk cache.")

    result = check_bge_readiness(model_cls=FailingBGEEmbeddingModel)

    assert result["status"] == "BGE_NOT_AVAILABLE"
    assert result["reason"] == "model_not_cached"
    assert result["model_name"] == "BAAI/bge-small-zh"
    assert "embedding_dimension" not in result


def test_bge_readiness_success_reports_vector_health():
    class FakeBatch:
        shape = (3, 3)
        dtype = "float32"

    class FakeInnerModel:
        def encode(self, texts, normalize_embeddings=True):
            assert normalize_embeddings is True
            assert len(texts) == 3
            return FakeBatch()

    class FakeBGEEmbeddingModel:
        def __init__(self, model_name):
            self.model_name = model_name
            self._model = FakeInnerModel()

        def embed(self, text):
            return [0.6, 0.8, 0.0]

    result = check_bge_readiness(model_cls=FakeBGEEmbeddingModel)

    assert result["status"] == "BGE_READY"
    assert result["embedding_dimension"] == 3
    assert result["shape"] == [3, 3]
    assert result["dtype"] == "float32"
    assert result["norms"] == [1.0, 1.0, 1.0]
    assert result["has_nan"] == [False, False, False]
    assert result["has_inf"] == [False, False, False]


def test_bge_failure_reason_classification_is_explicit():
    assert classify_bge_failure(RuntimeError("requires sentence-transformers")) == "dependency_missing"
    assert classify_bge_failure(OSError("Cannot find the requested files in the disk cache")) == "model_not_cached"
    assert classify_bge_failure(PermissionError("拒绝访问")) == "cache_permission_error"
