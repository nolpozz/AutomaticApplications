"""Score-boost logic: location and keyword bonuses, capping, idempotent base."""

from __future__ import annotations

from job_agent.classifier.boost import ScoreBoost


def _boost() -> ScoreBoost:
    return ScoreBoost(
        locations=("new york", "nyc"),
        location_boost=0.06,
        keywords=("research", "nlp"),
        keyword_boost=0.03,
        cap=0.10,
    )


def test_inactive_when_unconfigured() -> None:
    assert ScoreBoost().active is False
    assert ScoreBoost(locations=("nyc",)).active is False  # boost value is 0
    assert _boost().active is True


def test_location_boost_applies_only_on_match() -> None:
    b = _boost()
    hit, _ = b.apply(0.60, title="Software Engineer Intern", location="New York, NY")
    assert hit == 0.66
    miss, _ = b.apply(0.60, title="Software Engineer Intern", location="Austin, TX")
    assert miss == 0.60


def test_keyword_boost_and_reasons() -> None:
    b = _boost()
    # "research" + "nlp" = two hits * 0.03 = 0.06
    score, reasons = b.apply(0.60, title="NLP Research Intern", location="Remote")
    assert score == 0.66
    assert any("Role boost" in r for r in reasons)


def test_total_boost_is_capped() -> None:
    b = _boost()
    # NYC (0.06) + research+nlp (0.06) = 0.12, capped at 0.10
    score, _ = b.apply(0.60, title="NLP Research Intern", location="New York")
    assert score == 0.70


def test_score_clamped_to_one() -> None:
    score, _ = _boost().apply(0.98, title="NLP Research", location="NYC")
    assert score == 1.0
