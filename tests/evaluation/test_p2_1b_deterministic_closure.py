import json
from pathlib import Path

from evaluation.frozen_hash import canonical_text_sha256
from evaluation.p2_1b_deterministic_closure_eval import evaluate


HOLDOUT = Path("evaluation/p2_1b_deterministic_closure_holdout.json")
BEFORE_FIXTURE = Path("evaluation/p2_1b_legacy_context_baseline.json")
FROZEN_SHA256 = "9f61a24c2ae4a47bef44cb5320090fdb78e19f48c94939a75e817b5137393370"


def test_p2_1b_holdout_is_frozen_and_covers_requested_scenarios():
    raw = HOLDOUT.read_bytes()
    assert canonical_text_sha256(raw) == FROZEN_SHA256
    data = json.loads(raw.decode("utf-8"))
    assert len(data["queries"]) == 6
    assert len(data["context_cases"]) == 7
    assert data["protection_snapshot"]["tracked_diff_before_production_edit"] == ""


def test_frozen_before_report_records_provider_resume_state_gap():
    before = json.loads(BEFORE_FIXTURE.read_text(encoding="utf-8"))
    assert before["dataset_sha256"] == FROZEN_SHA256
    assert before["context_pack"]["previous_observation_retained"] == 0
    assert before["context_pack"]["human_fact_status_retained"] == 0


def test_current_provider_retains_resume_state():
    report = evaluate(require_frozen_hash=True)
    assert report["dataset_sha256"] == FROZEN_SHA256
    assert report["context_pack"]["previous_observation_retained"] == 8
    assert report["context_pack"]["human_fact_status_retained"] == 7


def test_p2_1b_memory_anchor_rejects_single_tag_neighbors_and_keeps_relevant_hits():
    report = evaluate(require_frozen_hash=True)
    memory = report["memory"]
    assert memory["recall_at_k"] == 1.0
    assert memory["precision_at_k"] == 1.0
    assert memory["mrr"] == 1.0
    assert memory["false_positive_count"] == 0
    assert memory["missed_relevant_count"] == 0
    assert memory["correct_empty_count"] == memory["empty_query_count"] == 4


def test_runtime_context_pack_preserves_bounded_resume_state_only_for_legal():
    report = evaluate(require_frozen_hash=True)
    pack = report["context_pack"]
    assert pack["required_information_retention"] == 1.0
    assert pack["previous_observation_retained"] == pack["previous_observation_count"]
    assert pack["human_fact_status_retained"] == pack["human_fact_status_count"]
    assert pack["legal_evidence_retained"] == pack["legal_evidence_count"]
    assert pack["human_asserted_boundary_preserved"] is True
    assert pack["role_boundary_preserved"] is True
    assert pack["forbidden_text_leaks"] == 0
    assert all(row["current_fact_status"] == "unverified" for row in pack["cases"])
    crowded = next(row for row in pack["cases"] if row["case_id"] == "b-crowded-required-state")
    assert crowded["budget_status"] == "REQUIRED_OVERFLOW"
    assert crowded["pack"]["human_fact_status"]["verification_status"] == "unresolved"


def test_runtime_provider_drops_unrecognized_free_text_observation_values():
    from backend.core.context_pack_runtime import _safe_observation, _safe_human_fact_status

    assert _safe_observation({"observation_type": "secret body", "status": "do not expose"}) is None
    assert _safe_human_fact_status({
        "request": {"claim_index": 0},
        "response": {"response_type": "FACT_PROVIDED", "fact_text": "private body"},
        "observation": {"source": "private body", "verification_status": "private body"},
    }) == {"response_type": "FACT_PROVIDED", "claim_index": 0,
          "source": "human_provided", "verification_status": "human_asserted"}
    assert _safe_human_fact_status({
        "request": {"claim_index": 1},
        "response": {"response_type": "FACT_PROVIDED", "fact_text": "private body"},
        "observation": {"source": "human_provided", "verification_status": "independently_verified"},
    }) == {"response_type": "FACT_PROVIDED", "claim_index": 1,
          "source": "human_provided", "verification_status": "human_asserted"}
