import json

import pytest

from backend.llm.client import LLMClient, _build_chat_completions_url, get_last_llm_trace, get_llm_trace_calls, reset_last_llm_trace
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
    assert get_llm_trace_calls()[0]["http_attempt_count"] == 2


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
