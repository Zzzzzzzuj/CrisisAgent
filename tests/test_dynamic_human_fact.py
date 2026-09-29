import asyncio

import httpx
import pytest

from backend.agents.legal_claim_coverage import build_claim_coverage
from backend.agents.legal_claim_extractor import extract_claims
from backend.agents.legal_targeted_search import run_legal_action_loop
from backend.core import checkpoint, dynamic_runtime, executor, human_fact_resume
from backend.core.human_fact_runtime import FACT_INPUT, PHASE_RESPONSE_RECORDED, record_response, revision_is_safe
from backend.main import app


DRAFT = "经调查，本批次不存在使用过期原料的情况。"
EVENT = "某食品品牌被曝使用过期原料，相关视频正在传播，企业内部调查尚未完成。"


def _request(method, path, body=None):
    async def send():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.request(method, path, json=body)
    return asyncio.run(send())


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("AGENT_MODE", "mock")
    monkeypatch.setenv("RUNTIME_MODE", "sync")
    monkeypatch.setattr(checkpoint, "CHECKPOINT_PATH", tmp_path / "checkpoints.json")
    calls = {name: 0 for name in ("sentiment", "writer", "redteam", "legal", "writer_v2", "decision")}
    revision = {"statement": "公司已启动专项核查，目前相关事实仍在进一步确认。"}
    writer_output = {"statement": DRAFT}

    def legal(payload):
        calls["legal"] += 1
        extraction = extract_claims(
            payload["draft"], "mock", event=payload["event"],
            risk_level=(payload.get("sentiment_analysis") or {}).get("risk_level"),
        )
        relation = {"legal_claim_relations": [], "relation_status": "skipped"}
        coverage = build_claim_coverage(extraction["legal_claims"], relation)
        rag = {"retrieval_status": "disabled", "retrieval_executed": False}
        loop = run_legal_action_loop(
            extraction, coverage, relation, rag,
            retrieve_call=lambda *_args, **_kwargs: pytest.fail("case-fact gap must not call Legal RAG"),
        )
        actions = loop["claim_action_recommendation"]
        return {"review_summary": "事实待核查", "_metadata": {"claim_extraction": extraction,
                "claim_coverage": loop["claim_coverage"], "claim_action_recommendation": actions,
                "claim_evidence_relation": loop["claim_evidence_relation"], "legal_action_loop": loop}}

    def simple(name, result):
        def runner(_payload):
            calls[name] += 1
            return result
        return runner

    def writer_v2(payload):
        calls["writer_v2"] += 1
        assert payload["human_fact_revision"]["target_claim"] == revision.get("expected_claim", DRAFT.rstrip("。"))
        assert payload["human_fact_revision"]["fact_currently_unavailable"] is True
        return {"statement": revision["statement"]}

    registry = {
        "sentiment": simple("sentiment", {"risk_level": "high"}),
        "writer": simple("writer", writer_output),
        "redteam": simple("redteam", {"attack_summary": "待核实"}),
        "legal": legal,
        "writer_v2": writer_v2,
        "decision": simple("decision", {"final_statement": "草稿", "scores": {"legal_safety": 8, "empathy": 8, "robustness": 8}}),
    }
    monkeypatch.setattr(dynamic_runtime, "_build_runtime_registry", lambda: registry)
    monkeypatch.setattr(human_fact_resume, "_build_runtime_registry", lambda: registry)
    monkeypatch.setattr(executor._CONTEXT_PACK_PROVIDER, "build_for_agent", lambda *_: None)
    monkeypatch.setattr(executor._SKILL_SELECTOR, "select_and_execute", lambda *_: {"results": []})
    revision["writer_output"] = writer_output
    return calls, revision


def _start():
    response = _request("POST", "/api/dynamic/run", {"event": EVENT})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "waiting_human"
    assert body["state_status"] == "WAITING_HUMAN"
    return body


