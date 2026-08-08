import json

import pytest

from backend.llm.client import LLMClient, _build_chat_completions_url
from backend.llm.config import LLMConfig
from backend.llm.parser import LLMParseError, parse_json_response, validate_required_fields


def test_llm_client_mock_mode_returns_response_without_api_key():
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
