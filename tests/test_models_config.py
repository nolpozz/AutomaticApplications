"""Domain-model and configuration tests."""

from __future__ import annotations

from job_agent.config.settings import PipelineSettings
from job_agent.models.domain import (
    ClassifierScore,
    Job,
    ParsedJob,
    Recommendation,
)


def test_dedup_key_prefers_external_id() -> None:
    job = Job(title="X", company="Y", url="https://a", source="s", external_id="EID-1")
    assert job.dedup_key() == "eid-1"


def test_dedup_key_falls_back_to_url() -> None:
    job = Job(title="X", company="Y", url="https://A/Job", source="s")
    assert job.dedup_key() == "https://a/job"


def test_parsed_job_defaults_are_empty() -> None:
    parsed = ParsedJob()
    assert parsed.required_skills == []
    assert parsed.years_experience is None


def test_classifier_passes_threshold() -> None:
    good = ClassifierScore(overall_score=0.8, recommendation=Recommendation.APPLY)
    weak = ClassifierScore(overall_score=0.8, recommendation=Recommendation.SKIP)
    assert good.passes(0.65)
    assert not good.passes(0.9)
    assert not weak.passes(0.1)  # SKIP never passes


def test_enabled_boards_split_from_comma_string() -> None:
    cfg = PipelineSettings(enabled_boards="greenhouse, lever ,ashby")  # type: ignore[arg-type]
    assert cfg.enabled_boards == ["greenhouse", "lever", "ashby"]
