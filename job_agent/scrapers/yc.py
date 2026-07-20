"""Y Combinator (Work at a Startup) scraper.

The Work-at-a-Startup jobs API is not publicly documented/stable, so live
fetching is best-effort against configured company pages; sample data is used by
default so the pipeline always has YC-style postings to work with.
"""

from __future__ import annotations

from job_agent.models.domain import Job, RemoteType
from job_agent.scrapers.base import AbstractScraper


class YCScraper(AbstractScraper):
    source = "yc"

    def _fetch_live(self) -> list[Job]:
        # If a company slug list is configured we could resolve their WaaS pages;
        # kept as sample-first to avoid brittle scraping of a private surface.
        return []

    def _sample(self) -> list[Job]:
        return [
            self._job(
                title="Founding AI Engineer",
                company="Cortex (YC W24)",
                url="https://www.workatastartup.com/jobs/7001",
                location="San Francisco, CA",
                salary="$160k-$200k + 0.75% equity",
                remote=RemoteType.ONSITE,
                description=(
                    "Be the first AI hire at a YC-backed startup.\n"
                    "- 3+ years building software; some ML exposure\n"
                    "- Python; comfort with LLM APIs and evaluation\n"
                    "- Ship fast and own outcomes"
                ),
                external_id="yc-7001",
            ),
            self._job(
                title="Data Scientist",
                company="Ledger (YC S23)",
                url="https://www.workatastartup.com/jobs/7002",
                location="Remote (US)",
                remote=RemoteType.REMOTE,
                description=(
                    "Own analytics and modeling for a fintech startup.\n"
                    "- Strong SQL and Python\n- Experience with experimentation"
                ),
                external_id="yc-7002",
            ),
            self._job(
                title="Growth Marketing Associate",
                company="Cortex (YC W24)",
                url="https://www.workatastartup.com/jobs/7003",
                location="Remote (US)",
                remote=RemoteType.REMOTE,
                description=(
                    "Own top-of-funnel growth at an early-stage startup.\n"
                    "- Bachelor's in Marketing or related; 0-2 years experience\n"
                    "- Hands-on with email marketing, SEO, and paid social\n"
                    "- Comfortable with Google Analytics and running experiments"
                ),
                external_id="yc-7003",
            ),
        ]
