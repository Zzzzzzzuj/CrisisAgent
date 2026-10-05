"""Offline P2.1b closure evaluation. Builds packs from frozen AgentState fixtures only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from backend.agents.memory_retriever import retrieve_memories
from backend.core.context_pack_runtime import ContextPackRuntimeProvider
from backend.core.state import AgentState
from evaluation.frozen_hash import canonical_text_sha256


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evaluation" / "p2_1b_deterministic_closure_holdout.json"
REPORT = ROOT / "evaluation" / "reports" / "p2_1b_after.json"
FROZEN_SHA256 = "9f61a24c2ae4a47bef44cb5320090fdb78e19f48c94939a75e817b5137393370"


def _required_present(pack: dict[str, Any], rule: dict[str, Any]) -> bool:
    value: Any = pack
    for key in rule["path"].split("."):
        if not isinstance(value, dict) or key not in value:
            return False
        value = value[key]
    if "item_id" in rule:
        return isinstance(value, list) and any(
            isinstance(item, dict) and item.get("evidence_id") == rule["item_id"] for item in value
        )
    return value == rule.get("equals")


def _build_pack(case: dict[str, Any]) -> dict[str, Any]:
    event = case["event"]
    metadata = {
        "ingestion": {key: value for key, value in event.items() if key != "event_summary"},
        **case.get("metadata", {}),
    }
    state = AgentState(
        session_id=f"p2-1b-{case['case_id']}", plan_id="p2-1b-eval",
        event=event.get("event_summary", ""), metadata=metadata,
    )
    if "budget_chars" in case:
        metadata["harness_spec"] = {"context_policy": {"token_budget_hint": case["budget_chars"]}}
    return ContextPackRuntimeProvider().build_for_agent(state, case["agent_name"])


def evaluate(dataset_path: Path = DATASET, *, require_frozen_hash: bool = True) -> dict[str, Any]:
    raw = dataset_path.read_bytes()
    dataset_sha = canonical_text_sha256(raw)
    if require_frozen_hash and dataset_sha != FROZEN_SHA256:
        raise ValueError("P2.1b holdout SHA-256 mismatch")
    data = json.loads(raw.decode("utf-8"))

    memories = data["memories"]
    top_k = data["memory_top_k"]
    memory_rows = []
    total_relevant = total_hits = total_retrieved = fp_count = miss_count = 0
    reciprocal_rank = ranked_count = empty_count = empty_correct = 0
    for query in data["queries"]:
        expected = set(query["relevant_memory_ids"])
        ranked = retrieve_memories(query["query"], memories, top_k=top_k)
        actual = [item["memory_id"] for item in ranked]
        hits = expected.intersection(actual)
        first_relevant = next((i for i, item_id in enumerate(actual, start=1) if item_id in expected), None)
        total_relevant += len(expected)
        total_hits += len(hits)
        total_retrieved += len(actual)
        fp_count += len(set(actual) - expected)
        miss_count += len(expected - set(actual))
        if expected:
            ranked_count += 1
            reciprocal_rank += 1 / first_relevant if first_relevant else 0
        else:
            empty_count += 1
            empty_correct += int(not actual)
        memory_rows.append({
            "query_case_id": query["query_case_id"], "kind": query["kind"],
            "results": [{"memory_id": item["memory_id"], "rank": i, "score": item["score"],
                         "matched_reasons": item["matched_reasons"], "expected_relevant": item["memory_id"] in expected}
                        for i, item in enumerate(ranked, start=1)],
            "false_positive_ids": sorted(set(actual) - expected),
            "missed_relevant_ids": sorted(expected - set(actual)),
        })

    context_rows = []
    required_total = retained_total = previous_total = previous_retained = 0
    human_total = human_retained = evidence_total = evidence_retained = 0
    for case in data["context_cases"]:
        pack = _build_pack(case)
        checks = [{"path": rule["path"], "present": _required_present(pack, rule)} for rule in case["required"]]
        required_total += len(checks)
        retained_total += sum(item["present"] for item in checks)
        for item in checks:
            if item["path"].startswith("previous_observation."):
                previous_total += 1
                previous_retained += int(item["present"])
            if item["path"].startswith("human_fact_status."):
                human_total += 1
                human_retained += int(item["present"])
            if item["path"] == "top_legal_evidence":
                evidence_total += 1
                evidence_retained += int(item["present"])
        absent = [{"path": path, "absent": path not in pack} for path in case.get("absent", [])]
        text = json.dumps(pack, ensure_ascii=False, default=str)
        forbidden_found = bool(case.get("forbidden_text") and case["forbidden_text"] in text)
        budget_status = pack.get("budget_status")
        context_rows.append({
            "case_id": case["case_id"], "agent_name": case["agent_name"],
            "required_count": len(checks), "required_retained": sum(item["present"] for item in checks),
            "required_checks": checks, "absent_checks": absent,
            "forbidden_text_found": forbidden_found,
            "current_fact_status": pack.get("fact_status"),
            "human_verification_status": (pack.get("human_fact_status") or {}).get("verification_status"),
            "budget_chars": case.get("budget_chars"), "budget_status": budget_status,
            "budget_enforcement": pack.get("budget_enforcement"),
            "rendered_context_chars": pack.get("rendered_context_chars"),
            "content_chars": len(json.dumps({k: v for k, v in pack.items()
                                               if k not in {"rendered_context", "context_pack_hash"}},
                                             ensure_ascii=False, default=str)),
            "pack": pack,
        })

    return {
        "version": data["version"], "dataset_sha256": dataset_sha,
        "measurement_boundary": "deterministic memory retrieval and ContextPack construction from frozen AgentState fixtures; no Agent or Provider calls",
        "protection_snapshot": data["protection_snapshot"],
        "memory": {
            "sample_size": len(memory_rows), "memory_count": len(memories), "top_k": top_k,
            "recall_at_k": round(total_hits / total_relevant, 4) if total_relevant else None,
            "precision_at_k": round(total_hits / total_retrieved, 4) if total_retrieved else None,
            "mrr": round(reciprocal_rank / ranked_count, 4) if ranked_count else None,
            "false_positive_count": fp_count, "missed_relevant_count": miss_count,
            "empty_query_count": empty_count, "correct_empty_count": empty_correct,
            "queries": memory_rows,
        },
        "context_pack": {
            "sample_size": len(context_rows), "required_information_count": required_total,
            "required_information_retained": retained_total,
            "required_information_retention": round(retained_total / required_total, 4) if required_total else None,
            "previous_observation_count": previous_total, "previous_observation_retained": previous_retained,
            "human_fact_status_count": human_total, "human_fact_status_retained": human_retained,
            "legal_evidence_count": evidence_total, "legal_evidence_retained": evidence_retained,
            "budget_overflow_count": sum(row["budget_status"] != "WITHIN_BUDGET" for row in context_rows),
            "required_overflow_count": sum(row["budget_status"] == "REQUIRED_OVERFLOW" for row in context_rows),
            "human_asserted_boundary_preserved": all(
                row["human_verification_status"] == "human_asserted"
                for row in context_rows if row["case_id"] in {"b-fact-provided", "b-observation-human-fact-evidence"}
            ),
            "role_boundary_preserved": all(
                all(item["absent"] for item in row["absent_checks"])
                for row in context_rows if row["case_id"] == "b-writer-role-boundary"
            ),
            "forbidden_text_leaks": sum(row["forbidden_text_found"] for row in context_rows),
            "cases": context_rows,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--output", type=Path, default=REPORT)
    args = parser.parse_args()
    report = evaluate(args.dataset)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"P2.1b deterministic evaluation saved: {args.output}")


if __name__ == "__main__":
    main()