def test_pause_after_legal_and_resume_unavailable_without_replaying(runtime):
    calls, _ = runtime
    started = _start()
    request = started["human_fact_request"]
    assert request["claim_index"] == 0
    assert request["status"] == "pending"
    assert started["legal_action_loop"]["phase"] == "WAITING_HUMAN"
    assert started["legal_action_loop"]["actions"][-1]["selected_action"] == "REQUEST_HUMAN_FACT"
    assert calls == {"sentiment": 1, "writer": 1, "redteam": 1, "legal": 1, "writer_v2": 0, "decision": 0}
    session_id = started["session_id"]
    saved = checkpoint.load_checkpoint(session_id)
    assert saved.metadata["human_fact"]["draft"] == DRAFT
    assert saved.metadata["legal_action_loop"]["phase"] == "WAITING_HUMAN"
    assert saved.metadata["legal_action_loop"]["current_gap"]["claim_index"] == 0
    assert [step["agent"] for step in saved.metadata["human_fact"]["remaining_plan"]] == ["writer_v2", "decision"]
    response = _request("POST", f"/api/dynamic/{session_id}/fact-response",
                        {"request_id": request["request_id"], "response_type": "FACT_UNAVAILABLE"})
    assert response.status_code == 200, response.text
    after = checkpoint.load_checkpoint(session_id)
    assert after.metadata["human_fact"]["observation"] == {
        "case_fact_status": "unresolved", "human_verification_attempted": True,
        "fact_currently_unavailable": True}
    assert after.metadata["legal_action_loop"]["last_observation"]["observation_type"] == "fact_unavailable"
    assert after.metadata["legal_action_loop"]["next_action"] == "STOP_UNRESOLVED"
    assert after.metadata["legal_action_loop"]["stop_reason"] == "Human review required: high_risk"
    assert calls == {"sentiment": 1, "writer": 1, "redteam": 1, "legal": 1, "writer_v2": 1, "decision": 1}
    assert [item["action"] for item in after.trace if item.get("agent") == "human_fact"] == [
        "REQUEST_HUMAN_FACT_VERIFICATION", "HUMAN_FACT_RESPONSE", "REVISE_UNVERIFIED_CLAIM", "CONTINUE"]
    assert response.json()["stopped_reason"] in {"review_required", "unsupported_claim_removed", "Human review required: high_risk"}
    duplicate = _request("POST", f"/api/dynamic/{session_id}/fact-response",
                         {"request_id": request["request_id"], "response_type": "FACT_UNAVAILABLE"})
    assert duplicate.status_code == 400


def test_data_privacy_event_gap_enters_existing_fact_loop(runtime):
    calls, revision = runtime
    revision["expected_claim"] = "数据是否真实泄露、涉及多少用户以及泄露原因"
    revision["writer_output"]["statement"] = (
        "我们已关注到相关反馈，公司已启动内部核查程序，将及时同步调查进展。"
    )
    event = (
        "某互联网平台被网友曝光疑似存在用户数据泄露。社交平台流传包含用户手机号和订单信息的截图。"
        "目前尚未确认数据是否真实泄露、涉及多少用户以及泄露原因。"
    )
    response = _request("POST", "/api/dynamic/run", {"event": event})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state_status"] == "WAITING_HUMAN"
    request = body["human_fact_request"]
    assert request["claim"] == "数据是否真实泄露、涉及多少用户以及泄露原因"
    assert request["status"] == "pending"
    state = checkpoint.load_checkpoint(body["session_id"])
    assert state.metadata["legal_claim_extraction"]["legal_claims"][0]["claim_origin"] == "event_fact_gap"
    assert state.metadata["legal_claim_coverage"]["claim_coverage"][0]["case_fact_status"] == "unresolved"
    unavailable = _request("POST", f"/api/dynamic/{body['session_id']}/fact-response",
                            {"request_id": request["request_id"], "response_type": "FACT_UNAVAILABLE"})
    assert unavailable.status_code == 200, unavailable.text
    state = checkpoint.load_checkpoint(body["session_id"])
    assert state.metadata["human_fact"]["observation"]["fact_currently_unavailable"] is True
    assert calls["writer_v2"] == 1


