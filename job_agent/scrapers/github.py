"""GitHub aggregator scraper for community internship/new-grad job lists.

These repos (SimplifyJobs, speedyapply, vanshb03, ...) are the highest-signal
source for internships and are updated constantly by bots. They come in two
shapes, both handled here:

* **Markdown tables** (speedyapply, vanshb03): ``| Company | Role | Location | ... |``
* **HTML tables** (SimplifyJobs): ``<table><tr><td>...</td></tr>``

In both, the real posting URL is the ``<a href>`` that wraps an ``<img>`` (the
"Apply" badge); the company's own link has no image. That single rule extracts
the posting URL from either format. ``↳`` in the company column means "same
company as the row above". Closed roles (no apply badge) are skipped.

Configure repos via ``slugs`` as ``owner/repo`` (optionally ``owner/repo/path``).
Branches ``dev``, ``main``, ``master`` are tried in order.
"""

from __future__ import annotations

import re

from job_agent.config.logging import get_logger
from job_agent.models.domain import Job
from job_agent.scrapers.base import AbstractScraper

logger = get_logger(__name__)

_RAW = "https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
_BRANCHES = ("dev", "main", "master")

_A_RE = re.compile(r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL | re.IGNORECASE)
_TR_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
_TD_RE = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_CONTINUATION = {"↳", "⤷", "->", "→", ""}


class GitHubJobsScraper(AbstractScraper):
    source = "github"

    def _fetch_live(self) -> list[Job]:
        jobs: list[Job] = []
        with self._client() as client:
            for slug in self.config.slugs:
                owner, repo, path = _parse_slug(slug)
                for branch in _BRANCHES:
                    url = _RAW.format(owner=owner, repo=repo, branch=branch, path=path)
                    resp = client.get(url)
                    if resp.status_code == 200 and len(resp.text) > 200:
                        parsed = self._parse(resp.text, f"{owner}/{repo}")
                        logger.info("%s@%s: %d jobs", f"{owner}/{repo}", branch, len(parsed))
                        jobs.extend(parsed)
                        break
        return jobs

    def _parse(self, content: str, repo: str) -> list[Job]:
        if "<tr" in content.lower() and "<td" in content.lower():
            jobs = self._parse_html_table(content, repo)
            # Some repos mix an HTML table with extra markdown tables; capture both.
            if "\n|" in content:
                jobs.extend(self._parse_markdown_table(content, repo))
            return jobs
        return self._parse_markdown_table(content, repo)

    def _parse_html_table(self, content: str, repo: str) -> list[Job]:
        jobs: list[Job] = []
        last_company = ""
        for tr in _TR_RE.findall(content):
            if "<th" in tr.lower():
                continue
            cells = _TD_RE.findall(tr)
            if len(cells) < 3:
                continue
            job, last_company = self._row_to_job(cells, tr, repo, last_company)
            if job:
                jobs.append(job)
        return jobs

    def _parse_markdown_table(self, content: str, repo: str) -> list[Job]:
        jobs: list[Job] = []
        last_company = ""
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped.startswith("|"):
                continue
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cells) < 3 or set("".join(cells)) <= set("-: "):
                continue  # separator row
            if _clean_text(cells[0]).lower() in {"company", "name", "company name"}:
                continue
            job, last_company = self._row_to_job(cells, stripped, repo, last_company)
            if job:
                jobs.append(job)
        return jobs

    def _row_to_job(
        self, cells: list[str], row_html: str, repo: str, last_company: str
    ) -> tuple[Job | None, str]:
        posting_url = _apply_url(row_html)
        if not posting_url:
            return None, last_company  # header, separator, or closed role

        company = _clean_text(cells[0])
        if company in _CONTINUATION or not company:
            company = last_company
        else:
            last_company = company
        role = _clean_text(cells[1]) if len(cells) > 1 else "Software Engineer Intern"
        location = _clean_text(cells[2]) if len(cells) > 2 else None
        if not company:
            return None, last_company

        job = self._job(
            title=role or "Software Engineer Intern",
            company=company,
            url=posting_url,
            location=location,
            description=f"Aggregated from github.com/{repo}. {role} at {company}.",
            raw={"repo": repo},
        )
        return job, last_company

    def _sample(self) -> list[Job]:
        return [
            self._job(
                title="Machine Learning Intern",
                company="Beacon Research",
                url="https://beacon.example.com/careers/ml-intern",
                location="Remote",
                description=(
                    "Aggregated from github.com/example/ai-internships. "
                    "Summer ML internship.\n- Graduate student in ML/CS\n- Python, PyTorch"
                ),
                raw={"repo": "example/ai-internships"},
            ),
        ]


def _apply_url(row_html: str) -> str | None:
    """The posting URL is the href of the ``<a>`` that wraps an Apply ``<img>``.

    Prefers a direct company link over a simplify.jobs tracker when both exist.
    """
    badges = [href for href, inner in _A_RE.findall(row_html) if "<img" in inner.lower()]
    if not badges:
        return None
    direct = [b for b in badges if "simplify.jobs" not in b and "redirect." not in b]
    return (direct or badges)[0]


def _clean_text(cell: str) -> str:
    text = _A_RE.sub(lambda m: _TAG_RE.sub("", m.group(2)), cell)  # keep <a> inner text
    text = _TAG_RE.sub("", text)  # strip remaining tags
    text = re.sub(r"[*`_]", "", text)  # markdown emphasis
    # Drop common status/flag emoji used in these lists.
    text = re.sub(r"[🔒🛂🇺🇸🔥⭐️✅🎓💰→↳⤷]", "", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("</br>", ", ")
    return re.sub(r"\s+", " ", text).strip()


def _parse_slug(slug: str) -> tuple[str, str, str]:
    parts = slug.split("/")
    owner, repo = parts[0], parts[1]
    path = "/".join(parts[2:]) if len(parts) > 2 else "README.md"
    return owner, repo, path
