import sys

from backend.rag.embedding import BGEEmbeddingModel, HashEmbeddingModel, get_embedding_model


def test_chinese_text_can_generate_embedding_vector():
    model = HashEmbeddingModel(dimension=64)

    vector = model.embed("食品安全危机需要谨慎回应")

    assert vector
    assert len(vector) == 64
    assert all(isinstance(value, float) for value in vector)


def test_different_texts_generate_same_dimension_vectors():
    model = HashEmbeddingModel(dimension=64)

    first_vector = model.embed("食品安全危机")
    second_vector = model.embed("避免提前定责")

    assert len(first_vector) == len(second_vector)
    assert len(first_vector) == 64


def test_empty_string_returns_zero_vector():
    model = HashEmbeddingModel(dimension=32)

    vector = model.embed("")

    assert vector == [0.0] * 32


def test_get_embedding_model_returns_model_with_embed_method():
    model = get_embedding_model()

    vector = model.embed("危机公关")

    assert isinstance(vector, list)
    assert all(isinstance(value, float) for value in vector)


def test_embedding_factory_returns_hash_by_default(monkeypatch):
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)

    model = get_embedding_model()

    assert isinstance(model, HashEmbeddingModel)


def test_embedding_factory_selects_hash(monkeypatch):
    monkeypatch.setenv("EMBEDDING_MODEL", "hash")

    model = get_embedding_model()

    assert isinstance(model, HashEmbeddingModel)


def test_embedding_factory_selects_bge_with_mock(monkeypatch):
    class FakeBGEEmbeddingModel:
        def embed(self, text):
            return [0.1, 0.2, 0.3]

    monkeypatch.setenv("EMBEDDING_MODEL", "bge")
    monkeypatch.setattr("backend.rag.embedding.BGEEmbeddingModel", FakeBGEEmbeddingModel)

    model = get_embedding_model()

    assert isinstance(model, FakeBGEEmbeddingModel)
    assert model.embed("crisis") == [0.1, 0.2, 0.3]


def test_embedding_factory_rejects_unknown_model(monkeypatch):
    monkeypatch.setenv("EMBEDDING_MODEL", "unknown")

    try:
        get_embedding_model()
    except ValueError as exc:
        assert "EMBEDDING_MODEL" in str(exc)
    else:
        raise AssertionError("Expected unknown embedding model to fail.")


def test_bge_embedding_model_uses_lazy_sentence_transformer_loading(monkeypatch):
    class FakeSentenceTransformer:
        def __init__(self, model_name):
            self.model_name = model_name

        def encode(self, text, normalize_embeddings=True):
            assert text == "food safety"
            assert normalize_embeddings is True
            return [1, 2, 3]

    class FakeModule:
        SentenceTransformer = FakeSentenceTransformer

    monkeypatch.setitem(sys.modules, "sentence_transformers", FakeModule)

    model = BGEEmbeddingModel(model_name="fake-bge")
    vector = model.embed("food safety")

    assert vector == [1.0, 2.0, 3.0]
    assert model.model_name == "fake-bge"


def test_hash_embedding_dimension_is_consistent():
    model = HashEmbeddingModel(dimension=16)

    vectors = [
        model.embed("food safety"),
        model.embed("legal risk"),
        model.embed(""),
    ]

    assert {len(vector) for vector in vectors} == {16}
