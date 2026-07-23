"""Amazon careers scraper (public ``amazon.jobs`` search JSON API).

Endpoint: ``https://www.amazon.jobs/en/search.json`` with query params. Each
result carries a ``job_path`` (e.g. ``/en/jobs/2481234/...``); the real posting
URL is ``https://www.amazon.jobs`` + that path. Configure search terms via
``extra.queries`` and an optional ``extra.location``.
"""

from __future__ import annotations

from typing import Any

from job_agent.models.domain import Job
from job_agent.scrapers.base import AbstractScraper, html_to_text, parse_iso

_BASE = "https://www.amazon.jobs"


class AmazonScraper(AbstractScraper):
    source = "amazon"
    requires_slugs = False
    API = f"{_BASE}/en/search.json"

    def _fetch_live(self) -> list[Job]:
        jobs: list[Job] = []
        with self._client() as client:
            for query in self._queries():
                params: dict[str, Any] = {
                    "base_query": query,
                    "result_limit": min(self.config.max_jobs, 100),
                    "sort": "recent",
                    "offset": 0,
                }
                # Country filter is opt-in: the default (unfiltered) endpoint is
                # what returns results; adding a country code can zero them out.
                country = self.config.extra.get("country")
                if country:
                    params["normalized_country_code[]"] = country
                loc = self._search_location()
                if loc:
                    params["normalized_location[]"] = loc
                resp = client.get(self.API, params=params)
                resp.raise_for_status()
                jobs.extend(self._parse(resp.json()))
        return jobs

    def _parse(self, payload: dict[str, Any]) -> list[Job]:
        jobs: list[Job] = []
        for item in payload.get("jobs", []):
            path = item.get("job_path") or ""
            url = f"{_BASE}{path}" if path.startswith("/") else (path or item.get("url", ""))
            if not url:
                continue  # never record a job without a posting URL
            description = " ".join(
                filter(
                    None,
                    [
                        item.get("description", ""),
                        item.get("basic_qualifications", ""),
                        item.get("preferred_qualifications", ""),
                    ],
                )
            )
            jobs.append(
                self._job(
                    title=item.get("title", ""),
                    company="Amazon",
                    url=url,
                    description=html_to_text(description),
                    location=item.get("normalized_location") or item.get("location"),
                    external_id=str(item.get("id_icims") or item.get("id") or ""),
                    date_posted=parse_iso(item.get("posted_date")),
                    raw={"team": item.get("business_category")},
                )
            )
        return jobs

    def _sample(self) -> list[Job]:
        return [
            self._job(
                title="Applied Scientist Intern, AWS AI",
                company="Amazon",
                url="https://www.amazon.jobs/en/jobs/2481234/applied-scientist-intern-aws-ai",
                location="Seattle, WA, USA",
                description=(
                    "Summer internship on large-scale ML.\n- Pursuing an MS or PhD\n"
                    "- Python, PyTorch, and NLP or ML fundamentals"
                ),
                external_id="amzn-2481234",
            ),
        ]
