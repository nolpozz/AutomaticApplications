"""Netflix careers scraper (Eightfold-powered public API).

Endpoint: ``https://explore.jobs.netflix.net/api/apply/v2/jobs`` with
``domain=netflix.com``. Positions carry a ``canonicalPositionUrl`` (the real
posting URL); we build one from the id if it is absent. Configure ``extra.queries``
and an optional ``extra.location``.
"""

from __future__ import annotations

from typing import Any

from job_agent.models.domain import Job
from job_agent.scrapers.base import AbstractScraper, html_to_text, parse_iso

_HOST = "https://explore.jobs.netflix.net"


class NetflixScraper(AbstractScraper):
    source = "netflix"
    API = f"{_HOST}/api/apply/v2/jobs"

    def _fetch_live(self) -> list[Job]:
        jobs: list[Job] = []
        with self._client() as client:
            for query in self._queries():
                params: dict[str, Any] = {
                    "domain": "netflix.com",
                    "query": query,
                    "start": 0,
                    "num": min(self.config.max_jobs, 100),
                }
                loc = self._search_location()
                if loc:
                    params["location"] = loc
                resp = client.get(self.API, params=params)
                resp.raise_for_status()
                jobs.extend(self._parse(resp.json()))
        return jobs

    def _parse(self, payload: dict[str, Any]) -> list[Job]:
        jobs: list[Job] = []
        for item in payload.get("positions", []):
            job_id = item.get("id") or item.get("display_job_id")
            url = (
                item.get("canonicalPositionUrl")
                or item.get("positionUrl")
                or (f"{_HOST}/careers/job/{job_id}?domain=netflix.com" if job_id else "")
            )
            if not url:
                continue
            jobs.append(
                self._job(
                    title=item.get("name", ""),
                    company="Netflix",
                    url=url,
                    description=html_to_text(item.get("job_description", "")),
                    location=_locations(item),
                    external_id=str(job_id or ""),
                    date_posted=parse_iso(item.get("t_update")),
                    raw={"department": item.get("department")},
                )
            )
        return jobs

    def _sample(self) -> list[Job]:
        return [
            self._job(
                title="Machine Learning Intern, Personalization",
                company="Netflix",
                url="https://explore.jobs.netflix.net/careers/job/790299000000?domain=netflix.com",
                location="Los Gatos, CA",
                description=(
                    "Internship on recommendation systems.\n- Graduate student in ML/CS\n"
                    "- Python, PyTorch, and strong fundamentals"
                ),
                external_id="nflx-790299000000",
            ),
        ]


def _locations(item: dict[str, Any]) -> str | None:
    locs = item.get("locations")
    if isinstance(locs, list) and locs:
        return ", ".join(str(x) for x in locs if x)
    return item.get("location")
