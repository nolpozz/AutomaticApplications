"""Spotify careers scraper.

Spotify has no usable public jobs JSON API, but its engineering jobs index page
(``https://engineering.atspotify.com/jobs``) lists real posting URLs of the form
``https://www.lifeatspotify.com/jobs/<slug>`` directly in the HTML. We extract
those links (each is a real posting URL) and derive the title from the slug.
Override the index page with ``extra.index_url`` if desired.
"""

from __future__ import annotations

import re

from job_agent.models.domain import Job
from job_agent.scrapers.base import AbstractScraper

_INDEX = "https://engineering.atspotify.com/jobs"
_JOB_RE = re.compile(r"https://www\.lifeatspotify\.com/jobs/([a-z0-9][a-z0-9-]+)")


class SpotifyScraper(AbstractScraper):
    source = "spotify"
    requires_slugs = False

    def _fetch_live(self) -> list[Job]:
        index_url = self.config.extra.get("index_url", _INDEX)
        with self._client() as client:
            resp = client.get(index_url)
            resp.raise_for_status()
            return self._parse(resp.text)

    def _parse(self, html: str) -> list[Job]:
        jobs: list[Job] = []
        for slug in list(dict.fromkeys(_JOB_RE.findall(html)))[: self.config.max_jobs]:
            title = slug.replace("-", " ").title()
            jobs.append(
                self._job(
                    title=title,
                    company="Spotify",
                    url=f"https://www.lifeatspotify.com/jobs/{slug}",
                    description=f"{title} at Spotify. See the posting for full details.",
                    external_id=slug,
                )
            )
        return jobs

    def _sample(self) -> list[Job]:
        return [
            self._job(
                title="Machine Learning Engineer Intern",
                company="Spotify",
                url="https://www.lifeatspotify.com/jobs/machine-learning-engineer-intern",
                location="New York, NY",
                description=(
                    "Internship on personalization and recommendations.\n"
                    "- Pursuing a degree in CS or related\n- Python and ML fundamentals"
                ),
                external_id="spotify-ml-intern",
            ),
        ]
