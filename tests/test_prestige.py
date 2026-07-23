"""Company-prestige tiers: FAANG+ > high-growth > other, boosts, and cap multiplier."""

from __future__ import annotations

from job_agent.classifier.prestige import CompanyPrestige


def _p() -> CompanyPrestige:
    return CompanyPrestige(boost_faang=0.12, boost_growth=0.072, cap_multiplier=3)


def test_inactive_by_default() -> None:
    assert CompanyPrestige().active is False
    assert _p().active is True


def test_tiers() -> None:
    p = _p()
    assert p.tier("Spotify") == "faang"
    assert p.tier("Google DeepMind") == "faang"
    assert p.tier("Databricks") == "growth"
    assert p.tier("Acme Widgets Co") is None


def test_score_boost_faang_beats_growth() -> None:
    p = _p()
    assert p.score_boost("Netflix") == (0.12, "faang")
    assert p.score_boost("Cohere") == (0.072, "growth")
    assert p.score_boost("Nowhere Inc") == (0.0, None)


def test_cap_multiplier_only_for_prestige() -> None:
    p = _p()
    assert p.cap_for("Amazon", 5) == 15
    assert p.cap_for("Databricks", 5) == 15
    assert p.cap_for("Local Startup", 5) == 5


def test_word_boundary_no_false_match() -> None:
    p = _p()
    # "meta" must not match inside "Metabolic"; "apple" is a whole word though.
    assert p.tier("Metabolic Health Inc") is None
    assert p.tier("Apple") == "faang"


def test_extra_lists_extend() -> None:
    p = CompanyPrestige(boost_faang=0.1, extra_faang=("Acme AI",))
    assert p.tier("Acme AI") == "faang"
