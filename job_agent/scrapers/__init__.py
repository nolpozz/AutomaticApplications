"""Modular job scrapers, all emitting normalized Job objects."""

from job_agent.scrapers.base import AbstractScraper, ScraperConfig
from job_agent.scrapers.registry import available_boards, build_scrapers

__all__ = ["AbstractScraper", "ScraperConfig", "available_boards", "build_scrapers"]
