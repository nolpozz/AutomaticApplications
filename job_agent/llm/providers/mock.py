"""Deterministic mock provider.

The mock never calls a network. For structured/text requests it returns the
caller's deterministic ``fallback`` directly, which makes the entire pipeline
runnable and reproducible with zero API keys. ``_complete`` returns a readable
echo so ``complete()`` still works if called directly.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from job_agent.llm.base import LLMMessage, LLMProvider, LLMResponse


class MockLLM(LLMProvider):
    name = "mock"

    def _complete(
        self, messages: list[LLMMessage], *, temperature: float, max_tokens: int
    ) -> LLMResponse:
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        preview = last_user.strip().splitlines()[0] if last_user.strip() else ""
        return LLMResponse(
            text=f"[mock:{self.model}] {preview[:200]}",
            model=self.model,
            raw={"mock": True},
        )

    def complete_json(
        self,
        messages: list[LLMMessage],
        *,
        fallback: Callable[[], dict[str, Any]],
        temperature: float | None = None,
    ) -> dict[str, Any]:
        return fallback()

    def complete_text(
        self,
        messages: list[LLMMessage],
        *,
        fallback: Callable[[], str],
        temperature: float | None = None,
    ) -> str:
        return fallback()
