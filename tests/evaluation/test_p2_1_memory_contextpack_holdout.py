import hashlib
import json

from backend.agents.context_pack import build_context_pack
from evaluation.p2_memory_contextpack_eval import evaluate


HOLDOUT = "evaluation/p2_1_memory_contextpack_holdout.json"
FROZEN_SHA256 = "37c98aaa9ec1d3ffe0b8f66950decfd8005becbb00b2383a9fb8e7eab9c66083"


def _dataset():
    from pathlib import Path

    raw = Path(HOLDOUT).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FROZEN_SHA256
    return json.loads(raw.decode("utf-8"))


def test_holdout_retrieval_abstains_without_erasing_relevant_matches():
    from pathlib import Path

    report = evaluate(Path(HOLDOUT))
    memory = report["memory"]
    assert memory["sample_size"] == 8
    assert memory["recall_at_k"] == 1.0
    assert memory["precision_at_k"] == 1.0
    assert memory["false_positive_count"] == 0
    assert memory["missed_relevant_count"] == 0
    assert memory["correct_empty_count"] == 3
    assert memory["empty_query_count"] == 3
    assert memory["injection_probe"]["historical_provenance_preserved"] is True


def test_holdout_required_legal_evidence_beats_optional_evidence():
    data = _dataset()
    for case_id in ("h-legal-required", "h-multi-required-evidence", "h-required-optional-competition"):
        case = next(item for item in data["context_cases"] if item["case_id"] == case_id)
        pack = build_context_pack(
            event=case["event"], legal_evidence=case["legal_evidence"],
            target_agent=case["target_agent"], token_budget_hint=case["budget_chars"],
        )
        actual = {item["evidence_id"] for item in pack["top_legal_evidence"]}
        required = {item["evidence_id"] for item in case["legal_evidence"]
                    if item.get("required_for_decision") is True}
        assert required <= actual
        assert pack["budget_enforcement"] == "soft_waterline"
        assert pack["budget_unit"] == "characters"


def test_tiny_budget_reports_required_overflow_without_dropping_required_items():
    data = _dataset()
    case = next(item for item in data["context_cases"] if item["case_id"] == "h-tiny-budget")
    pack = build_context_pack(event=case["event"], legal_evidence=case["legal_evidence"],
                              target_agent="legal", token_budget_hint=case["budget_chars"])
    assert pack["budget_status"] == "REQUIRED_OVERFLOW"
    assert pack["required_minimum_chars"] > case["budget_chars"]
    assert pack["top_legal_evidence"][0]["evidence_id"] == "h-tiny-required"


def test_explicitly_required_evidence_text_is_not_silently_preview_truncated():
    required_text = "必要规则" * 200
    pack = build_context_pack(
        event={"event_summary": "事实待核查", "fact_status": "unverified"},
        legal_evidence=[{"evidence_id": "long-required", "required_for_decision": True,
                         "relevance_score": 0.8, "text": required_text}],
        target_agent="legal", token_budget_hint=100,
    )
    assert pack["top_legal_evidence"][0]["text"] == required_text
    assert pack["budget_status"] == "REQUIRED_OVERFLOW"


def test_historical_experience_has_provenance_and_cannot_replace_current_fact_status():
    data = _dataset()
    case = next(item for item in data["context_cases"] if item["case_id"] == "h-memory-current-fact")
    memory = next(item for item in data["memories"] if item["memory_id"] == "h-food-other")
    pack = build_context_pack(event=case["event"], case_memories=[memory],
                              target_agent="writer", token_budget_hint=case["budget_chars"])
    assert pack["fact_status"] == "unverified"
    historical = pack["related_case_memories"][0]
    assert historical["historical_experience"] is True
    assert historical["source_case_id"] == "historical-other"
    assert historical["historical_fact_status"] == "verified"
    assert "fact_status" not in historical
    assert pack["agent_specific_focus"]["historical_source_case_ids"] == ["historical-other"]


def test_holdout_reports_unavailable_runtime_observation_fields_without_inventing_them():
    from pathlib import Path

    report = evaluate(Path(HOLDOUT))
    case = next(row for row in report["context_pack"]["cases"]
                if row["case_id"] == "h-observation-human-evidence")
    assert case["required_retained"] == 2
    assert case["required_count"] == 4
    writer = next(row for row in report["context_pack"]["cases"]
                  if row["case_id"] == "h-writer-crowded")
    assert writer["current_prompt_breakdown"]["context_pack_occurrences"] == 1
