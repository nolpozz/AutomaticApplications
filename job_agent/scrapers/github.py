"""GitHub aggregator scraper.

Many communities maintain GitHub repos that aggregate AI/ML/new-grad jobs as
Markdown tables (e.g. "New-Grad-Positions" style lists). This scraper fetches
raw README files from configured repos and parses their tables into normalized
jobs. Configure via ``slugs`` as ``owner/repo`` or ``owner/repo/path/README.md``.
"""

from __future__ import annotations

import re

from job_agent.config.logging import get_logger
from job_agent.models.domain import Job
from job_agent.scrapers.base import AbstractScraper

logger = get_logger(__name__)

_RAW = "https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
_ROW_RE = re.compile(r"^\|(.+)\|\s*$")
_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")


class GitHubJobsScraper(AbstractScraper):
    source = "github"

    def _fetch_live(self) -> list[Job]:
        jobs: list[Job] = []
        with self._client() as client:
            for slug in self.config.slugs:
                owner, repo, path = _parse_slug(slug)
                for branch in ("main", "master"):
                    url = _RAW.format(owner=owner, repo=repo, branch=branch, path=path)
                    resp = client.get(url)
                    if resp.status_code == 200:
                        jobs.extend(self._parse_markdown_table(resp.text, repo))
                        break
        return jobs

    def _parse_markdown_table(self, markdown: str, repo: str) -> list[Job]:
        jobs: list[Job] = []
        for line in markdown.splitlines():
            row = _ROW_RE.match(line.strip())
            if not row:
                continue
            cells = [c.strip() for c in row.group(1).split("|")]
            if len(cells) < 2 or set("".join(cells)) <= set("-: "):
                continue  # separator or header row
            if cells[0].lower() in {"company", "name"}:
                continue
            company = _strip_md(cells[0])
            role = _strip_md(cells[1]) if len(cells) > 1 else "Software Engineer"
            location = _strip_md(cells[2]) if len(cells) > 2 else None
            link = _first_link("|".join(cells))
            if not company or not link:
                continue
            jobs.append(
                self._job(
                    title=role or "Software Engineer",
                    company=company,
                    url=link,
                    location=location,
                    description=f"Aggregated from github.com/{repo}. {role} at {company}.",
                    raw={"repo": repo},
                )
            )
        return jobs

    def _sample(self) -> list[Job]:
        return [
            self._job(
                title="AI Resident",
                company="Beacon Research",
                url="https://beacon.example.com/careers/ai-resident",
                location="Remote",
                description=(
                    "Aggregated from github.com/example/ai-jobs. One-year AI residency.\n"
                    "- BS/MS in a technical field\n- Python and ML fundamentals"
                ),
                raw={"repo": "example/ai-jobs"},
            ),
        ]


def _parse_slug(slug: str) -> tuple[str, str, str]:
    parts = slug.split("/")
    owner, repo = parts[0], parts[1]
    path = "/".join(parts[2:]) if len(parts) > 2 else "README.md"
    return owner, repo, path


def _strip_md(text: str) -> str:
    text = _LINK_RE.sub(r"\1", text)
    return re.sub(r"[*`_]", "", text).strip()


def _first_link(text: str) -> str | None:
    match = _LINK_RE.search(text)
    if match:
        return match.group(2)
    url = re.search(r"https?://\S+", text)
    return url.group(0).rstrip(")") if url else None
