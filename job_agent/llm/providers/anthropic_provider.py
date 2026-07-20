"""Anthropic (Claude) provider."""

from __future__ import annotations

from job_agent.llm.base import LLMMessage, LLMProvider, LLMResponse


class AnthropicLLM(LLMProvider):
    name = "anthropic"

    def __init__(self, model: str, *, api_key: str | None = None, **kwargs: object) -> None:
        super().__init__(model, **kwargs)  # type: ignore[arg-type]
        self._api_key = api_key
        self._client = None

    def _get_client(self):  # type: ignore[no-untyped-def]
        if self._client is None:
            from anthropic import Anthropic  # lazy import

            self._client = Anthropic(api_key=self._api_key, timeout=self.timeout_seconds)
        return self._client

    def _complete(
        self, messages: list[LLMMessage], *, temperature: float, max_tokens: int
    ) -> LLMResponse:
        client = self._get_client()
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        chat = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
        resp = client.messages.create(
            model=self.model,
            system=system or None,
            messages=chat,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
        return LLMResponse(text=text, model=self.model, raw=resp.model_dump())
