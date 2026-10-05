import json

import pytest

from backend.llm.client import (LLMClient, _build_chat_completions_url, get_last_llm_trace,
                                get_llm_trace_calls, legal_operation_scope, reset_last_llm_trace)
from backend.llm.config import LLMConfig
from backend.llm.parser import LLMParseError, parse_json_response, validate_required_fields


def test_llm_client_mock_mode_returns_response_without_api_key():
    reset_last_llm_trace()
    client = LLMClient(
        config=LLMConfig(
            provider="openai_compatible",
            model="mock-model",
            api_key=None,
            base_url="mock://local",
        )
    )

    response = client.chat([{"role": "user", "content": "hello crisis agent"}])
    parsed = json.loads(response)

    assert parsed["mock"] is True
    assert parsed["content"] == "mock llm response"
    assert parsed["input_preview"] == "hello crisis agent"
    trace = get_last_llm_trace()
    assert trace["token_source"] == "estimated"
    assert trace["total_tokens"] is None
    assert trace["http_attempt_count"] == 0


def test_llm_provider_usage_is_captured_without_request_or_response_body(monkeypatch, caplog):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "safe output"}}],
                    "usage": {"prompt_tokens": 11, "completion_tokens": 4, "total_tokens": 15}}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("backend.llm.client.assert_external_model_call_allowed", lambda **kwargs: None)
    monkeypatch.setattr("backend.llm.client.httpx.Client", FakeClient)
    reset_last_llm_trace()
    client = LLMClient(config=LLMConfig(provider="openai_compatible", model="test-model",
                                        api_key="test-key", base_url="https://provider.invalid"),
                       max_retries=0)

    assert client.chat([{"role": "user", "content": "PRIVATE PROMPT"}], agent_name="writer") == "safe output"
    trace = get_last_llm_trace()
    assert trace["token_source"] == "provider"
    assert (trace["input_tokens"], trace["output_tokens"], trace["total_tokens"]) == (11, 4, 15)
    assert trace["http_attempt_count"] == 1
    assert trace["retry_count"] == 0
    assert trace["llm_call_id"]
    assert trace["operation_type"] == "unknown"
    assert len(trace["attempts"]) == 1
    assert trace["attempts"][0]["attempt_index"] == 0
    assert trace["attempts"][0]["attempt_status"] == "SUCCESS"
    assert trace["attempts"][0]["attempt_latency_ms"] >= 0
    assert len(get_llm_trace_calls()) == 1
    assert "PRIVATE PROMPT" not in repr(trace)
    assert "test-key" not in repr(trace)
    assert "PRIVATE PROMPT" not in caplog.text
    assert "test-key" not in caplog.text


def test_llm_trace_counts_one_transient_retry(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "safe output"}}],
                    "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}}

    class FakeClient:
        attempts = 0

        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            type(self).attempts += 1
            if type(self).attempts == 1:
                import httpx
                raise httpx.TimeoutException("synthetic timeout")
            return FakeResponse()

    monkeypatch.setattr("backend.llm.client.assert_external_model_call_allowed", lambda **kwargs: None)
    monkeypatch.setattr("backend.llm.client.httpx.Client", FakeClient)
    reset_last_llm_trace()
    client = LLMClient(config=LLMConfig(provider="openai_compatible", model="test-model",
                                        api_key="test-key", base_url="https://provider.invalid"),
                       max_retries=1, retry_backoff_seconds=0)

    assert client.chat([{"role": "user", "content": "safe fixture"}], agent_name="legal") == "safe output"
    trace = get_last_llm_trace()
    assert trace["http_attempt_count"] == 2
    assert trace["retry_count"] == 1
    call = get_llm_trace_calls()[0]
    assert call["http_attempt_count"] == 2
    assert call["attempts"][0]["attempt_status"] == "TIMEOUT"
    assert call["attempts"][1]["attempt_status"] == "SUCCESS"
    assert call["attempts"][0]["attempt_index"] == 0
    assert call["attempts"][1]["attempt_index"] == 1
    assert call["llm_call_id"] == trace["llm_call_id"]


