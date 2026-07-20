import httpx

from backend.config import get_config
from backend.logger import get_logger


logger = get_logger(__name__)


def _build_chat_completions_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def call_llm(prompt: str) -> str:
    config = get_config()

    if config.agent_mode != "llm":
        raise RuntimeError("call_llm() is only available when AGENT_MODE=llm.")

    url = _build_chat_completions_url(config.llm_base_url or "")
    headers = {
        "Authorization": f"Bearer {config.llm_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.llm_model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
    }

    logger.info("Starting LLM call with model=%s url=%s", config.llm_model, url)

    try:
        with httpx.Client(timeout=config.llm_timeout_seconds) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
    except httpx.TimeoutException as exc:
        logger.error("LLM call timed out after %s seconds", config.llm_timeout_seconds)
        raise RuntimeError(
            f"LLM request timed out after {config.llm_timeout_seconds} seconds."
        ) from exc
    except httpx.HTTPStatusError as exc:
        logger.error("LLM call failed with status=%s", exc.response.status_code)
        raise RuntimeError(
            f"LLM request failed with status code {exc.response.status_code}."
        ) from exc
    except httpx.HTTPError as exc:
        logger.error("LLM call failed with network/client error: %s", exc.__class__.__name__)
        raise RuntimeError(f"LLM request failed: {exc.__class__.__name__}.") from exc

    try:
        data = response.json()
        content = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        logger.error("LLM response format was invalid")
        raise RuntimeError("LLM response format was invalid.") from exc

    logger.info("LLM call succeeded")
    return content
