"""Real embedding provider using local SentenceTransformers (google/embeddinggemma-2)."""
from __future__ import annotations

from typing import Protocol
import torch
from sentence_transformers import SentenceTransformer


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        ...

    def embed_query(self, question: str) -> list[float]:
        """Return a query vector compatible with the stored document vectors."""
        ...


class MyEmbedder:
    """Real SentenceTransformers adapter for google/embeddinggemma-2 (no mock fallback)."""

    def __init__(self, model_name: str = "google/embeddinggemma-2", batch_size: int = 32) -> None:
        if not model_name:
            raise ValueError("model_name must be provided; mock embeddings are prohibited.")
        self.model_name = model_name
        self.batch_size = batch_size
        # Load in float32 on CPU for fast and accurate execution
        self._model = SentenceTransformer(
            model_name,
            model_kwargs={"dtype": torch.float32},
        )
        dim = self._model.get_embedding_dimension()
        if not dim or dim <= 0:
            raise RuntimeError(f"Failed to determine embedding dimension for {model_name}")
        self.dimensions: int = int(dim)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vecs = self._model.encode_document(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            show_progress_bar=True,
            convert_to_numpy=True,
        )
        return [v.astype(float).tolist() for v in vecs]

    def embed_query(self, question: str) -> list[float]:
        if not question or not question.strip():
            raise ValueError("question must be a non-empty string")
        vec = self._model.encode_query(
            question,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return vec.astype(float).tolist()
