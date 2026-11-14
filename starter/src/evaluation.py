"""Evaluate retrieved evidence and preserve per-query traces."""
from __future__ import annotations

import re
from typing import Any
from .ingestion import normalize_text


def _clean_for_match(text: str) -> str:
    """Normalize whitespace for robust substring matching without changing words or numbers."""
    norm = normalize_text(text)
    return re.sub(r"\s+", " ", norm).strip()


def _check_single_gold(hit: dict[str, Any], gold_source_id: str, gold_page: int, evidence_quote: str) -> dict[str, Any]:
    meta = hit.get("metadata", {})
    hit_doc = meta.get("document_id")
    hit_page = int(meta.get("page", -1))

    source_page_match = (hit_doc == gold_source_id) and (hit_page == int(gold_page))
    clean_chunk = _clean_for_match(hit.get("text", ""))
    clean_quote = _clean_for_match(evidence_quote)

    full_evidence_match = source_page_match and (clean_quote in clean_chunk)

    # Also detect partial overlap (e.g. if fixed-size chunking split the quote across two chunks)
    partial_overlap = False
    if source_page_match and not full_evidence_match and len(clean_quote) >= 30:
        half = len(clean_quote) // 2
        prefix = clean_quote[:half].strip()
        suffix = clean_quote[half:].strip()
        if (prefix and prefix in clean_chunk) or (suffix and suffix in clean_chunk):
            partial_overlap = True

    return {
        "source_page_match": source_page_match,
        "full_evidence_match": full_evidence_match,
        "partial_evidence_split": partial_overlap,
        "matched_gold_source_id": gold_source_id if full_evidence_match else None,
        "matched_gold_page": gold_page if full_evidence_match else None,
    }


def evaluate_query(
    question: dict[str, Any],
    hits: list[dict[str, Any]],
    strategy: str = "A",
    applied_filter: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Check source/page and enough gold evidence; keep hit@1 and hit@3 trace.

    Accept any documented alternative gold evidence (`alt_gold`). Do not infer human grounding
    or chunk coherence labels from exact string match.
    """
    gold_candidates = [
        {
            "gold_source_id": question["gold_source_id"],
            "gold_page": int(question["gold_page"]),
            "evidence_quote": question["evidence_quote"],
        }
    ]
    for alt in question.get("alt_gold", []):
        gold_candidates.append(
            {
                "gold_source_id": alt["gold_source_id"],
                "gold_page": int(alt["gold_page"]),
                "evidence_quote": alt["evidence_quote"],
            }
        )

    evaluated_hits: list[dict[str, Any]] = []
    for h in hits[:3]:
        best_eval = None
        for cand in gold_candidates:
            res = _check_single_gold(
                h, cand["gold_source_id"], cand["gold_page"], cand["evidence_quote"]
            )
            if res["full_evidence_match"]:
                best_eval = res
                break
            if best_eval is None or (res["source_page_match"] and not best_eval["source_page_match"]):
                best_eval = res

        best_eval = best_eval or {
            "source_page_match": False,
            "full_evidence_match": False,
            "partial_evidence_split": False,
            "matched_gold_source_id": None,
            "matched_gold_page": None,
        }

        # Check filter compliance on this hit if the question specifies a filter
        q_filter = question.get("filter")
        filter_compliant = None
        if q_filter:
            meta = h.get("metadata", {})
            filter_compliant = all(meta.get(k) == v for k, v in q_filter.items())

        evaluated_hits.append(
            {
                **h,
                "is_gold_hit": best_eval["full_evidence_match"],
                "source_page_match": best_eval["source_page_match"],
                "partial_evidence_split": best_eval["partial_evidence_split"],
                "matched_gold_source_id": best_eval["matched_gold_source_id"],
                "matched_gold_page": best_eval["matched_gold_page"],
                "filter_compliant": filter_compliant,
            }
        )

    hit_at_1 = bool(evaluated_hits and evaluated_hits[0]["is_gold_hit"])
    hit_at_3 = any(h["is_gold_hit"] for h in evaluated_hits[:3])

    # Check if evidence was split across multiple top-3 chunks from the gold page when hit_at_3 is False
    multi_chunk_combined_hit = False
    if not hit_at_3:
        for cand in gold_candidates:
            same_page_texts = [
                _clean_for_match(h.get("text", ""))
                for h in evaluated_hits
                if h.get("metadata", {}).get("document_id") == cand["gold_source_id"]
                and int(h.get("metadata", {}).get("page", -1)) == int(cand["gold_page"])
            ]
            if len(same_page_texts) >= 2:
                combined = " ".join(same_page_texts)
                if _clean_for_match(cand["evidence_quote"]) in combined:
                    multi_chunk_combined_hit = True
                    break

    q_filter = question.get("filter")
    top3_all_filter_compliant = None
    if q_filter:
        top3_all_filter_compliant = bool(evaluated_hits) and all(
            bool(h["filter_compliant"]) for h in evaluated_hits
        )

    return {
        "strategy": strategy,
        "id": question["id"],
        "split": question["split"],
        "type": question.get("type", ""),
        "question": question["question"],
        "expected_answer": question["expected_answer"],
        "gold_source_id": question["gold_source_id"],
        "gold_page": question["gold_page"],
        "evidence_quote": question["evidence_quote"],
        "alt_gold": question.get("alt_gold", []),
        "question_filter": q_filter,
        "applied_filter": applied_filter,
        "hit_at_1": hit_at_1,
        "evidence_hit_at_3": hit_at_3,
        "multi_chunk_combined_hit_only": multi_chunk_combined_hit,
        "top3_filter_compliant": top3_all_filter_compliant,
        "top_3_hits": evaluated_hits,
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate Hit@1 and Evidence Hit@3 (with n/N fractions) by strategy and dev/test split."""
    summary: dict[str, Any] = {}
    strategies = sorted({t["strategy"] for t in traces})

    for strat in strategies:
        strat_traces = [t for t in traces if t["strategy"] == strat]
        summary[strat] = {}
        for split in ["dev", "test", "all"]:
            sub = strat_traces if split == "all" else [t for t in strat_traces if t["split"] == split]
            n_total = len(sub)
            n_hit1 = sum(1 for t in sub if t["hit_at_1"])
            n_hit3 = sum(1 for t in sub if t["evidence_hit_at_3"])
            n_multi_split = sum(1 for t in sub if t.get("multi_chunk_combined_hit_only"))

            filter_sub = [t for t in sub if t.get("question_filter")]
            n_filter_q = len(filter_sub)
            n_filter_ok = sum(1 for t in filter_sub if t.get("top3_filter_compliant"))

            summary[strat][split] = {
                "total_questions": n_total,
                "hit_at_1_count": n_hit1,
                "hit_at_1_fraction": f"{n_hit1}/{n_total}",
                "hit_at_1_rate": round(n_hit1 / n_total, 4) if n_total else 0.0,
                "evidence_hit_at_3_count": n_hit3,
                "evidence_hit_at_3_fraction": f"{n_hit3}/{n_total}",
                "evidence_hit_at_3_rate": round(n_hit3 / n_total, 4) if n_total else 0.0,
                "multi_chunk_split_failures": n_multi_split,
                "filter_questions_count": n_filter_q,
                "filter_compliant_count": n_filter_ok,
                "filter_compliance_fraction": f"{n_filter_ok}/{n_filter_q}" if n_filter_q > 0 else "N/A",
            }
    return summary
