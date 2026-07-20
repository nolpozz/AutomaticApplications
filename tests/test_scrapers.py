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
