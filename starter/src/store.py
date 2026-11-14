"""Persistent vector store and metadata filter implementation using ChromaDB (and optional pgvector contract)."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import chromadb

from .models import Chunk

PERMITTED_FILTER_FIELDS = {"document_id", "source", "page", "document_type", "year", "chapter", "unit_id"}


def _sanitize_metadata(chunk: Chunk) -> dict[str, str | int | float | bool]:
    """Flatten chunk metadata to scalar types supported by Chroma metadata filtering."""
    meta: dict[str, str | int | float | bool] = {
        "document_id": str(chunk.document_id),
        "source": str(chunk.source),
        "page": int(chunk.page),
    }
    for k, v in chunk.metadata.items():
        if isinstance(v, (str, int, float, bool)):
            meta[k] = v
    return meta


def _build_chroma_where(filters: dict[str, Any] | None) -> dict[str, Any] | None:
    if not filters:
        return None
    clauses: list[dict[str, Any]] = []
    for k, v in filters.items():
        if k not in PERMITTED_FILTER_FIELDS:
            raise ValueError(f"Filter field '{k}' is not in permitted fields: {sorted(PERMITTED_FILTER_FIELDS)}")
        clauses.append({k: v})
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


class ChromaVectorStore:
    """Persistent disk-backed Chroma vector store using cosine similarity and metadata filtering."""

    def __init__(self, persist_dir: str | Path = "results/chroma", dimensions: int = 768) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.dimensions = dimensions
        self.client = chromadb.PersistentClient(path=str(self.persist_dir))

    def _collection_name(self, strategy: str) -> str:
        # Strategy C shares Strategy B's indexed chunks and only differs by query-time metadata filtering
        base = "B" if strategy.upper() == "C" else strategy.upper()
        return f"day06_strategy_{base}"

    def get_collection(self, strategy: str):
        return self.client.get_or_create_collection(
            name=self._collection_name(strategy),
            metadata={"hnsw:space": "cosine", "dimensions": self.dimensions},
        )

    def create_schema(self) -> None:
        """Ensure collections for strategies A and B exist on disk."""
        self.get_collection("A")
        self.get_collection("B")

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> dict[str, int]:
        """Validate lengths/dimensions, remove obsolete chunks for re-ingested documents, and upsert idempotently."""
        if len(chunks) != len(vectors):
            raise ValueError(f"chunks ({len(chunks)}) and vectors ({len(vectors)}) length mismatch")
        for v in vectors:
            if len(v) != self.dimensions:
                raise ValueError(f"Vector dimension {len(v)} != expected {self.dimensions}")

        col = self.get_collection(strategy)
        count_before = col.count()

        # Identify source documents being updated and remove any obsolete chunk IDs for those documents
        incoming_ids = {c.chunk_id for c in chunks}
        doc_ids = sorted({c.document_id for c in chunks})
        obsolete_removed = 0

        for doc_id in doc_ids:
            existing = col.get(where={"document_id": doc_id}, include=[])
            existing_ids = existing.get("ids", []) if existing else []
            stale_ids = [eid for eid in existing_ids if eid not in incoming_ids]
            if stale_ids:
                col.delete(ids=stale_ids)
                obsolete_removed += len(stale_ids)

        # Upsert in batches to stay well below SQLite parameter limits
        batch_size = 250
        for i in range(0, len(chunks), batch_size):
            b_chunks = chunks[i : i + batch_size]
            b_vecs = vectors[i : i + batch_size]
            col.upsert(
                ids=[c.chunk_id for c in b_chunks],
                documents=[c.text for c in b_chunks],
                embeddings=b_vecs,
                metadatas=[_sanitize_metadata(c) for c in b_chunks],
            )

        count_after = col.count()
        return {
            "count_before": count_before,
            "upserted": len(chunks),
            "obsolete_removed": obsolete_removed,
            "count_after": count_after,
        }

    def count(self, strategy: str) -> int:
        return self.get_collection(strategy).count()

    def search(
        self,
        strategy: str,
        query_vector: list[float],
        top_k: int = 3,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Filter permitted metadata and rank by cosine similarity (1 - cosine_distance)."""
        if len(query_vector) != self.dimensions:
            raise ValueError(f"Query vector dimension {len(query_vector)} != expected {self.dimensions}")

        col = self.get_collection(strategy)
        where_clause = _build_chroma_where(filters)

        res = col.query(
            query_embeddings=[query_vector],
            n_results=top_k,
            where=where_clause,
            include=["documents", "metadatas", "distances"],
        )

        ids = (res.get("ids") or [[]])[0]
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]

        hits: list[dict[str, Any]] = []
        for rank, (cid, text, meta, dist) in enumerate(zip(ids, docs, metas, dists), start=1):
            cosine_sim = round(1.0 - float(dist), 6)
            hits.append(
                {
                    "rank": rank,
                    "chunk_id": cid,
                    "text": text,
                    "score": cosine_sim,
                    "cosine_distance": round(float(dist), 6),
                    "metadata": meta,
                }
            )
        return hits


# Alias PgVectorStore to ChromaVectorStore so starter imports remain compatible if referenced
PgVectorStore = ChromaVectorStore
