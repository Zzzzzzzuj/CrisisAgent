import json
import os
import time
from contextvars import ContextVar
from copy import deepcopy
from time import perf_counter

import httpx

from backend.llm.config import LLMConfig, get_llm_config
from backend.logger import get_logger


logger = get_logger(__name__)
_LAST_LLM_TRACE: dict = {}
_LLM_TRACE_CONTEXT: ContextVar[dict] = ContextVar("llm_trace_context", default={})


FAILURE_TIMEOUT = "timeout"
FAILURE_RATE_LIMIT = "rate_limit"
FAILURE_PROVIDER_ERROR = "provider_error"
FAILURE_INVALID_JSON = "invalid_json"
FAILURE_SCHEMA_VALIDATION_FAILED = "schema_validation_failed"
FAILURE_EMPTY_RESPONSE = "empty_response"


class LLMClient:
    def __init__(
        self,
        config: LLMConfig | None = None,
        timeout_seconds: int | float | None = None,
        max_retries: int | None = None,
        retry_backoff_seconds: float | None = None,
    ):
        self.config = config or get_llm_config()
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else _read_float_env(
            "LLM_TIMEOUT_SECONDS",
            30.0,
        )
        self.max_retries = max(0, max_retries if max_retries is not None else _read_int_env("LLM_MAX_RETRIES", 1))
        self.retry_backoff_seconds = (
            retry_backoff_seconds
            if retry_backoff_seconds is not None
            else _read_float_env("LLM_RETRY_BACKOFF_SECONDS", 0.5)
        )

    def chat(self, messages, temperature=0.3, agent_name: str = "unknown"):
        start = perf_counter()
        if self.config.mock_enabled:
            logger.info("LLM mock response enabled because LLM_API_KEY is not configured")
            response = _mock_chat_response(messages)
            _record_llm_trace(
                provider=self.config.provider,
                model=self.config.model,
                agent_name=agent_name,
                latency_ms=_elapsed_ms(start),
                success=True,
                failure_type=None,
                fallback_used=True,
                retry_count=0,
                messages=messages,
                response_text=response,
            )
            return response

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

        last_error: RuntimeError | None = None
        last_failure_type = None
        attempts = self.max_retries + 1
        for attempt_index in range(attempts):
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                break
            except Exception as exc:
                last_failure_type = _classify_request_exception(exc)
                last_error = _build_runtime_error(exc, self.config.model)
                if attempt_index >= self.max_retries or not _is_retryable_failure(last_failure_type):
                    _record_llm_trace(
                        provider=self.config.provider,
                        model=self.config.model,
                        agent_name=agent_name,
                        latency_ms=_elapsed_ms(start),
                        success=False,
                        failure_type=last_failure_type,
                        fallback_used=True,
                        retry_count=attempt_index,
                        messages=messages,
                    )
                    raise last_error from exc
                _sleep_before_retry(self.retry_backoff_seconds, attempt_index)
        else:  # pragma: no cover - defensive guard.
            raise last_error or RuntimeError("LLM chat request failed.")

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            logger.error("LLM chat response format was invalid")
            _record_llm_trace(
                provider=self.config.provider,
                model=self.config.model,
                agent_name=agent_name,
                latency_ms=_elapsed_ms(start),
                success=False,
                failure_type=FAILURE_EMPTY_RESPONSE,
                fallback_used=True,
                retry_count=self.max_retries,
                messages=messages,
            )
            raise RuntimeError("LLM chat response format was invalid.") from exc

        if not str(content or "").strip():
            _record_llm_trace(
                provider=self.config.provider,
                model=self.config.model,
                agent_name=agent_name,
                latency_ms=_elapsed_ms(start),
                success=False,
                failure_type=FAILURE_EMPTY_RESPONSE,
                fallback_used=True,
                retry_count=self.max_retries,
                messages=messages,
            )
            raise RuntimeError("LLM chat response content was empty.")

        _record_llm_trace(
            provider=self.config.provider,
            model=self.config.model,
            agent_name=agent_name,
            latency_ms=_elapsed_ms(start),
            success=True,
            failure_type=None,
            fallback_used=False,
            retry_count=0,
            messages=messages,
            response_text=content,
        )
        return content


def get_last_llm_trace() -> dict:
    context_trace = _LLM_TRACE_CONTEXT.get({})
    return deepcopy(context_trace or _LAST_LLM_TRACE)


def reset_last_llm_trace() -> None:
    _LAST_LLM_TRACE.clear()
    _LLM_TRACE_CONTEXT.set({})


