"""Day 06 Pipeline Entry Point: Ingest, Chunk, Embed, Upsert, Re-ingest Verification, and Benchmark Retrieval."""
from __future__ import annotations

import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .chunking import by_paragraph, fixed_size
from .embeddings import MyEmbedder
from .evaluation import evaluate_query, summarize
from .ingestion import load_corpus
from .models import Chunk
from .store import ChromaVectorStore

sys.stdout.reconfigure(encoding="utf-8")


def _chunk_stats(chunks: list[Chunk]) -> dict[str, Any]:
    lengths = [len(c.text) for c in chunks]
    sorted_lens = sorted(lengths)
    n = len(sorted_lens)
    return {
        "chunk_count": n,
        "total_chars": sum(lengths),
        "approx_tokens_est": round(sum(lengths) / 4.0),
        "min_len": sorted_lens[0] if n else 0,
        "p25_len": sorted_lens[n // 4] if n else 0,
        "median_len": int(statistics.median(sorted_lens)) if n else 0,
        "mean_len": round(statistics.mean(sorted_lens), 1) if n else 0.0,
        "p75_len": sorted_lens[(3 * n) // 4] if n else 0,
        "max_len": sorted_lens[-1] if n else 0,
        "by_document": {
            doc_id: sum(1 for c in chunks if c.document_id == doc_id)
            for doc_id in sorted({c.document_id for c in chunks})
        },
    }


def _save_chunks_jsonl(path: Path, chunks: list[Chunk]) -> None:
    lines = []
    for c in chunks:
        lines.append(
            json.dumps(
                {
                    "chunk_id": c.chunk_id,
                    "document_id": c.document_id,
                    "source": c.source,
                    "page": c.page,
                    "text": c.text,
                    "metadata": c.metadata,
                },
                ensure_ascii=False,
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    raw_dir = repo_root / "data" / "raw"
    results_dir = repo_root / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    print("[1/5] Loading and normalizing corpus...")
    t0 = time.perf_counter()
    pages, ingest_report = load_corpus(raw_dir)
    t_load = round(time.perf_counter() - t0, 3)
    if len(pages) < 30:
        raise RuntimeError(f"Corpus has only {len(pages)} valid units; minimum 30 required.")
    print(f"      Loaded {len(pages)} valid content units ({ingest_report['total_normalized_chars']} chars) in {t_load}s.")

    print("[2/5] Building chunks for Strategy A (fixed 500/50) and Strategy B/C (paragraph max 800)...")
    t_ca0 = time.perf_counter()
    chunks_a = [c for p in pages for c in fixed_size(p, size=500, overlap=50)]
    t_chunk_a = round(time.perf_counter() - t_ca0, 3)

    t_cb0 = time.perf_counter()
    chunks_b = [c for p in pages for c in by_paragraph(p, max_size=800)]
    t_chunk_b = round(time.perf_counter() - t_cb0, 3)

    _save_chunks_jsonl(results_dir / "chunks_A.jsonl", chunks_a)
    _save_chunks_jsonl(results_dir / "chunks_B.jsonl", chunks_b)

    stats_a = _chunk_stats(chunks_a)
    stats_b = _chunk_stats(chunks_b)
    print(f"      Strategy A: {stats_a['chunk_count']} chunks (mean={stats_a['mean_len']} chars)")
    print(f"      Strategy B/C: {stats_b['chunk_count']} chunks (mean={stats_b['mean_len']} chars)")

    print("[3/5] Initializing real embedding model (google/embeddinggemma-2) and Chroma persistent store...")
    embedder = MyEmbedder(model_name="google/embeddinggemma-2", batch_size=32)
    store = ChromaVectorStore(persist_dir=results_dir / "chroma", dimensions=embedder.dimensions)
    store.create_schema()

    print(f"      Embedding Strategy A ({len(chunks_a)} chunks)...")
    t_ea0 = time.perf_counter()
    vecs_a = embedder.embed_documents([c.text for c in chunks_a])
    upsert_a_first = store.upsert("A", chunks_a, vecs_a)
    t_ingest_a = round(time.perf_counter() - t_ea0, 3)

    print(f"      Embedding Strategy B/C ({len(chunks_b)} chunks)...")
    t_eb0 = time.perf_counter()
    vecs_b = embedder.embed_documents([c.text for c in chunks_b])
    upsert_b_first = store.upsert("B", chunks_b, vecs_b)
    t_ingest_b = round(time.perf_counter() - t_eb0, 3)

    print("[4/5] Verifying idempotent re-ingestion (no duplicate chunks on second upsert)...")
    upsert_a_reingest = store.upsert("A", chunks_a, vecs_a)
    upsert_b_reingest = store.upsert("B", chunks_b, vecs_b)
    print(f"      Strategy A re-ingest: before={upsert_a_reingest['count_before']} -> after={upsert_a_reingest['count_after']}")
    print(f"      Strategy B re-ingest: before={upsert_b_reingest['count_before']} -> after={upsert_b_reingest['count_after']}")

    print("[5/5] Running benchmark retrieval across Strategies A, B, and C...")
    bench_data = json.loads((repo_root / "benchmark" / "questions.json").read_text(encoding="utf-8"))
    questions = bench_data["questions"]

    # Embed all queries once using the query prompt
    q_vectors = {q["id"]: embedder.embed_query(q["question"]) for q in questions}

    all_traces: list[dict[str, Any]] = []
    query_timings: dict[str, float] = {}

    for strat in ["A", "B", "C"]:
        t_q0 = time.perf_counter()
        strat_traces: list[dict[str, Any]] = []
        for q in questions:
            q_vec = q_vectors[q["id"]]
            # Only Strategy C applies metadata filters when provided by the question
            applied_filter = q.get("filter") if strat == "C" else None
            hits = store.search(strat, q_vec, top_k=3, filters=applied_filter)
            trace = evaluate_query(q, hits, strategy=strat, applied_filter=applied_filter)
            strat_traces.append(trace)
            all_traces.append(trace)
        query_timings[strat] = round(time.perf_counter() - t_q0, 3)

        trace_file = results_dir / f"traces_{strat}.jsonl"
        trace_file.write_text(
            "\n".join(json.dumps(t, ensure_ascii=False) for t in strat_traces) + "\n",
            encoding="utf-8",
        )

    metrics_summary = summarize(all_traces)

    full_report = {
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "embedding_model": {
            "provider": "HuggingFace / SentenceTransformers (local)",
            "model_name": embedder.model_name,
            "dimensions": embedder.dimensions,
            "dtype": "float32",
            "query_prompt_method": "model.encode_query (SearchQuery prompt, normalized)",
            "document_prompt_method": "model.encode_document (Document prompt, normalized)",
            "cost_usd": 0.0,
        },
        "vector_store": {
            "backend": "ChromaDB PersistentClient",
            "persist_directory": "results/chroma",
            "distance_metric": "cosine",
            "search_type": "Approximate Nearest Neighbor (HNSW)",
        },
        "strategies": {
            "A": {
                "description": "Fixed-size chunking (size=500 chars, overlap=50 chars), no metadata filtering",
                "chunk_stats": stats_a,
                "chunking_time_sec": t_chunk_a,
                "embed_and_upsert_time_sec": t_ingest_a,
                "query_time_24q_sec": query_timings["A"],
                "cost_usd": 0.0,
                "first_upsert": upsert_a_first,
                "reingest_verification": upsert_a_reingest,
            },
            "B": {
                "description": "Structure-aware paragraph/article chunking (max_size=800 chars), no metadata filtering",
                "chunk_stats": stats_b,
                "chunking_time_sec": t_chunk_b,
                "embed_and_upsert_time_sec": t_ingest_b,
                "query_time_24q_sec": query_timings["B"],
                "cost_usd": 0.0,
                "first_upsert": upsert_b_first,
                "reingest_verification": upsert_b_reingest,
            },
            "C": {
                "description": "Same chunks/index as Strategy B + metadata filtering (document_type / year) when question specifies filter",
                "chunk_stats": stats_b,
                "chunking_time_sec": t_chunk_b,
                "embed_and_upsert_time_sec": t_ingest_b,
                "shared_index_with_B": True,
                "query_time_24q_sec": query_timings["C"],
                "cost_usd": 0.0,
                "reingest_verification": upsert_b_reingest,
            },
        },
        "retrieval_metrics": metrics_summary,
    }

    (results_dir / "metrics.json").write_text(
        json.dumps(full_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n=== RETRIEVAL SUMMARY ===")
    for strat in ["A", "B", "C"]:
        dev_m = metrics_summary[strat]["dev"]
        test_m = metrics_summary[strat]["test"]
        print(
            f"Strategy {strat} | DEV: Hit@1={dev_m['hit_at_1_fraction']} ({dev_m['hit_at_1_rate']*100:.1f}%), "
            f"Hit@3={dev_m['evidence_hit_at_3_fraction']} ({dev_m['evidence_hit_at_3_rate']*100:.1f}%), "
            f"Filter={dev_m['filter_compliance_fraction']} | "
            f"TEST: Hit@1={test_m['hit_at_1_fraction']} ({test_m['hit_at_1_rate']*100:.1f}%), "
            f"Hit@3={test_m['evidence_hit_at_3_fraction']} ({test_m['evidence_hit_at_3_rate']*100:.1f}%), "
            f"Filter={test_m['filter_compliance_fraction']}"
        )


if __name__ == "__main__":
    main()