def test_timeout_retries_keep_one_logical_call_and_record_no_attempt_tokens(monkeypatch):
    import httpx

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            raise httpx.TimeoutException("synthetic timeout")

    monkeypatch.setattr("backend.llm.client.assert_external_model_call_allowed", lambda **kwargs: None)
    monkeypatch.setattr("backend.llm.client.httpx.Client", FakeClient)
    reset_last_llm_trace()
    client = LLMClient(config=LLMConfig(provider="openai_compatible", model="test-model",
                                        api_key="test-key", base_url="https://provider.invalid"),
                       max_retries=1, retry_backoff_seconds=0)

    with pytest.raises(RuntimeError, match="timed out"):
        client.chat([{"role": "user", "content": "safe fixture"}], agent_name="legal")

    calls = get_llm_trace_calls()
    assert len(calls) == 1
    trace = calls[0]
    assert trace["http_attempt_count"] == 2
    assert trace["retry_count"] == 1
    assert [item["attempt_status"] for item in trace["attempts"]] == ["TIMEOUT", "TIMEOUT"]
    assert [item["attempt_index"] for item in trace["attempts"]] == [0, 1]
    assert all(set(item) == {"attempt_index", "attempt_latency_ms", "attempt_status"}
               for item in trace["attempts"])
    assert trace["input_tokens"] is None
    assert trace["output_tokens"] is None
    assert trace["total_tokens"] is None


@pytest.mark.parametrize("operation_type", [
    "legal.claim_extraction", "legal.action_proposal", "legal.relation_check", "legal.review",
])
def test_legal_operation_scope_attaches_safe_logical_identity(monkeypatch, operation_type):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "safe output"}}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("backend.llm.client.assert_external_model_call_allowed", lambda **kwargs: None)
    monkeypatch.setattr("backend.llm.client.httpx.Client", FakeClient)
    reset_last_llm_trace()
    client = LLMClient(config=LLMConfig(provider="openai_compatible", model="test-model",
                                        api_key="test-key", base_url="https://provider.invalid"),
                       max_retries=0)

    with legal_operation_scope(operation_type):
        client.chat([{"role": "user", "content": "PRIVATE PROMPT"}], agent_name="legal")
        client.chat([{"role": "user", "content": "PRIVATE PROMPT"}], agent_name="legal")

    calls = get_llm_trace_calls()
    assert len(calls) == 2
    assert {call["operation_type"] for call in calls} == {operation_type}
    assert calls[0]["operation_span_id"] == calls[1]["operation_span_id"]
    assert calls[0]["llm_call_id"] != calls[1]["llm_call_id"]
    assert "PRIVATE PROMPT" not in repr(calls)
    assert "test-key" not in repr(calls)


def test_trace_identity_generation_failure_does_not_change_mock_result(monkeypatch):
    monkeypatch.setattr("backend.llm.client.uuid.uuid4", lambda: (_ for _ in ()).throw(RuntimeError("trace unavailable")))
    reset_last_llm_trace()
    client = LLMClient(config=LLMConfig(provider="openai_compatible", model="mock-model",
                                        api_key=None, base_url="mock://local"))

    with legal_operation_scope("legal.review"):
        response = client.chat([{"role": "user", "content": "fixture"}], agent_name="legal")

    assert json.loads(response)["mock"] is True
    calls = get_llm_trace_calls()
    assert len(calls) == 1
    assert calls[0]["operation_type"] == "legal.review"
    assert calls[0]["operation_span_id"] is None
    assert calls[0]["llm_call_id"] is None


def test_build_chat_completions_url_appends_endpoint_once():
    assert (
        _build_chat_completions_url("https://api.deepseek.com")
        == "https://api.deepseek.com/chat/completions"
    )
    assert (
        _build_chat_completions_url("https://api.deepseek.com/chat/completions")
        == "https://api.deepseek.com/chat/completions"
    )


def test_parse_json_response_handles_code_block_and_extra_text():
    text = """
    下面是分析结果：
    ```json
    {"risk_level": "high", "passed": true}
    ```
    """

    parsed = parse_json_response(text)

    assert parsed == {"risk_level": "high", "passed": True}


def test_parse_json_response_failure_can_be_caught():
    with pytest.raises(LLMParseError) as exc_info:
        parse_json_response("this is not json")

    error = exc_info.value.to_dict()
    assert error["error_type"] == "llm_parse_error"
    assert "Could not parse JSON object" in error["message"]
    assert error["raw_text_preview"] == "this is not json"


def test_validate_required_fields_reports_missing_fields():
    with pytest.raises(LLMParseError, match="Missing required fields"):
        validate_required_fields({"a": 1}, ["a", "b"])
