from functools import lru_cache

from app.config import get_settings
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.provider import LLMProvider


@lru_cache
def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    if settings.LLM_PROVIDER == "anthropic":
        return AnthropicProvider(api_key=settings.LLM_API_KEY, model=settings.LLM_MODEL)
    raise ValueError(f"Unsupported LLM_PROVIDER: {settings.LLM_PROVIDER!r}")
