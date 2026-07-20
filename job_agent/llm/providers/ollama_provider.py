"""Local LLM provider for Ollama (self-hosted, OpenAI-free) via httpx."""

from __future__ import annotations

import httpx

from job_agent.llm.base import LLMMessage, LLMProvider, LLMResponse


class OllamaLLM(LLMProvider):
    name = "ollama"

    def __init__(
        self, model: str, *, base_url: str = "http://localhost:11434", **kwargs: object
    ) -> None:
        super().__init__(model, **kwargs)  # type: ignore[arg-type]
        self._base_url = base_url.rstrip("/")

    def _complete(
        self, messages: list[LLMMessage], *, temperature: float, max_tokens: int
    ) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        with httpx.Client(timeout=self.timeout_seconds) as client:
            resp = client.post(f"{self._base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
        text = data.get("message", {}).get("content", "")
        return LLMResponse(text=text, model=self.model, raw=data)