def test_data_privacy_fact_provided_stays_human_asserted(runtime):
    calls, revision = runtime
    revision["writer_output"]["statement"] = "我们已关注到相关反馈，并将及时同步调查进展。"
    event = (
        "某互联网平台被网友曝光疑似存在用户数据泄露。社交平台流传包含用户手机号和订单信息的截图。"
        "目前尚未确认数据是否真实泄露、涉及多少用户以及泄露原因。"
    )
    started = _request("POST", "/api/dynamic/run", {"event": event}).json()
    request = started["human_fact_request"]
    provided = _request("POST", f"/api/dynamic/{started['session_id']}/fact-response", {
        "request_id": request["request_id"],
        "response_type": "FACT_PROVIDED",
        "fact_text": "内部调查人员提供了一份待复核说明。",
    })
    assert provided.status_code == 200, provided.text
    state = checkpoint.load_checkpoint(started["session_id"])
    observation = state.metadata["human_fact"]["observation"]
    assert observation["case_fact_status"] == "unresolved"
    assert observation["verification_status"] == "human_asserted"
    assert observation["source"] == "human_provided"
    assert state.metadata["human_wait_type"] == "FINAL_REVIEW"
    assert state.metadata["legal_action_loop"]["last_observation"]["observation_type"] == "fact_provided"
    assert state.metadata["legal_action_loop"]["next_action"] == "STOP_UNRESOLVED"
    assert calls["writer_v2"] == 0


def test_revision_with_paraphrased_assertion_stops_once(runtime):
    calls, revision = runtime
    revision["statement"] = "经核实，本批次没有使用过期原料。"
    started = _start()
    response = _request("POST", f"/api/dynamic/{started['session_id']}/fact-response",
                        {"request_id": started["human_fact_request"]["request_id"], "response_type": "FACT_UNAVAILABLE"})
    assert response.status_code == 200
    state = checkpoint.load_checkpoint(started["session_id"])
    assert state.status == "WAITING_HUMAN"
    assert calls["writer_v2"] == 1 and calls["decision"] == 0
    assert state.metadata["human_fact"]["revision_attempted"] is True
    assert any(item.get("action") == "STOP" and item.get("reason") == "unsupported_claim_remains_after_revision"
               for item in state.trace)


def test_revision_catches_paraphrase_not_recognized_as_p30_claim(runtime):
    calls, revision = runtime
    revision["statement"] = "相关原料均合格。"
    started = _start()
    response = _request("POST", f"/api/dynamic/{started['session_id']}/fact-response",
                        {"request_id": started["human_fact_request"]["request_id"], "response_type": "FACT_UNAVAILABLE"})
    assert response.status_code == 200
    state = checkpoint.load_checkpoint(started["session_id"])
    assert state.status == "WAITING_HUMAN"
    assert calls["writer_v2"] == 1 and calls["decision"] == 0


@pytest.mark.parametrize("draft", [
    "我们未见批次原料过期。",
    "该批次不含过期原料。",
    "目前确认该批次没有使用过期原料，调查工作仍在进行。",
    "该批次原料符合食品安全要求，其他事项尚待确认。",
    "我们将持续跟进相关情况。",
])
def test_revision_requires_explicit_safe_uncertainty_and_stops_unknown_or_assertive_text(runtime, draft):
    assert revision_is_safe(DRAFT.rstrip("。"), draft) is False


def test_revision_accepts_explicit_fact_uncertainty(runtime):
    assert revision_is_safe(DRAFT.rstrip("。"), "公司正对相关原料和涉事批次进行专项核查，目前相关事实仍在进一步确认。") is True


def test_provided_fact_is_human_asserted_not_verified(runtime):
    calls, _ = runtime
    started = _start()
    response = _request("POST", f"/api/dynamic/{started['session_id']}/fact-response",
                        {"request_id": started["human_fact_request"]["request_id"],
                         "response_type": "FACT_PROVIDED", "fact_text": "调查人员称已检查该批次台账。"})
    assert response.status_code == 200
    state = checkpoint.load_checkpoint(started["session_id"])
    observation = state.metadata["human_fact"]["observation"]
    assert observation["verification_status"] == "human_asserted"
    assert observation["source"] == "human_provided"
    assert state.metadata["legal_claim_coverage"]["claim_coverage"][0]["case_fact_status"] == "unresolved"
    assert state.status == "WAITING_HUMAN"
    assert calls["writer_v2"] == 0 and calls["decision"] == 0
    assert "fact_text" not in str(state.trace)
    assert state.metadata["human_wait_type"] == "FINAL_REVIEW"
    assert _request("POST", f"/api/dynamic/{started['session_id']}/fact-response",
                    {"request_id": started["human_fact_request"]["request_id"],
                     "response_type": "FACT_PROVIDED", "fact_text": "另一份不同表述"}).status_code == 400
    before = dict(calls)
    approved = _request("POST", f"/api/dynamic/{started['session_id']}/approve", {})
    assert approved.status_code == 200
    assert approved.json()["state_status"] == "COMPLETED"
    assert calls == before


