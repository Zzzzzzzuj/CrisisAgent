import json
import logging

import httpx

from backend.agents import legal_agent, writer_agent
from backend.llm.client import _build_runtime_error


def test_writer_info_logs_only_safe_metadata(monkeypatch, caplog):
    event = "PRIVATE_EVENT_SENTINEL"
    prompt_context = "PRIVATE_PROMPT_SENTINEL"
    statement = "PRIVATE_STATEMENT_SENTINEL"
    payload = {
        "event": event,
        "sentiment_analysis": {
            "risk_level": "high",
            "public_emotion": "worried",
            "keywords": [],
            "recommended_tone": "careful",
            "analysis_summary": "summary",
        },
        "context_pack": {"rendered_context": prompt_context},
    }

    def fake_llm(prompt):
        assert event in prompt
        assert prompt_context in prompt
        return json.dumps({"statement": statement, "strategy": "safe", "tone": "careful", "notes": "notes"})

    monkeypatch.setattr(writer_agent, "call_llm", fake_llm)
    with caplog.at_level(logging.DEBUG):
        result = writer_agent._run_llm(payload)

    assert result["statement"] == statement
    assert "statement_chars=" in caplog.text
    for secret in (event, prompt_context, statement):
        assert secret not in caplog.text


def test_writer_v2_logs_do_not_include_statement_or_human_fact(monkeypatch, caplog):
    statement = "PRIVATE_V2_STATEMENT_SENTINEL"
    human_fact = "PRIVATE_HUMAN_FACT_SENTINEL"
    payload = {
        "event": "PRIVATE_EVENT_SENTINEL",
        "first_draft": {"statement": "PRIVATE_FIRST_DRAFT_SENTINEL"},
        "redteam_review": {},
        "legal_review": {},
        "human_fact_revision": {"response": human_fact},
    }

    def fake_llm(prompt):
        assert human_fact in prompt
        return json.dumps({"statement": statement, "strategy": "safe", "tone": "careful", "revisions": []})

    monkeypatch.setattr(writer_agent, "call_llm", fake_llm)
    with caplog.at_level(logging.DEBUG):
        result = writer_agent._generate_second_draft_llm(payload)

    assert result["statement"] == statement
    assert "statement_chars=" in caplog.text
    for secret in (statement, human_fact, payload["event"], payload["first_draft"]["statement"]):
        assert secret not in caplog.text


def test_legal_evidence_and_gate_details_stay_out_of_logs(monkeypatch, caplog):
    evidence = "PRIVATE_EVIDENCE_SENTINEL"
    source = "PRIVATE_SOURCE_SENTINEL"
    monkeypatch.setattr(legal_agent, "_is_rag_enabled", lambda: True)
    monkeypatch.setattr(legal_agent, "evaluate_retrieval_need", lambda **kwargs: {"need_rag": True, "reason": evidence})
    monkeypatch.setattr(legal_agent, "retrieve", lambda query, top_k: {
        "context": evidence,
        "sources": [{"source": source}],
        "chunks": [],
    })
    payload = {"event": "event", "draft": "draft", "redteam_review": {}}
    with caplog.at_level(logging.INFO):
        assert legal_agent._retrieve_legal_context(payload) == evidence

    assert "source_count=" in caplog.text
    assert evidence not in caplog.text
    assert source not in caplog.text


def test_provider_error_logs_status_not_body_url_or_credentials(caplog):
    request = httpx.Request("POST", "https://example.invalid/chat?token=PRIVATE_URL_TOKEN")
    response = httpx.Response(429, request=request, text="PRIVATE_RESPONSE_BODY Authorization: Bearer PRIVATE_API_KEY")
    error = httpx.HTTPStatusError("provider error", request=request, response=response)
    with caplog.at_level(logging.ERROR):
        safe_error = _build_runtime_error(error, "test-model")

    assert "status=429" in caplog.text
    assert "status=429" in str(safe_error)
    for secret in ("PRIVATE_RESPONSE_BODY", "PRIVATE_API_KEY", "PRIVATE_URL_TOKEN", "Authorization"):
        assert secret not in caplog.text
        assert secret not in str(safe_error)


def test_fallback_warning_does_not_log_exception_body(monkeypatch, caplog):
    monkeypatch.setenv("AGENT_MODE", "llm")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setattr(writer_agent, "_run_llm", lambda payload: (_ for _ in ()).throw(RuntimeError("PRIVATE_PROMPT_SENTINEL Authorization: Bearer PRIVATE_API_KEY")))
    payload = {
        "event": "event",
        "sentiment_analysis": {"risk_level": "low", "recommended_tone": "careful"},
    }
    with caplog.at_level(logging.WARNING):
        writer_agent.run(payload)

    assert "RuntimeError" in caplog.text
    assert "PRIVATE_PROMPT_SENTINEL" not in caplog.text
    assert "PRIVATE_API_KEY" not in caplog.text
