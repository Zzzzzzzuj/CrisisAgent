"""Run the frozen P33.2 local retrieval comparison without changing production code."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.legal_targeted_paired import DEFAULT_CASES, run_legal_targeted_paired_eval


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline broad-vs-targeted Legal retrieval evaluation")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, help="Optional full JSON report path")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    report = run_legal_targeted_paired_eval(args.cases)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {key: report[key] for key in (
        "dataset_version", "configuration", "positive_cases", "negative_cases",
        "paired_outcome_counts", "p33_eligible_positive_cases",
        "p33_eligible_paired_outcome_counts", "hit_at_1", "hit_at_3",
        "target_retrieved_relation_coverage", "latency_ms_median",
        "by_material_kind",
        "additional_retrieval_call_per_eligible_case",
    )}
    summary["cases"] = [
        {"case_id": row["case_id"], "label": row["label"],
         "paired_outcome": row.get("paired_outcome"), "p33_eligible": row.get("p33_eligible_from_broad"),
         "broad_rank": row.get("broad_rank"), "targeted_rank": row.get("targeted_rank"),
         "rewrite_shared_count": row["rewrite_overlap"]["shared_count"]}
        for row in report["cases"]
    ]
    print(json.dumps(summary, ensure_ascii=False, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()
