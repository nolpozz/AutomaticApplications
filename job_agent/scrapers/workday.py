"""Workday scraper (CxS JSON API).

Workday exposes a JSON endpoint per tenant/site:
``POST {host}/wday/cxs/{tenant}/{site}/jobs``. Configure each target via
``extra`` keys ``host``, ``tenant``, ``site``. Falls back to sample data.
"""

from __future__ import annotations

from job_agent.models.domain import Job
from job_agent.scrapers.base import AbstractScraper, html_to_text


class WorkdayScraper(AbstractScraper):
    source = "workday"
    requires_slugs = False

    def _fetch_live(self) -> list[Job]:
        targets = self.config.extra.get("targets", [])
        jobs: list[Job] = []
        with self._client() as client:
            for target in targets:
                host, tenant, site = target["host"], target["tenant"], target["site"]
                url = f"{host}/wday/cxs/{tenant}/{site}/jobs"
                resp = client.post(url, json={"limit": 20, "offset": 0, "searchText": ""})
                resp.raise_for_status()
                for item in resp.json().get("jobPostings", []):
                    path = item.get("externalPath", "")
                    jobs.append(
                        self._job(
                            title=item.get("title", ""),
                            company=target.get("company", tenant),
                            url=f"{host}{path}",
                            description=html_to_text(item.get("jobDescription", "")),
                            location=item.get("locationsText"),
                            external_id=item.get("bulletFields", [None])[0],
                        )
                    )
        return jobs

    def _sample(self) -> list[Job]:
        return [
            self._job(
                title="Software Engineer, Machine Learning",
                company="Globex",
                url="https://globex.wd1.myworkdayjobs.com/careers/job/4001",
                location="Seattle, WA",
                description=(
                    "Build ML infrastructure at scale.\n- 3+ years software engineering\n"
                    "- Python and distributed systems\n- BS in CS required"
                ),
                external_id="wd-4001",
            ),
        ]
