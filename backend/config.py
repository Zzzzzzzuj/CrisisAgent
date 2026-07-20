import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class AppConfig:
    agent_mode: str = "mock"
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_timeout_seconds: int = 30

    def validate(self) -> None:
        if self.agent_mode not in {"mock", "llm"}:
            raise ValueError("AGENT_MODE must be either 'mock' or 'llm'.")

        if self.agent_mode == "mock":
            return

        missing = []
        if not self.llm_api_key:
            missing.append("LLM_API_KEY")
        if not self.llm_base_url:
            missing.append("LLM_BASE_URL")
        if not self.llm_model:
            missing.append("LLM_MODEL")

        if missing:
            missing_fields = ", ".join(missing)
            raise ValueError(
                f"AGENT_MODE=llm requires the following environment variables: {missing_fields}."
            )


def _read_timeout() -> int:
    raw_value = os.getenv("LLM_TIMEOUT_SECONDS", "30")
    try:
        timeout_seconds = int(raw_value)
    except ValueError as exc:
        raise ValueError("LLM_TIMEOUT_SECONDS must be an integer.") from exc

    if timeout_seconds <= 0:
        raise ValueError("LLM_TIMEOUT_SECONDS must be greater than 0.")

    return timeout_seconds


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    config = AppConfig(
        agent_mode=os.getenv("AGENT_MODE", "mock").strip().lower() or "mock",
        llm_api_key=os.getenv("LLM_API_KEY"),
        llm_base_url=os.getenv("LLM_BASE_URL"),
        llm_model=os.getenv("LLM_MODEL"),
        llm_timeout_seconds=_read_timeout(),
    )
    config.validate()
    return config
