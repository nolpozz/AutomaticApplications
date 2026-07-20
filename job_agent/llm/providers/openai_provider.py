"""OpenAI provider (also used for OpenAI-compatible servers like vLLM)."""

from __future__ import annotations

from job_agent.llm.base import LLMMessage, LLMProvider, LLMResponse


class OpenAILLM(LLMProvider):
    name = "openai"

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(model, **kwargs)  # type: ignore[arg-type]
        self._api_key = api_key
        self._base_url = base_url
        self._client = None

    def _get_client(self):  # type: ignore[no-untyped-def]
        if self._client is None:
            from openai import OpenAI  # lazy import; only needed when selected

            self._client = OpenAI(
                api_key=self._api_key, base_url=self._base_url, timeout=self.timeout_seconds
            )
        return self._client

    def _complete(
        self, messages: list[LLMMessage], *, temperature: float, max_tokens: int
    ) -> LLMResponse:
        client = self._get_client()
        resp = client.chat.completions.create(
            model=self.model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        text = resp.choices[0].message.content or ""
        return LLMResponse(text=text, model=self.model, raw=resp.model_dump())
