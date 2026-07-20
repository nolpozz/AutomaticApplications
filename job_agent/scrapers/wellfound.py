"""Wellfound (formerly AngelList Talent) scraper — startup jobs.

Wellfound has no free public jobs API; live fetching requires an authorized
integration. Ships deterministic startup-flavored sample data by default.
"""

from __future__ import annotations

from job_agent.models.domain import Job, RemoteType
from job_agent.scrapers.base import AbstractScraper


class WellfoundScraper(AbstractScraper):
    source = "wellfound"

    def _fetch_live(self) -> list[Job]:
        # Placeholder for an authorized API integration; normalized output only.
        return []

    def _sample(self) -> list[Job]:
        return [
            self._job(
                title="Machine Learning Engineer (Early Stage)",
                company="Nimbus AI",
                url="https://wellfound.com/jobs/6001",
                location="Remote",
                salary="$140k-$180k + 0.5%-1.0% equity",
                remote=RemoteType.REMOTE,
                description=(
                    "Seed-stage startup building AI agents.\n- 2+ years ML/software\n"
                    "- Python, LLMs, and RAG\n- Wear many hats at an early company"
                ),
                external_id="wf-6001",
            ),
        ]
