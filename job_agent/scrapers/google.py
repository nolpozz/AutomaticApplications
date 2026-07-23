"""Google careers scraper.

Google's public search API is gated, but the careers results page
(``.../jobs/results/?q=<query>``) embeds job result ids, and each individual job
page (``.../jobs/results/<id>``) exposes a clean ``og:title`` and
``og:description``. We list ids from the results page, then fetch each job page
(bounded by ``max_jobs``) for its title/description. Each job's URL is its real
posting page. Configure ``extra.queries`` and optional ``extra.location``.
"""

from __future__ import annotations

import re

from job_agent.models.domain import Job
from job_agent.scrapers.base import AbstractScraper, html_to_text

_RESULTS = "https://www.google.com/about/careers/applications/jobs/results/"
_ID_RE = re.compile(r"jobs/results/(\d+)")


class GoogleScraper(AbstractScraper):
    source = "google"
    requires_slugs = False

    def _fetch_live(self) -> list[Job]:
        jobs: list[Job] = []
        seen: set[str] = set()
        with self._client() as client:
            for query in self._queries():
                params = {"q": query}
                loc = self._search_location()
                if loc:
                    params["location"] = loc
                resp = client.get(_RESULTS, params=params)
                resp.raise_for_status()
                for job_id in self.extract_ids(resp.text):
                    if job_id in seen or len(seen) >= self.config.max_jobs:
                        continue
                    seen.add(job_id)
                    page = client.get(f"{_RESULTS}{job_id}")
                    if page.status_code != 200:
                        continue
                    job = self.job_from_page(job_id, page.text)
                    if job:
                        jobs.append(job)
        return jobs

    @staticmethod
    def extract_ids(html: str) -> list[str]:
        return list(dict.fromkeys(_ID_RE.findall(html)))

    def job_from_page(self, job_id: str, html: str) -> Job | None:
        title = _meta(html, "og:title") or _tag(html, "title") or ""
        title = re.sub(r"\s*[—–-]\s*Google Careers.*$", "", title).strip()  # noqa: RUF001
        if not title:
            return None
        description = _meta(html, "og:description") or ""
        return self._job(
            title=title,
            company="Google",
            url=f"{_RESULTS}{job_id}",
            description=html_to_text(description),
            external_id=job_id,
        )

    def _sample(self) -> list[Job]:
        return [
            self._job(
                title="Student Researcher, MS/PhD, Machine Learning",
                company="Google",
                url=f"{_RESULTS}128299363099607750",
                location="Mountain View, CA",
                description=(
                    "Research internship for MS/PhD students.\n- Coursework or research in ML\n"
                    "- Python; publications a plus"
                ),
                external_id="128299363099607750",
            ),
        ]


def _meta(html: str, prop: str) -> str | None:
    m = re.search(rf'<meta\s+property="{re.escape(prop)}"\s+content="([^"]+)"', html, re.IGNORECASE)
    if not m:
        m = re.search(
            rf'<meta\s+content="([^"]+)"\s+property="{re.escape(prop)}"', html, re.IGNORECASE
        )
    return m.group(1) if m else None


def _tag(html: str, tag: str) -> str | None:
    m = re.search(rf"<{tag}>([^<]+)</{tag}>", html, re.IGNORECASE)
    return m.group(1) if m else None
