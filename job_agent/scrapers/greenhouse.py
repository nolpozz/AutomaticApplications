"""Greenhouse job-board scraper (public boards API)."""

from __future__ import annotations

from job_agent.models.domain import Job
from job_agent.scrapers.base import AbstractScraper, html_to_text, parse_iso


class GreenhouseScraper(AbstractScraper):
    source = "greenhouse"
    API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"

    def _fetch_live(self) -> list[Job]:
        jobs: list[Job] = []
        with self._client() as client:
            for token in self.config.slugs:
                resp = client.get(self.API.format(token=token))
                resp.raise_for_status()
                for item in resp.json().get("jobs", []):
                    loc = (item.get("location") or {}).get("name")
                    jobs.append(
                        self._job(
                            title=item.get("title", ""),
                            company=self.config.extra.get("company", token),
                            url=item.get("absolute_url", ""),
                            description=html_to_text(item.get("content", "")),
                            location=loc,
                            external_id=str(item.get("id")),
                            date_posted=parse_iso(item.get("updated_at")),
                            raw={"board_token": token},
                        )
                    )
        return jobs

    def _sample(self) -> list[Job]:
        return [
            self._job(
                title="Machine Learning Engineer",
                company="Aperture Labs",
                url="https://boards.greenhouse.io/aperture/jobs/1001",
                location="San Francisco, CA (Hybrid)",
                salary="$170,000 - $210,000",
                description=(
                    "We are hiring an ML Engineer to build LLM-powered products.\n"
                    "- 3+ years of experience with Python and PyTorch\n"
                    "- Experience with NLP, RAG, and retrieval systems\n"
                    "- BS in Computer Science or related field\n"
                    "We sponsor visas for exceptional candidates."
                ),
                external_id="gh-1001",
            ),
            self._job(
                title="Senior Data Scientist",
                company="Aperture Labs",
                url="https://boards.greenhouse.io/aperture/jobs/1002",
                location="Remote (US)",
                description=(
                    "Own experimentation and modeling for our recommendations team.\n"
                    "- 5+ years in data science with strong SQL and Python\n"
                    "- A/B testing and statistics\n"
                    "- Master's preferred"
                ),
                external_id="gh-1002",
            ),
            self._job(
                title="Marketing Coordinator",
                company="Aperture Labs",
                url="https://boards.greenhouse.io/aperture/jobs/1003",
                location="Chicago, IL (Hybrid)",
                salary="$52,000 - $62,000",
                description=(
                    "Support our brand and growth team across social, email, and content.\n"
                    "- Bachelor's in Marketing, Communication, or related field\n"
                    "- Experience with social media, content marketing, and SEO\n"
                    "- Familiarity with Google Analytics, HubSpot, and Canva\n"
                    "- Strong copywriting and an eye for what performs"
                ),
                external_id="gh-1003",
            ),
        ]
