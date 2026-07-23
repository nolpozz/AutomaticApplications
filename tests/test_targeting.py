"""Level targeting: on-target roles keep full score; off-target ones are penalized
even when a prestige boost is present (interns-only ranking)."""

from __future__ import annotations

from job_agent.classifier.prestige import CompanyPrestige
from job_agent.classifier.targeting import LevelTargeting


def _t() -> LevelTargeting:
    return LevelTargeting(
        levels=["intern"], keywords=["intern", "internship", "student researcher"]
    )


def test_inactive_without_config() -> None:
    assert LevelTargeting([], []).active is False
    assert _t().active is True


def test_on_target_intern_keeps_score() -> None:
    t = _t()
    assert t.factor(level="intern", title="Machine Learning Engineer Intern") == 1.0
    assert t.factor(level="unknown", title="Student Researcher, ML") == 1.0


def test_off_target_fulltime_penalized() -> None:
    t = _t()
    assert t.factor(level="mid", title="Machine Learning Engineer") == 0.6
    assert t.factor(level="senior", title="Staff ML Engineer") == 0.5


def test_prestige_cannot_rescue_fulltime() -> None:
    """A full-time FAANG role stays below threshold; an intern one clears it."""
    t = _t()
    prestige = CompanyPrestige(boost_faang=0.12)
    thr = 0.62

    # Full-time FAANG: base 0.62 -> *0.6 targeting = 0.372 -> +0.12 prestige = 0.492
    base = 0.62
    ft = base * t.factor(level="mid", title="ML Engineer") + prestige.score_boost("OpenAI")[0]
    assert ft < thr

    # Intern FAANG: base 0.70 -> *1.0 -> +0.12 = 0.82
    intern = (
        0.70 * t.factor(level="intern", title="ML Engineer Intern")
        + prestige.score_boost("OpenAI")[0]
    )
    assert intern >= thr
