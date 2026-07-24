from backend.rag.embedding import EmbeddingModel


class BGEEmbeddingModel(EmbeddingModel):
    def __init__(self, model_name: str = "BAAI/bge-small-zh"):
        self.model_name = model_name
        self._model = self._load_model()

    def embed(self, text: str) -> list[float]:
        if not text.strip():
            return []

        vector = self._model.encode(text, normalize_embeddings=True)
        if hasattr(vector, "tolist"):
            vector = vector.tolist()

        return [float(value) for value in vector]

    def _load_model(self):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "BGEEmbeddingModel requires sentence-transformers. "
                "Install it before using EMBEDDING_MODEL=bge."
            ) from exc

        return SentenceTransformer(self.model_name)