def test_generic_approval_cannot_bypass_pending_fact(runtime):
    started = _start()
    response = _request("POST", f"/api/dynamic/{started['session_id']}/approve", {})
    assert response.status_code == 409
    assert checkpoint.load_checkpoint(started["session_id"]).status == "WAITING_HUMAN"


def test_saved_response_resumes_after_interruption_before_continuation(runtime):
    calls, _ = runtime
    started = _start()
    session_id = started["session_id"]
    request = started["human_fact_request"]
    state = checkpoint.load_checkpoint(session_id)
    assert state.metadata["human_wait_type"] == FACT_INPUT
    record_response(state, {"request_id": request["request_id"], "response_type": "FACT_UNAVAILABLE"})
    checkpoint.save_checkpoint(state)
    assert checkpoint.load_checkpoint(session_id).metadata["human_fact"]["phase"] == PHASE_RESPONSE_RECORDED

    resumed = _request("POST", f"/api/dynamic/{session_id}/fact-response",
                        {"request_id": request["request_id"], "response_type": "FACT_UNAVAILABLE"})
    assert resumed.status_code == 200, resumed.text
    assert calls["writer_v2"] == 1 and calls["decision"] == 1


def test_final_review_reject_does_not_resume_agents(runtime):
    calls, _ = runtime
    started = _start()
    response = _request("POST", f"/api/dynamic/{started['session_id']}/fact-response",
                        {"request_id": started["human_fact_request"]["request_id"],
                         "response_type": "FACT_PROVIDED", "fact_text": "調查人員提供了材料。"})
    assert response.status_code == 200
    before = dict(calls)
    rejected = _request("POST", f"/api/dynamic/{started['session_id']}/reject", {})
    assert rejected.status_code == 200
    assert rejected.json()["state_status"] == "REJECTED"
    assert calls == before


def test_same_response_retry_does_not_duplicate_revision(runtime):
    calls, _ = runtime
    started = _start()
    request = started["human_fact_request"]
    payload = {"request_id": request["request_id"], "response_type": "FACT_UNAVAILABLE"}
    assert _request("POST", f"/api/dynamic/{started['session_id']}/fact-response", payload).status_code == 200
    assert calls["writer_v2"] == 1
    retry = _request("POST", f"/api/dynamic/{started['session_id']}/fact-response", payload)
    assert retry.status_code == 400  # It has advanced to FINAL_REVIEW; it cannot restart continuation.
    assert calls["writer_v2"] == 1 and calls["decision"] == 1


@pytest.mark.parametrize("payload", [
    {"request_id": "expired", "response_type": "FACT_UNAVAILABLE"},
    {"response_type": "FACT_UNAVAILABLE"},
    {"request_id": "expired", "response_type": "FACT_PROVIDED", "fact_text": "x"},
])
def test_invalid_or_expired_request_cannot_resume(runtime, payload):
    calls, _ = runtime
    started = _start()
    response = _request("POST", f"/api/dynamic/{started['session_id']}/fact-response", payload)
    assert response.status_code == 400
    assert calls["writer_v2"] == 0


def test_frozen_draft_change_rejects_response(runtime):
    calls, _ = runtime
    started = _start()
    state = checkpoint.load_checkpoint(started["session_id"])
    state.set_result("writer", {"statement": "不同草稿"})
    checkpoint.save_checkpoint(state)
    response = _request("POST", f"/api/dynamic/{started['session_id']}/fact-response",
                        {"request_id": started["human_fact_request"]["request_id"], "response_type": "FACT_UNAVAILABLE"})
    assert response.status_code == 400
    assert calls["writer_v2"] == 0


def test_invalid_response_type_returns_controlled_error(runtime):
    started = _start()
    response = _request("POST", f"/api/dynamic/{started['session_id']}/fact-response",
                        {"request_id": started["human_fact_request"]["request_id"], "response_type": []})
    assert response.status_code == 400
