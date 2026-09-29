import logging
import os


logger = logging.getLogger(__name__)
_TRUTHY = {"1", "true", "yes", "on"}


class OfflineNetworkBlockedError(RuntimeError):
    """Raised before a model-provider HTTP request in offline evaluation mode."""


def offline_eval_enabled() -> bool:
    return os.getenv("OFFLINE_EVAL", "").strip().casefold() in _TRUTHY


def assert_external_model_call_allowed(*, provider: str, operation: str) -> None:
    if offline_eval_enabled():
        raise OfflineNetworkBlockedError(
            "External model request blocked: OFFLINE_EVAL is enabled "
            f"(provider={_safe_label(provider)}, operation={_safe_label(operation)})."
        )


def assert_offline_eval_startup() -> dict[str, object]:
    """Fail closed unless this process is configured for a mock offline run."""
    from backend.config import get_config
    from backend.llm.config import get_llm_config

    if not offline_eval_enabled():
        raise RuntimeError("Offline evaluation startup requires OFFLINE_EVAL=1.")

    # Resolve startup configuration from the current process environment rather
    # than accepting a mode cached before the offline-eval launcher set it.
    get_config.cache_clear()
    get_llm_config.cache_clear()
    app_config = get_config()
    llm_config = get_llm_config()
    environment_mode = os.getenv("AGENT_MODE", "mock").strip().lower() or "mock"
    if app_config.agent_mode != "mock" or environment_mode != "mock":
        raise RuntimeError(
            "Offline evaluation requires effective AGENT_MODE=mock; "
            "no case was executed."
        )

    summary: dict[str, object] = {
        "agent_mode": app_config.agent_mode,
        "offline_eval": True,
        "model_provider": _safe_label(llm_config.provider),
        "network_policy": "external_model_http_blocked",
        "external_llm_allowed": False,
    }
    logger.info("Offline evaluation config: %s", summary)
    return summary


def _safe_label(value: object) -> str:
    text = str(value or "unknown")
    return "".join(char for char in text if char.isalnum() or char in "_.-:/")[:80]
