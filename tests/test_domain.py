"""Domain-relevance gate: penalize off-domain roles, keep ML roles, no false hits."""

from __future__ import annotations

from job_agent.classifier.domain import DomainFilter

KW = ["machine learning", "ml", "ai", "nlp", "deep learning", "pytorch"]


def _f() -> DomainFilter:
    return DomainFilter(KW, penalty=0.6)


def test_inactive_when_penalty_one_or_no_keywords() -> None:
    assert DomainFilter(KW, penalty=1.0).active is False
    assert DomainFilter([], penalty=0.6).active is False
    assert _f().active is True


def test_on_domain_titles_not_penalized() -> None:
    f = _f()
    assert f.factor("Machine Learning Engineer Intern") == 1.0
    assert f.factor("NLP Research Intern") == 1.0
    assert f.factor("Software Engineer Intern", "we use PyTorch for models") == 1.0


def test_off_domain_generic_swe_is_penalized() -> None:
    f = _f()
    assert (
        f.factor("Software Engineer Intern", "Aggregated from github. Software Engineer Intern")
        == 0.6
    )


def test_short_tokens_use_word_boundaries() -> None:
    f = _f()
    # "ml" and "ai" must not match inside "html" / "email" / "available"
    assert f.matches("Frontend Intern building html and email flows") is False
    assert f.matches("AI Research Intern") is True
    assert f.matches("ML Platform Intern") is True
