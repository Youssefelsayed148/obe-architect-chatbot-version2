from __future__ import annotations

from app.rag.ollama_client import OllamaClient
from app.settings import settings


class OllamaEmbedder:
    def __init__(
        self,
        client: OllamaClient | None = None,
        model: str | None = None,
        expected_dim: int | None = None,
    ) -> None:
        self._client = client or OllamaClient()
        self._model = model or settings.ollama_embed_model
        self._expected_dim = expected_dim or settings.rag_embed_dim

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vector = self._client.embed(text=text, model=self._model)
            if self._expected_dim and len(vector) != self._expected_dim:
                raise ValueError(
                    f"Embedding dimension mismatch: expected {self._expected_dim}, got {len(vector)}"
                )
            vectors.append(vector)
        return vectors
