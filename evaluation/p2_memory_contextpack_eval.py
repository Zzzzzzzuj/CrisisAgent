"""Offline P2 retrieval and safe-context measurements; never calls an Agent or Provider."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from backend.agents.context_pack import build_context_pack
from backend.agents.memory_retriever import retrieve_memories


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evaluation" / "p2_memory_contextpack_v1.json"
REPORT = ROOT / "evaluation" / "reports" / "p2_memory_contextpack_v1.json"
CONTENT_KEYS = (
    "event_facts", "risk_summary", "fact_status", "event_status", "risk_level",
    "top_public_signals", "top_alerts", "top_legal_evidence", "related_case_memories",
    "agent_specific_focus", "human_review_notes", "aggregate_summary",
)


def _content(pack: dict[str, Any]) -> dict[str, Any]:
    return {key: pack.get(key) for key in CONTENT_KEYS}


def _writer_prompt_measurement(pack: dict[str, Any], event: dict[str, Any]) -> dict[str, int]:
    from backend.agents.writer_agent import _build_context, _build_writer_prompt

    rendered = json.dumps(pack, ensure_ascii=False, default=str, separators=(",", ":"))
    payload = {
        "event": event["event_summary"],
        "sentiment_analysis": {"recommended_tone": "审慎"},
        "context_pack_text": rendered,
        "context_pack": pack,
    }
    context = _build_context(payload, rendered)
    prompt = _build_writer_prompt(payload, rendered, context)
    fixed_payload = {**payload, "event": "", "sentiment_analysis": "", "context_pack_text": ""}
    fixed_chars = len(_build_writer_prompt(fixed_payload, "", ""))
    case_chars = len(payload["event"]) + len(str(payload["sentiment_analysis"]))
    pack_occurrences = prompt.count(rendered)
    return {
        "prompt_characters": len(prompt),
        "instructions_and_labels_characters": fixed_chars,
        "current_case_characters": case_chars,
        "context_pack_characters_per_copy": len(rendered),
        "context_pack_occurrences": pack_occurrences,
        "context_pack_embedded_characters": len(rendered) * pack_occurrences,
        "legacy_context_characters": len(context),
        "other_characters": len(prompt) - fixed_chars - case_chars - len(rendered) * pack_occurrences,
    }


def _field_count(value: Any) -> int:
    if isinstance(value, dict):
        return sum(_field_count(item) for item in value.values())
    if isinstance(value, list):
        return sum(_field_count(item) for item in value)
    return int(value is not None and value != "")


def _required_present(pack: dict[str, Any], rule: dict[str, Any]) -> bool:
    value: Any = pack
    for key in rule["path"].split("."):
        if not isinstance(value, dict) or key not in value:
            return False
        value = value[key]
    if "item_id" in rule:
        return isinstance(value, list) and any(
            isinstance(item, dict) and item.get("evidence_id") == rule["item_id"]
            for item in value
        )
    if "contains" in rule:
        return isinstance(value, str) and rule["contains"] in value
    return value == rule.get("equals")


def evaluate(dataset_path: Path = DATASET) -> dict[str, Any]:
    raw = dataset_path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    memories = data["memories"]
    by_id = {item["memory_id"]: item for item in memories}
    top_k = data["memory_top_k"]

    retrieval_rows = []
    relevant_total = hit_total = retrieved_total = reciprocal_rank_total = 0
    ranked_query_count = empty_query_count = correct_empty_count = 0
    for case in data["queries"]:
        expected = set(case["relevant_memory_ids"])
        ranked = retrieve_memories(case["query"], memories, top_k=top_k)
        actual = [item["memory_id"] for item in ranked]
        hits = expected.intersection(actual)
        relevant_total += len(expected)
        hit_total += len(hits)
        retrieved_total += len(actual)
        first_relevant = next((rank for rank, memory_id in enumerate(actual, 1)
                               if memory_id in expected), None)
        if expected:
            ranked_query_count += 1
            reciprocal_rank_total += 1 / first_relevant if first_relevant else 0
        else:
            empty_query_count += 1
            correct_empty_count += int(not actual)
        retrieval_rows.append({
            "query_case_id": case["query_case_id"], "kind": case["kind"],
            "top_k": top_k, "judged_relevant_count": len(expected),
            "results": [{"memory_id": item["memory_id"], "rank": rank,
                         "score": item["score"], "expected_relevant": item["memory_id"] in expected}
                        for rank, item in enumerate(ranked, 1)],
            "false_positive_ids": [memory_id for memory_id in actual if memory_id not in expected],
            "missed_relevant_ids": sorted(expected.difference(actual)),
            "historical_fact_exposed": (
                case.get("historical_fact_memory_id") in actual
                if case["kind"] == "historical_fact_conflict" else None
            ),
        })

    conflict = next(case for case in data["queries"] if case["kind"] == "historical_fact_conflict")
    historical_id = conflict["historical_fact_memory_id"]
    probe_event = {
        "event_summary": "当前事件事实尚未确认。",
        "company": conflict["query"]["entity_name"], "crisis_type": conflict["query"]["crisis_type"],
        "risk_level": conflict["query"]["risk_level"], "fact_status": "unverified",
        "event_status": "uncertain", "risk_keywords": conflict["query"]["tags"],
    }
    on_pack = build_context_pack(event=probe_event, case_memories=memories,
                                 target_agent="writer", token_budget_hint=10000)
    off_pack = build_context_pack(event=probe_event, case_memories=[],
                                  target_agent="writer", token_budget_hint=10000)
    historical_summary = by_id[historical_id]["final_statement_summary"]
    on_content = json.dumps(_content(on_pack), ensure_ascii=False, sort_keys=True)
    off_content = json.dumps(_content(off_pack), ensure_ascii=False, sort_keys=True)
    historical_in_pack = next((item for item in on_pack["related_case_memories"]
                               if item.get("memory_id") == historical_id), None)
    injection_probe = {
        "mode": "EVALUATION_ONLY_INPUT_ABLATION_NOT_DOWNSTREAM_AB",
        "case_id": conflict["query_case_id"],
        "memory_on_ids": on_pack["selected_case_ids"],
        "memory_off_ids": off_pack["selected_case_ids"],
        "memory_on_characters": len(on_content), "memory_off_characters": len(off_content),
        "historical_confirmed_statement_visible_on": historical_summary in on_content,
        "historical_confirmed_statement_visible_off": historical_summary in off_content,
        "current_fact_status_on": on_pack["fact_status"],
        "current_fact_status_off": off_pack["fact_status"],
        "historical_provenance_preserved": bool(
            historical_in_pack and historical_in_pack.get("historical_experience") is True
            and historical_in_pack.get("source_case_id")
            and historical_in_pack.get("historical_fact_status") == "verified"
            and "fact_status" not in historical_in_pack
        ),
        "agent_output_evaluated": False,
    }

    pack_rows = []
    reference_chars = current_chars = required_total = required_retained = 0
    for case in data["context_cases"]:
        selected_memories = [by_id[memory_id] for memory_id in case.get("memory_ids", [])]
        arguments = dict(
            event=case["event"], public_signals=case.get("public_signals", []),
            legal_evidence=case.get("legal_evidence", []), case_memories=selected_memories,
            target_agent=case["target_agent"], token_budget_hint=case["budget_chars"],
        )
        reference = build_context_pack(**arguments, compression_mode="off")
        current = build_context_pack(**arguments)
        ref_content = _content(reference)
        current_content = _content(current)
        ref_chars = len(json.dumps(ref_content, ensure_ascii=False, sort_keys=True))
        cur_chars = len(json.dumps(current_content, ensure_ascii=False, sort_keys=True))
        reference_chars += ref_chars
        current_chars += cur_chars
        retained = sum(_required_present(current, rule) for rule in case["required"])
        required_total += len(case["required"])
        required_retained += retained
        row = {
            "case_id": case["case_id"], "target_agent": case["target_agent"],
            "budget_unit": "characters", "budget": case["budget_chars"],
            "safe_reference_characters": ref_chars, "current_characters": cur_chars,
            "character_reduction_ratio": round(1 - cur_chars / ref_chars, 4) if ref_chars else 0.0,
            "available_field_count": _field_count(ref_content),
            "included_field_count": _field_count(current_content),
            "required_count": len(case["required"]), "required_retained": retained,
            "required_field_recall": round(retained / len(case["required"]), 4),
            "compression_level": current["compression_level"],
            "over_budget": cur_chars > case["budget_chars"],
            "budget_status": current.get("budget_status"),
            "budget_enforcement": current.get("budget_enforcement"),
            "rendered_context_chars": current.get("rendered_context_chars"),
            "truncated": bool(current["dropped_fields"] or current["compression_level"] in {"yellow", "orange", "red"}),
            "optional_dropped": current["dropped_fields"],
            "selected_memory_ids": current["selected_case_ids"],
        }
        if case["target_agent"] == "writer":
            reference_breakdown = _writer_prompt_measurement(reference, case["event"])
            current_breakdown = _writer_prompt_measurement(current, case["event"])
            reference_prompt_chars = reference_breakdown["prompt_characters"]
            current_prompt_chars = current_breakdown["prompt_characters"]
            row["safe_reference_writer_prompt_characters"] = reference_prompt_chars
            row["current_writer_prompt_characters"] = current_prompt_chars
            row["writer_prompt_character_reduction_ratio"] = round(
                1 - current_prompt_chars / reference_prompt_chars, 4
            )
            row["safe_reference_prompt_breakdown"] = reference_breakdown
            row["current_prompt_breakdown"] = current_breakdown
        pack_rows.append(row)

    return {
        "version": data["version"], "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "measurement_boundary": "synthetic offline retrieval, content sections, and Writer prompt construction; no Agent output",
        "memory": {
            "sample_size": len(data["queries"]), "memory_count": len(memories), "top_k": top_k,
            "recall_at_k": round(hit_total / relevant_total, 4) if relevant_total else None,
            "precision_at_k": round(hit_total / retrieved_total, 4) if retrieved_total else None,
            "mrr": round(reciprocal_rank_total / ranked_query_count, 4) if ranked_query_count else None,
            "empty_query_count": empty_query_count, "correct_empty_count": correct_empty_count,
            "false_positive_count": retrieved_total - hit_total,
            "missed_relevant_count": relevant_total - hit_total,
            "queries": retrieval_rows,
            "injection_probe": injection_probe,
            "historical_fact_transfer": "NOT_EVALUATED_NO_GENERATED_OUTPUT",
            "unsupported_current_fact": "NOT_EVALUATED_NO_GENERATED_OUTPUT",
        },
        "context_pack": {
            "sample_size": len(pack_rows), "safe_reference_characters": reference_chars,
            "current_characters": current_chars,
            "character_reduction_ratio": round(1 - current_chars / reference_chars, 4) if reference_chars else 0.0,
            "required_count": required_total, "required_retained": required_retained,
            "required_field_recall": round(required_retained / required_total, 4) if required_total else None,
            "budget_overflow_count": sum(row["budget_status"] != "WITHIN_BUDGET" for row in pack_rows),
            "required_overflow_count": sum(row["budget_status"] == "REQUIRED_OVERFLOW" for row in pack_rows),
            "cases": pack_rows,
            "provider_input_tokens": None, "provider_output_tokens": None,
            "downstream_quality": "NOT_EVALUATED", "cost": "NOT_AVAILABLE",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--output", type=Path, default=REPORT)
    arguments = parser.parse_args()
    report = evaluate(arguments.dataset)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"P2 offline evaluation saved: {arguments.output}")


if __name__ == "__main__":
    main()
