"""Abstract scraper interface and shared helpers.

Every scraper inherits :class:`AbstractScraper` and emits normalized
:class:`Job` objects — downstream stages never see source-specific structure.

Each scraper implements two methods:

* ``_fetch_live`` — hit the real API/endpoint (used when configured & online).
* ``_sample`` — return deterministic example jobs for that source.

``fetch()`` orchestrates: it calls ``_fetch_live`` when configured and not in
offline mode, and falls back to ``_sample`` on any error or when offline. This
is what makes the whole repository runnable with no network access while keeping
real integrations one config change away. Adding a new board is: subclass, fill
the two methods, register in ``registry.py`` — nothing else changes (#8).
"""

from __future__ import annotations

import abc
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from job_agent.config.logging import get_logger
from job_agent.models.domain import (
    EmploymentType,
    ExperienceLevel,
    Job,
    RemoteType,
)

logger = get_logger(__name__)


@dataclass
class ScraperConfig:
    """Configuration for a single scraper instance."""

    source: str
    slugs: list[str] = field(default_factory=list)  # board tokens / company handles
    urls: list[str] = field(default_factory=list)
    enabled: bool = True
    offline: bool = False  # force sample mode (used by tests & default demo)
    max_jobs: int = 50
    timeout_seconds: int = 20
    extra: dict[str, Any] = field(default_factory=dict)


class AbstractScraper(abc.ABC):
    source: str = "base"

    def __init__(self, config: ScraperConfig) -> None:
        self.config = config

    # -- to implement per source -------------------------------------------
    @abc.abstractmethod
    def _fetch_live(self) -> list[Job]: ...

    @abc.abstractmethod
    def _sample(self) -> list[Job]: ...

    # -- orchestration ------------------------------------------------------
    def fetch(self) -> list[Job]:
        jobs: list[Job]
        use_live = not self.config.offline and (self.config.slugs or self.config.urls)
        if use_live:
            try:
                jobs = self._fetch_live()
                if not jobs:
                    logger.info("%s: live fetch returned no jobs; using sample", self.source)
                    jobs = self._sample()
            except Exception as exc:
                logger.warning("%s: live fetch failed (%s); using sample", self.source, exc)
                jobs = self._sample()
        else:
            jobs = self._sample()
        deduped = _dedupe_within(jobs)
        capped = deduped[: self.config.max_jobs]
        logger.info("%s: yielded %d jobs", self.source, len(capped))
        return capped

    # -- helpers ------------------------------------------------------------
    def _client(self) -> httpx.Client:
        return httpx.Client(
            timeout=self.config.timeout_seconds,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; job-agent/0.1; +https://example.com)",
                "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
                # Disable compression: reusing one client for many sequential
                # requests can trigger httpx's "cannot use a decompressobj
                # multiple times" error on some servers (e.g. amazon.jobs).
                "Accept-Encoding": "identity",
            },
            follow_redirects=True,
        )

    def _queries(self) -> list[str]:
        """Search terms for search-based boards. Configured via ``extra.queries``.

        Defaults to a single empty query (i.e. "all jobs") when unset.
        """
        q = self.config.extra.get("queries")
        if isinstance(q, list) and q:
            return [str(x) for x in q]
        if isinstance(q, str) and q.strip():
            return [q]
        return [""]

    def _search_location(self) -> str | None:
        loc = self.config.extra.get("location")
        return str(loc) if loc else None

    def _job(
        self,
        *,
        title: str,
        company: str,
        url: str,
        description: str = "",
        location: str | None = None,
        salary: str | None = None,
        remote: RemoteType | None = None,
        employment_type: EmploymentType = EmploymentType.FULL_TIME,
        experience_level: ExperienceLevel = ExperienceLevel.UNKNOWN,
        external_id: str | None = None,
        date_posted: datetime | None = None,
        raw: dict[str, Any] | None = None,
    ) -> Job:
        return Job(
            title=title.strip(),
            company=company.strip(),
            url=url,
            description=description.strip(),
            location=location,
            salary=salary,
            remote=remote or infer_remote(f"{title} {location or ''} {description}"),
            employment_type=employment_type,
            experience_level=(
                infer_level(title)
                if experience_level == ExperienceLevel.UNKNOWN
                else experience_level
            ),
            external_id=external_id or url,
            date_posted=date_posted,
            source=self.source,
            raw=raw or {},
        )


# -- module-level normalization utilities -----------------------------------
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\n{3,}")


def html_to_text(html: str) -> str:
    if not html:
        return ""
    text = _TAG_RE.sub("", html)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#39;", "'")
    text = re.sub(r"[ \t]+", " ", text)
    return _WS_RE.sub("\n\n", text).strip()


def infer_remote(text: str) -> RemoteType:
    low = text.lower()
    if "hybrid" in low:
        return RemoteType.HYBRID
    if "remote" in low:
        return RemoteType.REMOTE
    if any(k in low for k in ("on-site", "onsite", "in office", "in-office")):
        return RemoteType.ONSITE
    return RemoteType.UNKNOWN


def infer_level(title: str) -> ExperienceLevel:
    low = title.lower()
    if any(k in low for k in ("intern", "internship")):
        return ExperienceLevel.INTERN
    if any(k in low for k in ("principal", "staff", "distinguished")):
        return ExperienceLevel.STAFF
    if any(k in low for k in ("senior", "sr.", "lead")):
        return ExperienceLevel.SENIOR
    if any(k in low for k in ("junior", "jr.", "entry", "new grad", "graduate")):
        return ExperienceLevel.ENTRY
    return ExperienceLevel.MID


def parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000 if value > 1e12 else value, tz=timezone.utc)
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, OSError):
        return None


def _dedupe_within(jobs: Iterable[Job]) -> list[Job]:
    seen: set[str] = set()
    out: list[Job] = []
    for job in jobs:
        key = job.dedup_key()
        if key not in seen:
            seen.add(key)
            out.append(job)
    return out
