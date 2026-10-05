import hashlib
import json

from backend.agents import context_pack
from evaluation import p2_3b_retrieval_qualified_eval as runner


def _data():
    raw = runner.DATASET.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == runner.FROZEN_SHA256
    return json.loads(raw.decode("utf-8"))


def test_holdout_is_frozen_and_uses_new_case_ids():
    data = _data()
    assert [case["case_id"] for case in data["cases"]] == ["G1", "G2", "G3"]
    assert data["parent_p2_3_sha256"] == "2485f1b5fcae1ad7b9d0266453ea387bb63be673e921e29467a0dab6fe6c076a"
    assert all(case["expected_memory_id"] and case["allowed_assertions"] and case["prohibited_assertions"] for case in data["cases"])


def test_production_retriever_qualifies_each_frozen_expected_memory():
    data = _data()
    rows = runner.qualify_cases(data)
    assert len(rows) == 3
    assert all(row["qualification_status"] == "QUALIFIED" for row in rows)
    assert all(row["expected_memory_retrieved"] for row in rows)
    assert all(row["historical_marker_present"] and row["source_case_id_present"] for row in rows)
    assert all(row["retrieval_score"] is not None for row in rows)
    for case, row in zip(data["cases"], rows):
        actual = context_pack.retrieve_memories(case["event"], case["memories"], top_k=data["memory_top_k"])
        assert row["retrieved_memory_ids"] == [memory["memory_id"] for memory in actual]


def test_memory_off_and_on_use_same_case_and_only_change_memory_input():
    case = _data()["cases"][0]
    off_prompt, off_pack = runner.build_prompt(case, memory_enabled=False)
    on_prompt, on_pack = runner.build_prompt(case, memory_enabled=True)
    assert off_pack["event_facts"] == on_pack["event_facts"]
    assert off_pack["fact_status"] == on_pack["fact_status"]
    assert off_pack["target_agent"] == on_pack["target_agent"]
    assert off_pack["selected_case_ids"] == []
    assert on_pack["selected_case_ids"] == [case["expected_memory_id"]]
    assert off_prompt != on_prompt


def test_g2_keeps_current_unverified_fact_separate_from_historical_confirmed_fact():
    case = _data()["cases"][1]
    assert case["current_facts"]["fact_status"] == "unverified"
    memory = case["memories"][0]
    assert memory["historical_fact_status"] == "verified"
    prompt, pack = runner.build_prompt(case, memory_enabled=True)
    assert pack["fact_status"] == "unverified"
    assert pack["related_case_memories"][0]["historical_fact_status"] == "verified"
    assert "不得将历史案例中的事实或已执行动作写成当前 Case 的事实" in prompt


def test_g3_preserves_human_asserted_provenance_with_memory_on_and_off():
    case = _data()["cases"][2]
    off_prompt, off_pack = runner.build_prompt(case, memory_enabled=False)
    on_prompt, on_pack = runner.build_prompt(case, memory_enabled=True)
    for prompt, pack in ((off_prompt, off_pack), (on_prompt, on_pack)):
        assert pack["human_fact_status"]["verification_status"] == "human_asserted"
        assert '"verification_status":"human_asserted"' in prompt
        assert "不得表述为独立核实结论" in prompt
    assert off_pack["human_fact_status"] == on_pack["human_fact_status"]
    assert on_pack["selected_case_ids"] == [case["expected_memory_id"]]


def test_qualification_does_not_mutate_frozen_case_or_expected_labels():
    data = _data()
    before = json.dumps(data, ensure_ascii=False, sort_keys=True)
    runner.qualify_cases(data)
    assert json.dumps(data, ensure_ascii=False, sort_keys=True) == before


def test_inadequate_qualification_threshold_stops_before_provider_preflight():
    rows = [
        {"case_id": "G1", "qualification_status": "NOT_QUALIFIED_FOR_GENERATION_EVIDENCE"},
        {"case_id": "G2", "qualification_status": "QUALIFIED"},
    ]
    qualified_ids = {row["case_id"] for row in rows if row["qualification_status"] == "QUALIFIED"}
    assert len(qualified_ids) < 2