def record_llm_fallback(agent_name: str, exc: Exception) -> dict:
    trace = get_last_llm_trace()
    config = get_llm_config()
    trace.update(
        {
            "provider": trace.get("provider") or config.provider,
            "model": trace.get("model") or config.model,
            "agent_name": agent_name,
            "latency_ms": trace.get("latency_ms", 0),
            "success": False,
            "failure_type": classify_failure_from_exception(exc),
            "fallback_used": True,
            "retry_count": trace.get("retry_count", 0),
            "estimated_tokens": trace.get("estimated_tokens", 0),
            "input_chars": trace.get("input_chars", 0),
            "output_chars": trace.get("output_chars", 0),
            "failure_message": _safe_exception_message(exc),
        }
    )
    _LAST_LLM_TRACE.clear()
    _LAST_LLM_TRACE.update(trace)
    _LLM_TRACE_CONTEXT.set(deepcopy(trace))
    return get_last_llm_trace()


def classify_failure_from_exception(exc: Exception) -> str:
    name = exc.__class__.__name__.lower()
    message = str(exc).lower()
    if "timeout" in name or "timed out" in message:
        return FAILURE_TIMEOUT
    if "rate_limit" in message or "429" in message:
        return FAILURE_RATE_LIMIT
    if "missing required fields" in message or "schema" in message or isinstance(exc, (TypeError, ValueError)):
        if "json" not in message and "parse" not in message:
            return FAILURE_SCHEMA_VALIDATION_FAILED
    if "json" in message or "parse" in message:
        return FAILURE_INVALID_JSON
    if "empty" in message:
        return FAILURE_EMPTY_RESPONSE
    return FAILURE_PROVIDER_ERROR


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


def _record_llm_trace(
    provider: str,
    model: str,
    agent_name: str,
    latency_ms: int,
    success: bool,
    failure_type: str | None,
    fallback_used: bool,
    retry_count: int,
    messages,
    response_text: str = "",
) -> None:
    input_chars = _estimate_message_chars(messages)
    response_chars = len(str(response_text or ""))
    _LAST_LLM_TRACE.clear()
    _LAST_LLM_TRACE.update(
        {
            "provider": provider,
            "model": model,
            "agent_name": agent_name,
            "latency_ms": latency_ms,
            "success": success,
            "failure_type": failure_type,
            "fallback_used": fallback_used,
            "retry_count": retry_count,
            "estimated_tokens": max(1, (input_chars + response_chars) // 4),
            "input_chars": input_chars,
            "output_chars": response_chars,
        }
    )
    _LLM_TRACE_CONTEXT.set(deepcopy(_LAST_LLM_TRACE))


def _estimate_message_chars(messages) -> int:
    total = 0
    for message in messages or []:
        total += len(str(message.get("role", "")))
        total += len(str(message.get("content", "")))
    return total


def _elapsed_ms(start: float) -> int:
    return max(0, int((perf_counter() - start) * 1000))


def _classify_request_exception(exc: Exception) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return FAILURE_TIMEOUT
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code == 429:
            return FAILURE_RATE_LIMIT
        return FAILURE_PROVIDER_ERROR
    return FAILURE_PROVIDER_ERROR


def _is_retryable_failure(failure_type: str | None) -> bool:
    return failure_type in {FAILURE_TIMEOUT, FAILURE_RATE_LIMIT, FAILURE_PROVIDER_ERROR}


def _build_runtime_error(exc: Exception, model: str) -> RuntimeError:
    if isinstance(exc, httpx.TimeoutException):
        logger.error("LLM chat call timed out")
        return RuntimeError("LLM chat request timed out.")
    if isinstance(exc, httpx.HTTPStatusError):
        response_body = _response_body_preview(exc.response)
        logger.error(
            "LLM chat call failed status=%s url=%s model=%s response_body=%s",
            exc.response.status_code,
            str(exc.request.url),
            model,
            response_body,
        )
        return RuntimeError(
            "LLM chat request failed "
            f"status={exc.response.status_code} "
            f"url={exc.request.url} "
            f"model={model} "
            f"response_body={response_body}"
        )
    logger.error("LLM chat call failed with network/client error: %s", exc.__class__.__name__)
    return RuntimeError(f"LLM chat request failed: {exc.__class__.__name__}.")


def _sleep_before_retry(base_seconds: float, attempt_index: int) -> None:
    if base_seconds <= 0:
        return
    time.sleep(base_seconds * (2 ** attempt_index))


def _read_int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _read_float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _safe_exception_message(exc: Exception) -> str:
    text = str(exc)
    return text[:200]
