import hashlib
import json
from pathlib import Path

import pytest

from evaluation import p2_2_real_provider_eval as p2


def test_holdout_hash_is_checked_before_any_provider_request(monkeypatch, tmp_path):
    dataset = json.loads(p2.DATASET.read_text(encoding="utf-8"))
    path = tmp_path / "mutated.json"
    path.write_text(json.dumps(dataset, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(p2, "validate_provider_config", lambda: pytest.fail("preflight should not run"))
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        p2.run(path)


def test_memory_conditions_change_only_memory_input():
    dataset = json.loads(p2.DATASET.read_text(encoding="utf-8"))
    case = dataset["memory_cases"][0]
    selected = p2.context_pack.retrieve_memories(case["event"], case["memories"], top_k=dataset["memory_top_k"])
    on_payload, on_pack = p2._build_writer_payload(case, selected)
    off_payload, off_pack = p2._build_writer_payload(case, [])
    assert on_payload["event"] == off_payload["event"]
    assert on_payload["sentiment_analysis"] == off_payload["sentiment_analysis"]
    assert on_pack["fact_status"] == off_pack["fact_status"] == "unverified"
    assert on_pack["selected_case_ids"] != off_pack["selected_case_ids"]


def test_context_pair_keeps_legal_role_and_resume_verification_boundary():
    dataset = json.loads(p2.DATASET.read_text(encoding="utf-8"))
    case = next(item for item in dataset["context_cases"] if item["case_type"] == "human_fact_resume")
    ref_payload, ref_pack = p2._build_legal_payload(case, safe_reference=True)
    current_payload, current_pack = p2._build_legal_payload(case, safe_reference=False)
    assert ref_payload["event"] == current_payload["event"]
    assert ref_pack["target_agent"] == current_pack["target_agent"] == "legal"
    for pack in (ref_pack, current_pack):
        assert pack["human_fact_status"]["verification_status"] == "human_asserted"
        assert pack["previous_observation"]["verification_status"] == "human_asserted"


def test_report_never_uses_client_estimated_tokens_as_provider_usage():
    # The report contract intentionally stores null token metrics; no chars/4 estimate is accepted.
    source = Path(p2.__file__).read_text(encoding="utf-8")
    assert '"input_tokens": None, "output_tokens": None, "total_tokens": None' in source
    assert "estimated_tokens" in source
    assert "provider_usage_raw_available\": False" in source
