"""Ashby job-board scraper (public posting API)."""

from __future__ import annotations

from job_agent.models.domain import Job
from job_agent.scrapers.base import AbstractScraper, html_to_text, parse_iso


class AshbyScraper(AbstractScraper):
    source = "ashby"
    API = "https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=true"

    def _fetch_live(self) -> list[Job]:
        jobs: list[Job] = []
        with self._client() as client:
            for org in self.config.slugs:
                resp = client.get(self.API.format(org=org))
                resp.raise_for_status()
                for item in resp.json().get("jobs", []):
                    comp = item.get("compensation", {}) or {}
                    jobs.append(
                        self._job(
                            title=item.get("title", ""),
                            company=self.config.extra.get("company", org),
                            url=item.get("jobUrl", ""),
                            description=item.get("descriptionPlain")
                            or html_to_text(item.get("descriptionHtml", "")),
                            location=item.get("location"),
                            salary=comp.get("compensationTierSummary"),
                            external_id=str(item.get("id")),
                            date_posted=parse_iso(item.get("publishedAt")),
                        )
                    )
        return jobs

    def _sample(self) -> list[Job]:
        return [
            self._job(
                title="Founding ML Engineer",
                company="Vector Systems",
                url="https://jobs.ashbyhq.com/vector/3001",
                location="Remote (Global)",
                salary="$190k-$240k + equity",
                description=(
                    "Early engineer to own our ML platform end to end.\n"
                    "- 4+ years Python; production ML experience\n"
                    "- Comfortable with FAISS, embeddings, and serving\n"
                    "- Startup mindset"
                ),
                external_id="ashby-3001",
            ),
        ]
