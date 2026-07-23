"""Lever job-board scraper (public postings API)."""

from __future__ import annotations

from job_agent.config.logging import get_logger
from job_agent.models.domain import Job
from job_agent.scrapers.base import AbstractScraper, html_to_text, parse_iso

logger = get_logger(__name__)


class LeverScraper(AbstractScraper):
    source = "lever"
    API = "https://api.lever.co/v0/postings/{company}?mode=json"

    def _fetch_live(self) -> list[Job]:
        jobs: list[Job] = []
        with self._client() as client:
            for company in self.config.slugs:
                try:
                    resp = client.get(self.API.format(company=company))
                    resp.raise_for_status()
                    items = resp.json()
                except Exception as exc:
                    logger.warning("lever: slug %r failed (%s); skipping", company, exc)
                    continue
                for item in items:
                    categories = item.get("categories", {}) or {}
                    jobs.append(
                        self._job(
                            title=item.get("text", ""),
                            company=self.config.extra.get("company", company),
                            url=item.get("hostedUrl", ""),
                            description=item.get("descriptionPlain")
                            or html_to_text(item.get("description", "")),
                            location=categories.get("location"),
                            external_id=str(item.get("id")),
                            date_posted=parse_iso(item.get("createdAt")),
                            raw={"commitment": categories.get("commitment")},
                        )
                    )
        return jobs

    def _sample(self) -> list[Job]:
        return [
            self._job(
                title="NLP Research Engineer",
                company="Lexi AI",
                url="https://jobs.lever.co/lexi/2001",
                location="New York, NY",
                salary="$180k-$230k",
                description=(
                    "Join our applied research team working on retrieval-augmented "
                    "generation.\n- Strong Python and PyTorch\n- Publications in NLP/ML "
                    "venues a plus\n- Experience with transformers and embeddings"
                ),
                external_id="lever-2001",
            ),
            self._job(
                title="AI Research Intern",
                company="Lexi AI",
                url="https://jobs.lever.co/lexi/2002",
                location="Remote",
                description=(
                    "Summer internship on LLM evaluation.\n- Pursuing a BS/MS/PhD\n"
                    "- Familiarity with Python and deep learning"
                ),
                external_id="lever-2002",
            ),
            self._job(
                title="Social Media Marketing Intern",
                company="Lexi AI",
                url="https://jobs.lever.co/lexi/2003",
                location="Remote (US)",
                description=(
                    "Help run our social channels and content calendar this summer.\n"
                    "- Pursuing a Bachelor's in Marketing or Communication\n"
                    "- Experience with Instagram, TikTok, and content creation\n"
                    "- Comfortable with analytics and basic design tools like Canva"
                ),
                external_id="lever-2003",
            ),
        ]
