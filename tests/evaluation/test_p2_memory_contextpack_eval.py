from copy import deepcopy

from backend.agents.context_pack import build_context_pack
from evaluation.p2_memory_contextpack_eval import DATASET, evaluate


def test_frozen_memory_retrieval_metrics_are_small_sample_not_downstream_value():
    report = evaluate()
    memory = report["memory"]
    assert report["dataset_sha256"]
    assert memory["sample_size"] == 5
    assert memory["memory_count"] == 6
    assert memory["top_k"] == 2
    assert memory["recall_at_k"] == 1.0
    assert memory["precision_at_k"] == 0.625
    assert memory["mrr"] == 1.0
    assert memory["false_positive_count"] == 3
    assert memory["missed_relevant_count"] == 0
    assert memory["historical_fact_transfer"] == "NOT_EVALUATED_NO_GENERATED_OUTPUT"


def test_conflicting_historical_fact_is_exposed_but_not_relabelled_as_current_fact():
    report = evaluate()
    conflict = next(row for row in report["memory"]["queries"]
                    if row["kind"] == "historical_fact_conflict")
    probe = report["memory"]["injection_probe"]
    assert conflict["historical_fact_exposed"] is True
    assert probe["historical_confirmed_statement_visible_on"] is True
    assert probe["historical_confirmed_statement_visible_off"] is False
    assert probe["current_fact_status_on"] == probe["current_fact_status_off"] == "unverified"
    assert probe["historical_provenance_preserved"] is True
    assert probe["agent_output_evaluated"] is False


def test_safe_reference_and_current_pack_measure_character_loss_without_token_claim():
    report = evaluate()
    pack = report["context_pack"]
    assert pack["sample_size"] == 3
    assert pack["required_count"] == 11
    assert pack["required_retained"] == 10
    assert pack["required_field_recall"] == 0.9091
    assert pack["character_reduction_ratio"] == 0.1282
    assert pack["provider_input_tokens"] is None
    crowded = next(row for row in pack["cases"] if row["case_id"] == "pack-legal-crowded")
    assert crowded["required_retained"] == 3
    assert crowded["over_budget"] is True
    assert crowded["compression_level"] == "red"
    writer = next(row for row in pack["cases"] if row["case_id"] == "pack-writer-memory")
    assert writer["current_writer_prompt_characters"] > writer["current_characters"]
    assert writer["writer_prompt_character_reduction_ratio"] < 0
    assert writer["current_prompt_breakdown"]["context_pack_occurrences"] == 1


def test_safe_reference_does_not_reintroduce_forbidden_fields():
    import json

    data = json.loads(DATASET.read_text(encoding="utf-8"))
    case = deepcopy(data["context_cases"][0])
    case["legal_evidence"][0]["system_prompt"] = "DO_NOT_INCLUDE_THIS_SENTINEL"
    for mode in ("off", "auto"):
        pack = build_context_pack(
            event=case["event"], legal_evidence=case["legal_evidence"],
            target_agent="legal", token_budget_hint=case["budget_chars"],
            compression_mode=mode,
        )
        assert "DO_NOT_INCLUDE_THIS_SENTINEL" not in str(pack)
        assert pack["agent_specific_focus"]["target_agent"] == "legal"
