"""Company blocklist.

Companies the candidate never wants to work at. Matched on word boundaries against
the company name (so "meta" blocks "Meta" but not "Metabolic"). Blocked jobs are
dropped at scrape time, before any embedding/LLM work.
"""

from __future__ import annotations

import re


class CompanyBlocklist:
    def __init__(self, names: list[str] | tuple[str, ...]) -> None:
        self.names = tuple(n.lower().strip() for n in names if n.strip())
        self._re: re.Pattern[str] | None = (
            re.compile(r"\b(" + "|".join(re.escape(n) for n in self.names) + r")\b", re.I)
            if self.names
            else None
        )

    @classmethod
    def from_pipeline(cls, pipeline: object) -> CompanyBlocklist:
        return cls(getattr(pipeline, "blocked_companies", []) or [])

    @property
    def active(self) -> bool:
        return self._re is not None

    def blocks(self, company: str) -> bool:
        return bool(self._re is not None and company and self._re.search(company))
