"""Extract pre-defined audit samples for manual evaluation (Coherence, Metadata Usefulness, Grounding Quality).

Does NOT invent or fill manual human scores (0/1/2); leaves human label columns blank for the student to grade.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from starter.src.ingestion import load_corpus

sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    results_dir = repo_root / "results"
    audit_dir = results_dir / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)

    pages, _ = load_corpus(repo_root / "data" / "raw")
    page_map = {(p.document_id, p.page): p for p in pages}

    chunks_a = [json.loads(ln) for ln in (results_dir / "chunks_A.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    chunks_b = [json.loads(ln) for ln in (results_dir / "chunks_B.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]

    # 1. COHERENCE SAMPLE: Pre-selected BEFORE viewing scores:
    # First 5 unit IDs of blld-2019 (p01..p05) and first 5 unit IDs of nd-145-2020 (p01..p05) = 10 source positions.
    # At each unit, pick the focal text at character offset 550..650 (first boundary region in the unit)
    # and find the chunk covering that focal text in Strategy A and Strategy B/C.
    sample_units = [("blld-2019", i) for i in range(1, 6)] + [("nd-145-2020", i) for i in range(1, 6)]

    coherence_rows = []
    for pos_idx, (doc_id, pg_num) in enumerate(sample_units, start=1):
        p_obj = page_map[(doc_id, pg_num)]
        focal_offset = min(520, max(0, len(p_obj.text) // 3))
        focal_snippet = p_obj.text[focal_offset : focal_offset + 90].strip()
        anchor_probe = focal_snippet[:40].strip()

        for strat_label, chunk_list in [("A", chunks_a), ("B_and_C", chunks_b)]:
            unit_chunks = [c for c in chunk_list if c["document_id"] == doc_id and int(c["page"]) == pg_num]
            covering = [c for c in unit_chunks if anchor_probe in c["text"]]
            chosen = covering[0] if covering else unit_chunks[min(1, len(unit_chunks) - 1)]

            coherence_rows.append(
                {
                    "position_id": f"pos_{pos_idx:02d}",
                    "unit_id": p_obj.metadata["unit_id"],
                    "document_id": doc_id,
                    "page": pg_num,
                    "section": p_obj.metadata["section"],
                    "focal_source_snippet": focal_snippet.replace("\n", " "),
                    "strategy": strat_label,
                    "chunk_id": chosen["chunk_id"],
                    "chunk_char_len": len(chosen["text"]),
                    "chunk_text": chosen["text"],
                    "human_coherence_score_0_1_2": "",
                    "human_rationale": "",
                }
            )

    coh_csv = audit_dir / "coherence_audit.csv"
    with coh_csv.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(coherence_rows[0].keys()))
        writer.writeheader()
        writer.writerows(coherence_rows)

    # 2. METADATA USEFULNESS & GROUNDING SAMPLES on the 6 test questions (q19..q24)
    traces_by_strat = {}
    for strat in ["A", "B", "C"]:
        lines = (results_dir / f"traces_{strat}.jsonl").read_text(encoding="utf-8").splitlines()
        traces_by_strat[strat] = [json.loads(ln) for ln in lines if ln.strip()]

    metadata_rows = []
    grounding_rows = []

    for strat in ["A", "B", "C"]:
        test_traces = [t for t in traces_by_strat[strat] if t["split"] == "test"]
        for t in test_traces:
            qid = t["id"]
            q_filter = t.get("question_filter")
            top3 = t["top_3_hits"]

            for h in top3:
                meta = h.get("metadata", {})
                src_page_obj = page_map.get((meta.get("document_id"), int(meta.get("page", -1))))
                # Objective check whether chunk text actually comes from the claimed source/page
                text_exists_in_claimed_unit = bool(src_page_obj and (h["text"][:60] in src_page_obj.text))
                metadata_rows.append(
                    {
                        "strategy": strat,
                        "question_id": qid,
                        "rank": h["rank"],
                        "chunk_id": h["chunk_id"],
                        "claimed_document_id": meta.get("document_id", ""),
                        "claimed_source": meta.get("source", ""),
                        "claimed_page": meta.get("page", ""),
                        "claimed_document_type": meta.get("document_type", ""),
                        "claimed_year": meta.get("year", ""),
                        "claimed_section": meta.get("section", ""),
                        "question_filter": json.dumps(q_filter, ensure_ascii=False) if q_filter else "none",
                        "filter_compliant_auto": h.get("filter_compliant") if q_filter else "N/A",
                        "text_verified_in_claimed_source_auto": text_exists_in_claimed_unit,
                        "human_metadata_complete_and_correct_yes_no": "",
                        "human_error_note": "",
                    }
                )

            grounding_rows.append(
                {
                    "strategy": strat,
                    "question_id": qid,
                    "question_type": t.get("type", ""),
                    "question": t["question"],
                    "expected_answer": t["expected_answer"],
                    "gold_source_id": t["gold_source_id"],
                    "gold_page": t["gold_page"],
                    "gold_evidence_quote": t["evidence_quote"],
                    "auto_hit_at_1": t["hit_at_1"],
                    "auto_evidence_hit_at_3": t["evidence_hit_at_3"],
                    "top1_chunk_id": top3[0]["chunk_id"] if len(top3) > 0 else "",
                    "top1_text": top3[0]["text"] if len(top3) > 0 else "",
                    "top2_chunk_id": top3[1]["chunk_id"] if len(top3) > 1 else "",
                    "top2_text": top3[1]["text"] if len(top3) > 1 else "",
                    "top3_chunk_id": top3[2]["chunk_id"] if len(top3) > 2 else "",
                    "top3_text": top3[2]["text"] if len(top3) > 2 else "",
                    "human_grounding_score_0_1_2": "",
                    "human_rationale": "",
                }
            )

    meta_csv = audit_dir / "metadata_audit.csv"
    with meta_csv.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(metadata_rows[0].keys()))
        writer.writeheader()
        writer.writerows(metadata_rows)

    grd_csv = audit_dir / "grounding_audit.csv"
    with grd_csv.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(grounding_rows[0].keys()))
        writer.writeheader()
        writer.writerows(grounding_rows)

    print(f"Generated {coh_csv} ({len(coherence_rows)} rows)")
    print(f"Generated {meta_csv} ({len(metadata_rows)} rows)")
    print(f"Generated {grd_csv} ({len(grounding_rows)} rows)")


if __name__ == "__main__":
    main()
