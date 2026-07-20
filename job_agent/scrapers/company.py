"""Generic company career-page scraper via configurable URLs.

When a company's careers page is powered by a known ATS (Greenhouse/Lever/Ashby)
we delegate to that scraper by detecting the host — so adding a company is just a
URL in config, no new code. Unknown hosts fall back to sample data (a real HTML
scraper would be added per-site as an extension point).
"""

from __future__ import annotations

from urllib.parse import urlparse

from job_agent.config.logging import get_logger
from job_agent.models.domain import Job
from job_agent.scrapers.ashby import AshbyScraper
from job_agent.scrapers.base import AbstractScraper, ScraperConfig
from job_agent.scrapers.greenhouse import GreenhouseScraper
from job_agent.scrapers.lever import LeverScraper

logger = get_logger(__name__)


class CompanyPageScraper(AbstractScraper):
    source = "company"

    def _fetch_live(self) -> list[Job]:
        jobs: list[Job] = []
        for url in self.config.urls:
            host = urlparse(url).netloc
            token = _token_from_url(url)
            if "greenhouse" in host and token:
                jobs.extend(self._delegate(GreenhouseScraper, token))
            elif "lever" in host and token:
                jobs.extend(self._delegate(LeverScraper, token))
            elif "ashby" in host and token:
                jobs.extend(self._delegate(AshbyScraper, token))
            else:
                logger.info("No known ATS for %s; add a custom parser to extend.", host)
        return jobs

    def _delegate(self, scraper_cls: type[AbstractScraper], token: str) -> list[Job]:
        cfg = ScraperConfig(source=self.source, slugs=[token], offline=self.config.offline)
        return scraper_cls(cfg)._fetch_live()

    def _sample(self) -> list[Job]:
        return [
            self._job(
                title="Software Engineer, AI Platform",
                company="Umbrella Corp",
                url="https://careers.umbrella.example.com/jobs/8001",
                location="Austin, TX (Hybrid)",
                description=(
                    "Build the platform powering our AI products.\n"
                    "- 3+ years Python\n- Kubernetes, Docker, cloud\n- BS in CS or equivalent"
                ),
                external_id="co-8001",
            ),
        ]


def _token_from_url(url: str) -> str | None:
    parts = [p for p in urlparse(url).path.split("/") if p]
    return parts[-1] if parts else None
