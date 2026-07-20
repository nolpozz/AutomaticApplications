"""Parser and classifier tests (mock LLM -> deterministic heuristics)."""

from __future__ import annotations

from job_agent.classifier.classifier import JobClassifier
from job_agent.parser.llm_parser import JobParser


def test_parser_extracts_years_and_languages(llm, prompts, sample_job) -> None:  # type: ignore[no-untyped-def]
    parsed, version = JobParser(llm, prompts).parse(sample_job)
    assert version == "parse_job.v1"
    assert parsed.years_experience == 3
    assert "python" in parsed.programming_languages
    assert any("Bachelor" in d for d in parsed.degree_requirements)


def test_parser_detects_research_requirement(llm, prompts, sample_job) -> None:  # type: ignore[no-untyped-def]
    parsed, _ = JobParser(llm, prompts).parse(sample_job)
    assert parsed.research_requirements  # "Research a bonus" -> flagged


def test_classifier_is_reproducible(llm, prompts, knowledge, sample_job) -> None:  # type: ignore[no-untyped-def]
    parser = JobParser(llm, prompts)
    parsed, _ = parser.parse(sample_job)
    clf = JobClassifier(llm, prompts, knowledge)
    first, _ = clf.classify(sample_job, parsed)
    second, _ = clf.classify(sample_job, parsed)
    assert first.model_dump() == second.model_dump()


def test_strong_candidate_scores_high(llm, prompts, knowledge, sample_job) -> None:  # type: ignore[no-untyped-def]
    parsed, _ = JobParser(llm, prompts).parse(sample_job)
    score, _ = JobClassifier(llm, prompts, knowledge).classify(sample_job, parsed)
    assert score.overall_score > 0.7
    assert score.recommendation.value in {"apply", "strong_apply"}
    assert score.reasons
