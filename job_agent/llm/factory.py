"""Build an :class:`LLMProvider` from settings.

Adding a provider is a one-line registration here plus a provider module; no
other component changes (design principle #8).
"""

from __future__ import annotations

from typing import Any

from job_agent.config.logging import get_logger
from job_agent.config.settings import Settings, get_settings
from job_agent.llm.base import LLMProvider
from job_agent.llm.providers.mock import MockLLM

logger = get_logger(__name__)


def build_llm(settings: Settings | None = None) -> LLMProvider:
    settings = settings or get_settings()
    cfg = settings.llm
    common: dict[str, Any] = dict(
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
        max_retries=cfg.max_retries,
        timeout_seconds=cfg.timeout_seconds,
    )
    provider = cfg.provider.lower()

    if provider == "mock":
        return MockLLM(cfg.model, **common)

    if provider == "openai":
        from job_agent.llm.providers.openai_provider import OpenAILLM

        key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
        return OpenAILLM(cfg.model, api_key=key, **common)

    if provider == "vllm":
        from job_agent.llm.providers.openai_provider import OpenAILLM

        return OpenAILLM(cfg.model, base_url=cfg.vllm_base_url, api_key="not-needed", **common)

    if provider == "anthropic":
        from job_agent.llm.providers.anthropic_provider import AnthropicLLM

        key = settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
        return AnthropicLLM(cfg.model, api_key=key, **common)

    if provider == "gemini":
        from job_agent.llm.providers.gemini_provider import GeminiLLM

        key = settings.google_api_key.get_secret_value() if settings.google_api_key else None
        return GeminiLLM(cfg.model, api_key=key, **common)

    if provider == "ollama":
        from job_agent.llm.providers.ollama_provider import OllamaLLM

        return OllamaLLM(cfg.model, base_url=cfg.ollama_base_url, **common)

    logger.warning("Unknown LLM provider %r; falling back to mock", provider)
    return MockLLM(cfg.model, **common)
