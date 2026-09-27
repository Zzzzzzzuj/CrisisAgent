"""Small frozen-set baseline for candidate legal-rule relations only."""

import json
from collections import Counter
from pathlib import Path

from backend.agents.legal_claim_relation import RELATIONS, build_legal_claim_relations


def evaluate_relation_cases(path: str | Path) -> dict:
    cases = json.loads(Path(path).read_text(encoding="utf-8"))
    matrix = {expected: {actual: 0 for actual in sorted(RELATIONS)} for expected in sorted(RELATIONS)}
    correct = 0
    skipped = 0
    by_label = Counter()
    for case in cases:
        claim = {key: case[key] for key in ("claim", "requires_legal_rule", "requires_case_fact")}
        chunk = {"chunk_id": case["id"], "source": "frozen-fixture", "text": case["evidence"]}
        rows = build_legal_claim_relations([claim], [chunk])["legal_claim_relations"]
        if case["expected"] is None:
            if rows:
                raise ValueError(f"Case-fact-only fixture produced a legal relation: {case['id']}")
            skipped += 1
            continue
        if case["expected"] not in RELATIONS or len(rows) != 1:
            raise ValueError(f"Invalid frozen relation fixture: {case['id']}")
        actual = rows[0]["relation"]
        matrix[case["expected"]][actual] += 1
        by_label[case["expected"]] += 1
        correct += actual == case["expected"]
    labeled = len(cases) - skipped
    return {
        "total_cases": len(cases),
        "labeled_pairs": labeled,
        "skipped_case_fact_only": skipped,
        "correct": correct,
        "accuracy": correct / labeled if labeled else 0.0,
        "per_class_correct": {label: matrix[label][label] for label in sorted(RELATIONS)},
        "per_class_total": dict(sorted(by_label.items())),
        "confusion_matrix": matrix,
    }
