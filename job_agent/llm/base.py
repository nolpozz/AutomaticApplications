"""LLM provider abstraction.

Every AI component (parser, classifier, resume, cover letter) depends only on
this interface, never on a concrete SDK. Switching providers is a config change.

Two design points worth calling out:

* ``complete_json`` / ``complete_text`` take a ``fallback`` callable. The caller
  supplies a *deterministic* computation of the same result. Real providers use
  it only when the model returns unparseable output; the mock provider returns
  it directly. This is what makes the whole pipeline runnable with no API keys
  and makes results reproducible in tests.
* Retries are centralized here via ``tenacity`` so individual providers stay
  small.
"""

from __future__ import annotations

import abc
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

from job_agent.config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class LLMResponse:
    text: str
    model: str
    raw: dict[str, Any] = field(default_factory=dict)


class LLMError(RuntimeError):
    """Raised when a provider fails after exhausting retries."""


class LLMProvider(abc.ABC):
    """Abstract base for all LLM providers."""

    name: str = "base"

    def __init__(
        self,
        model: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        max_retries: int = 3,
        timeout_seconds: int = 60,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds

    # -- provider-specific -------------------------------------------------
    @abc.abstractmethod
    def _complete(
        self, messages: list[LLMMessage], *, temperature: float, max_tokens: int
    ) -> LLMResponse:
        """Perform a single completion call. Implemented per provider."""

    # -- public API --------------------------------------------------------
    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        temp = self.temperature if temperature is None else temperature
        tokens = self.max_tokens if max_tokens is None else max_tokens

        @retry(
            reraise=True,
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        )
        def _run() -> LLMResponse:
            return self._complete(messages, temperature=temp, max_tokens=tokens)

        try:
            return _run()
        except Exception as exc:
            raise LLMError(f"{self.name} completion failed: {exc}") from exc

    def complete_text(
        self,
        messages: list[LLMMessage],
        *,
        fallback: Callable[[], str],
        temperature: float | None = None,
    ) -> str:
        """Return model text, or the deterministic fallback on failure."""
        try:
            return self.complete(messages, temperature=temperature).text
        except LLMError as exc:
            logger.warning("Falling back to deterministic text: %s", exc)
            return fallback()

    def complete_json(
        self,
        messages: list[LLMMessage],
        *,
        fallback: Callable[[], dict[str, Any]],
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """Return a parsed JSON object from the model, or the fallback."""
        try:
            text = self.complete(messages, temperature=temperature).text
        except LLMError as exc:
            logger.warning("LLM call failed, using fallback: %s", exc)
            return fallback()
        parsed = extract_json(text)
        if parsed is None:
            logger.warning("Could not parse JSON from %s response; using fallback", self.name)
            return fallback()
        return parsed


def extract_json(text: str) -> dict[str, Any] | None:
    """Best-effort extraction of a JSON object from model output.

    Handles fenced code blocks and leading/trailing prose.
    """
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text
    # Fall back to the outermost braces.
    if not fenced:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1 or end < start:
            return None
        candidate = candidate[start : end + 1]
    try:
        data = json.loads(candidate)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None
