"""LinkedIn scraper (guest job-search endpoint) — use only where permitted.

LinkedIn's Terms of Service restrict automated access. This scraper is disabled
by default and ships sample data. Enable it only if you have permission (e.g. an
official partner/API arrangement) by configuring ``urls``/``extra`` and clearing
``offline``. It is intentionally conservative and rate-limited.
"""

from __future__ import annotations

from job_agent.config.logging import get_logger
from job_agent.models.domain import ExperienceLevel, Job
from job_agent.scrapers.base import AbstractScraper

logger = get_logger(__name__)


class LinkedInScraper(AbstractScraper):
    source = "linkedin"

    def _fetch_live(self) -> list[Job]:
        # Deliberately not implemented against the private voyager endpoints to
        # avoid encouraging ToS violations. If you have an authorized API, wire
        # it here; the normalized `_job(...)` helper is all downstream needs.
        logger.warning("LinkedIn live fetch is disabled by default (ToS). Using sample data.")
        return []

    def _sample(self) -> list[Job]:
        return [
            self._job(
                title="Applied Scientist, NLP",
                company="Initech",
                url="https://www.linkedin.com/jobs/view/5001",
                location="Boston, MA (Hybrid)",
                description=(
                    "Applied science role on conversational AI.\n"
                    "- PhD or MS with 2+ years experience\n- Python, PyTorch, transformers\n"
                    "- Publications preferred"
                ),
                experience_level=ExperienceLevel.MID,
                external_id="li-5001",
            ),
        ]
