"""Scraper tests (offline sample mode)."""

from __future__ import annotations

import pytest

from job_agent.scrapers.base import ScraperConfig
from job_agent.scrapers.registry import available_boards, build_scrapers


@pytest.mark.parametrize("board", available_boards())
def test_every_scraper_yields_normalized_jobs(settings, board) -> None:  # type: ignore[no-untyped-def]
    scrapers = build_scrapers(settings, only=[board], offline=True)
    assert len(scrapers) == 1
    jobs = scrapers[0].fetch()
    assert jobs, f"{board} produced no sample jobs"
    for job in jobs:
        assert job.title and job.company and job.url
        assert job.source == board
        assert job.dedup_key()


def test_registry_skips_unknown_board(settings) -> None:  # type: ignore[no-untyped-def]
    scrapers = build_scrapers(settings, only=["greenhouse", "does-not-exist"], offline=True)
    assert len(scrapers) == 1


def test_max_jobs_cap_is_respected() -> None:
    from job_agent.scrapers.greenhouse import GreenhouseScraper

    cfg = ScraperConfig(source="greenhouse", offline=True, max_jobs=1)
    assert len(GreenhouseScraper(cfg).fetch()) == 1


def test_search_boards_inherit_centralized_queries(settings, tmp_path) -> None:
    # No sources file -> search boards still go live-capable and inherit queries.
    from job_agent.scrapers.registry import build_scrapers

    settings.pipeline.search_queries = ["machine learning engineer", "ai research"]
    scrapers = build_scrapers(
        settings, only=["amazon", "google", "netflix"], sources_file=tmp_path / "none.yaml"
    )
    for sc in scrapers:
        assert sc.config.extra["queries"] == ["machine learning engineer", "ai research"]
        assert sc._queries() == ["machine learning engineer", "ai research"]
        assert sc.config.offline is False  # search boards are live-capable by default


def test_default_search_queries_cover_ml_ai_roles() -> None:
    from job_agent.config.settings import DEFAULT_SEARCH_QUERIES

    joined = " ".join(DEFAULT_SEARCH_QUERIES).lower()
    for term in [
        "machine learning",
        "ai research",
        "research scientist",
        "applied scientist",
        "nlp",
        "large language models",
        "computer vision",
        "deep learning",
    ]:
        assert term in joined
