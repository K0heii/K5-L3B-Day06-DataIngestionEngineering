"""Verify that all benchmark questions, gold sources/pages, and evidence quotes exist in the normalized corpus."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from starter.src.ingestion import load_corpus, normalize_text

sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    pages, _ = load_corpus(Path("data/raw"))
    page_map = {(p.document_id, p.page): p for p in pages}

    bench_path = Path("benchmark/questions.json")
    bench = json.loads(bench_path.read_text(encoding="utf-8"))
    questions = bench["questions"]

    results = []
    all_passed = True

    for q in questions:
        qid = q["id"]
        src_id = q["gold_source_id"]
        pg_num = q["gold_page"]
        quote = normalize_text(q["evidence_quote"])

        page_obj = page_map.get((src_id, pg_num))
        if not page_obj:
            all_passed = False
            results.append(
                {
                    "id": qid,
                    "split": q["split"],
                    "status": "FAIL_MISSING_PAGE",
                    "gold_source_id": src_id,
                    "gold_page": pg_num,
                }
            )
            continue

        pos = page_obj.text.find(quote)
        primary_ok = pos >= 0

        # Also verify any alt_gold entries
        alt_checks = []
        for alt in q.get("alt_gold", []):
            alt_page = page_map.get((alt["gold_source_id"], alt["gold_page"]))
            alt_quote = normalize_text(alt["evidence_quote"])
            alt_pos = alt_page.text.find(alt_quote) if alt_page else -1
            alt_checks.append(
                {
                    "gold_source_id": alt["gold_source_id"],
                    "gold_page": alt["gold_page"],
                    "found": alt_pos >= 0,
                    "char_offset": alt_pos,
                }
            )
            if alt_pos < 0:
                all_passed = False

        if not primary_ok:
            all_passed = False

        results.append(
            {
                "id": qid,
                "split": q["split"],
                "type": q["type"],
                "gold_source_id": src_id,
                "gold_page": pg_num,
                "unit_id": page_obj.metadata.get("unit_id"),
                "has_filter": q.get("filter") is not None,
                "filter": q.get("filter"),
                "primary_quote_found": primary_ok,
                "primary_char_offset": pos,
                "evidence_length": len(quote),
                "alt_gold_checks": alt_checks,
            }
        )

    dev_qs = [q for q in questions if q["split"] == "dev"]
    test_qs = [q for q in questions if q["split"] == "test"]
    filter_dev = [q for q in dev_qs if q.get("filter")]
    filter_test = [q for q in test_qs if q.get("filter")]

    report = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "all_passed": all_passed,
        "total_questions": len(questions),
        "dev_count": len(dev_qs),
        "test_count": len(test_qs),
        "filter_questions_total": len(filter_dev) + len(filter_test),
        "filter_questions_dev": len(filter_dev),
        "filter_questions_test": len(filter_test),
        "checks": results,
    }

    out_path = Path("benchmark/verify_report.json")
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"Verification complete: all_passed={all_passed} | "
        f"total={len(questions)} (dev={len(dev_qs)}, test={len(test_qs)}) | "
        f"filter_questions={len(filter_dev)+len(filter_test)} (dev={len(filter_dev)}, test={len(filter_test)})"
    )
    if not all_passed:
        for r in results:
            if not r.get("primary_quote_found") or any(not a["found"] for a in r.get("alt_gold_checks", [])):
                print("FAILED:", r)
        sys.exit(1)


if __name__ == "__main__":
    main()
