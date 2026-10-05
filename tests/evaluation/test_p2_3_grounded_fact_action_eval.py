import json
from pathlib import Path

from backend.agents import context_pack, writer_agent
from evaluation.frozen_hash import canonical_text_sha256
from evaluation import p2_3_grounded_fact_action_eval as eval_runner


def _dataset():
    raw = eval_runner.DATASET.read_bytes()
    assert canonical_text_sha256(raw) == eval_runner.FROZEN_SHA256
    return json.loads(raw.decode("utf-8"))


def test_frozen_replay_contains_three_bad_cases_and_six_holdouts():
    cases = _dataset()["cases"]
    assert [case["case_id"] for case in cases] == [
        "BC-01", "BC-02", "BC-03", "HC-01", "HC-02", "HC-03", "HC-04", "HC-05", "HC-06"
    ]
    assert all(case["allowed_assertions"] and case["prohibited_assertions"] for case in cases)


def test_memory_cases_use_existing_retrieval_and_keep_historical_provenance():
    case = _dataset()["cases"][0]
    selected = context_pack.retrieve_memories(case["event"], case["memories"], top_k=3)
    assert [item["memory_id"] for item in selected] == ["p22-mem-relevant-01"]
    prompt, pack, role = eval_runner._build_case_prompt(case)
    assert role == "writer"
    memory = pack["related_case_memories"][0]
    assert memory["historical_experience"] is True
    assert memory["source_case_id"] == "p22-historical-food-a"
    assert memory["historical_fact_status"] == "verified"
    assert "历史经验仅供参考处理策略" in prompt


def test_writer_prompts_separate_recommendation_from_confirmed_action():
    case = _dataset()["cases"][3]
    prompt, _, role = eval_runner._build_case_prompt(case)
    v2_prompt = writer_agent._build_writer_v2_prompt({"event": case["event"]["event_summary"]})
    assert role == "writer"
    for text in (prompt, v2_prompt):
        assert "建议" in text
        assert "不得" in text and ("已执行" in text or "已经" in text)
        assert "历史" in text
    assert "不得将历史案例中的事实或已执行动作写成当前 Case 的事实" in prompt
    assert "建议不等于已执行" in v2_prompt


def test_recommendation_remains_allowed_when_no_action_is_confirmed():
    case = _dataset()["cases"][6]
    prompt, _, role = eval_runner._build_case_prompt(case)
    assert role == "writer"
    assert "建议立即开展内部核查" in case["allowed_assertions"]
    assert "我们已经开展内部核查" in case["prohibited_assertions"]
    assert "可以建议立即调查、核查或排查" in prompt


def test_legal_prompt_preserves_human_asserted_and_unavailable_boundaries():
    data = _dataset()
    provided, provided_pack, role = eval_runner._build_case_prompt(data["cases"][5])
    unavailable, unavailable_pack, unavailable_role = eval_runner._build_case_prompt(data["cases"][8])
    assert role == unavailable_role == "legal"
    assert provided_pack["human_fact_status"]["verification_status"] == "human_asserted"
    assert unavailable_pack["human_fact_status"]["verification_status"] == "unresolved"
    assert "human_asserted" in provided
    assert "FACT_UNAVAILABLE" in unavailable
    assert "不得称为 independently verified" in provided


def test_p2_1b_required_context_state_and_role_boundary_remain():
    data = _dataset()
    prompt, pack, role = eval_runner._build_case_prompt(data["cases"][5])
    assert role == "legal"
    assert pack["target_agent"] == "legal"
    assert pack["fact_status"] == "unverified"
    assert "human_fact_status" in prompt
    assert "response" not in pack["human_fact_status"]


def test_memory_off_keeps_normal_action_recommendation_prompt_path():
    case = _dataset()["cases"][6]
    prompt, pack, role = eval_runner._build_case_prompt(case)
    assert role == "writer"
    assert pack["related_case_memories"] == []
    assert "可以建议立即调查、核查或排查" in prompt


def test_p2_2_eval_runner_is_not_invoked_by_p2_3_tests():
    assert Path(eval_runner.DATASET).exists()
    assert eval_runner.FROZEN_SHA256 == canonical_text_sha256(Path(eval_runner.DATASET).read_bytes())
