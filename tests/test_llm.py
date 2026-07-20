"""LLM abstraction, mock provider, and prompt registry tests."""

from __future__ import annotations

from job_agent.llm.base import LLMMessage, extract_json
from job_agent.llm.providers.mock import MockLLM


def test_extract_json_from_fenced_block() -> None:
    text = 'Here you go:\n```json\n{"a": 1, "b": [2, 3]}\n```\nDone.'
    assert extract_json(text) == {"a": 1, "b": [2, 3]}


def test_extract_json_from_bare_object() -> None:
    assert extract_json('prefix {"x": true} suffix') == {"x": True}


def test_extract_json_returns_none_on_garbage() -> None:
    assert extract_json("no json here") is None


def test_mock_json_uses_fallback() -> None:
    llm = MockLLM("mock-model")
    result = llm.complete_json([LLMMessage("user", "hi")], fallback=lambda: {"ok": 1})
    assert result == {"ok": 1}


def test_mock_text_uses_fallback() -> None:
    llm = MockLLM("mock-model")
    assert llm.complete_text([LLMMessage("user", "hi")], fallback=lambda: "deterministic") == (
        "deterministic"
    )


def test_prompt_registry_versioning(prompts) -> None:  # type: ignore[no-untyped-def]
    available = prompts.available()
    assert "parse_job" in available
    rendered = prompts.render("parse_job", title="T", company="C", location="L", description="D")
    assert rendered.version == "parse_job.v1"
    assert any(m.role == "system" for m in rendered.messages())
