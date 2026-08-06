import json

import httpx

from backend.llm.config import LLMConfig, get_llm_config
from backend.logger import get_logger


logger = get_logger(__name__)


class LLMClient:
    def __init__(self, config: LLMConfig | None = None, timeout_seconds: int = 30):
        self.config = config or get_llm_config()
        self.timeout_seconds = timeout_seconds

    def chat(self, messages, temperature=0.3):
        if self.config.mock_enabled:
            logger.info("LLM mock response enabled because LLM_API_KEY is not configured")
            return _mock_chat_response(messages)

        if self.config.provider != "openai_compatible":
            raise ValueError(f"Unsupported LLM_PROVIDER: {self.config.provider}")

        url = _build_chat_completions_url(self.config.base_url)
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
        }

        logger.info(
            "Starting LLM chat call provider=%s model=%s url=%s",
            self.config.provider,
            self.config.model,
            url,
        )

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            logger.error("LLM chat call timed out")
            raise RuntimeError("LLM chat request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            response_body = _response_body_preview(exc.response)
            logger.error(
                "LLM chat call failed status=%s url=%s model=%s response_body=%s",
                exc.response.status_code,
                str(exc.request.url),
                self.config.model,
                response_body,
            )
            raise RuntimeError(
                "LLM chat request failed "
                f"status={exc.response.status_code} "
                f"url={exc.request.url} "
                f"model={self.config.model} "
                f"response_body={response_body}"
            ) from exc
        except httpx.HTTPError as exc:
            logger.error("LLM chat call failed with network/client error: %s", exc.__class__.__name__)
            raise RuntimeError(f"LLM chat request failed: {exc.__class__.__name__}.") from exc

        try:
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            logger.error("LLM chat response format was invalid")
            raise RuntimeError("LLM chat response format was invalid.") from exc


def _build_chat_completions_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def _response_body_preview(response: httpx.Response, limit: int = 1000) -> str:
    text = response.text or ""
    return text[:limit]


def _mock_chat_response(messages) -> str:
    user_content = ""
    for message in reversed(messages or []):
        if message.get("role") == "user":
            user_content = str(message.get("content", ""))
            break

    return json.dumps(
        {
            "mock": True,
            "content": "mock llm response",
            "input_preview": user_content[:120],
        },
        ensure_ascii=False,
    )
