"""Scraper registry — the one place boards are wired up.

Adding a board: implement a scraper, then add a line to ``_SCRAPERS``. Enabled
boards and per-board tokens/URLs come from settings and an optional
``config/sources.yaml``. Nothing else in the pipeline changes (design #8).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from job_agent.config.logging import get_logger
from job_agent.config.settings import Settings
from job_agent.scrapers.amazon import AmazonScraper
from job_agent.scrapers.ashby import AshbyScraper
from job_agent.scrapers.base import AbstractScraper, ScraperConfig
from job_agent.scrapers.company import CompanyPageScraper
from job_agent.scrapers.github import GitHubJobsScraper
from job_agent.scrapers.google import GoogleScraper
from job_agent.scrapers.greenhouse import GreenhouseScraper
from job_agent.scrapers.lever import LeverScraper
from job_agent.scrapers.linkedin import LinkedInScraper
from job_agent.scrapers.netflix import NetflixScraper
from job_agent.scrapers.spotify import SpotifyScraper
from job_agent.scrapers.wellfound import WellfoundScraper
from job_agent.scrapers.workday import WorkdayScraper
from job_agent.scrapers.yc import YCScraper

logger = get_logger(__name__)

_SCRAPERS: dict[str, type[AbstractScraper]] = {
    "greenhouse": GreenhouseScraper,
    "lever": LeverScraper,
    "ashby": AshbyScraper,
    "workday": WorkdayScraper,
    "amazon": AmazonScraper,
    "spotify": SpotifyScraper,
    "netflix": NetflixScraper,
    "google": GoogleScraper,
    "linkedin": LinkedInScraper,
    "wellfound": WellfoundScraper,
    "yc": YCScraper,
    "github": GitHubJobsScraper,
    "company": CompanyPageScraper,
}


# Boards whose "target" is a search query rather than a slug/URL. They are
# always live-capable and inherit the centralized ML/AI search queries.
_SEARCH_BOARDS = {"amazon", "netflix", "google", "spotify"}


def available_boards() -> list[str]:
    return sorted(_SCRAPERS)


def _load_sources_config(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("sources", {}) if isinstance(data, dict) else {}


def build_scrapers(
    settings: Settings,
    *,
    only: list[str] | None = None,
    offline: bool | None = None,
    sources_file: Path | str = "config/sources.yaml",
) -> list[AbstractScraper]:
    """Instantiate the enabled scrapers.

    ``offline=None`` means: run live if a board has slugs/urls configured,
    otherwise sample. Pass ``offline=True`` to force deterministic sample data.
    """
    sources_cfg = _load_sources_config(Path(sources_file))
    enabled = only or settings.pipeline.enabled_boards
    scrapers: list[AbstractScraper] = []
    for name in enabled:
        cls = _SCRAPERS.get(name)
        if cls is None:
            logger.warning("Unknown board %r (available: %s)", name, available_boards())
            continue
        board_cfg = sources_cfg.get(name, {})
        # Search-based boards need no slug/URL to go live. Others go live only
        # when the user configured slugs/urls/extra.
        has_targets = name in _SEARCH_BOARDS or bool(
            board_cfg.get("slugs") or board_cfg.get("urls") or board_cfg.get("extra")
        )
        # Inject the centralized ML/AI search queries unless the board overrides
        # them, so every search-based board covers the full role space.
        extra = dict(board_cfg.get("extra", {}))
        if name in _SEARCH_BOARDS and "queries" not in extra:
            extra["queries"] = list(settings.pipeline.search_queries)
        cfg = ScraperConfig(
            source=name,
            slugs=board_cfg.get("slugs", []),
            urls=board_cfg.get("urls", []),
            offline=(offline if offline is not None else not has_targets),
            max_jobs=settings.pipeline.max_jobs,
            extra=extra,
        )
        scrapers.append(cls(cfg))
    return scrapers
