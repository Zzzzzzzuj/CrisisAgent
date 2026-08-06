import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class LLMConfig:
    provider: str = "openai_compatible"
    model: str = "mock-model"
    api_key: str | None = None
    base_url: str = "mock://local"

    @property
    def mock_enabled(self) -> bool:
        return not self.api_key


@lru_cache(maxsize=1)
def get_llm_config() -> LLMConfig:
    return LLMConfig(
        provider=os.getenv("LLM_PROVIDER", "openai_compatible").strip() or "openai_compatible",
        model=os.getenv("LLM_MODEL", "mock-model").strip() or "mock-model",
        api_key=os.getenv("LLM_API_KEY") or None,
        base_url=os.getenv("LLM_BASE_URL", "mock://local").strip() or "mock://local",
    )
