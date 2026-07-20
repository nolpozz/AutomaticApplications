"""Google Gemini provider."""

from __future__ import annotations

from job_agent.llm.base import LLMMessage, LLMProvider, LLMResponse


class GeminiLLM(LLMProvider):
    name = "gemini"

    def __init__(self, model: str, *, api_key: str | None = None, **kwargs: object) -> None:
        super().__init__(model, **kwargs)  # type: ignore[arg-type]
        self._api_key = api_key
        self._model_obj = None

    def _get_model(self):  # type: ignore[no-untyped-def]
        if self._model_obj is None:
            import google.generativeai as genai  # lazy import

            genai.configure(api_key=self._api_key)
            self._model_obj = genai.GenerativeModel(self.model)
        return self._model_obj

    def _complete(
        self, messages: list[LLMMessage], *, temperature: float, max_tokens: int
    ) -> LLMResponse:
        model = self._get_model()
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        user = "\n\n".join(m.content for m in messages if m.role != "system")
        prompt = f"{system}\n\n{user}" if system else user
        resp = model.generate_content(
            prompt,
            generation_config={"temperature": temperature, "max_output_tokens": max_tokens},
        )
        return LLMResponse(text=resp.text or "", model=self.model, raw={"gemini": True})
