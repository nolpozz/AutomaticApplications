"""Domain-relevance gate.

Some postings clear the fit threshold on generic early-career signal despite
having nothing to do with the target domain — e.g. a bare "Software Engineer
Intern" from an aggregator list with a thin description. The ``DomainFilter``
multiplies the score by ``penalty`` when NONE of the domain keywords appear in
the role's title, description, or parsed skills, pushing off-domain roles below
threshold while leaving genuine matches untouched.

Keywords are matched on word boundaries, so short tokens like "ai" and "ml" do
not spuriously match "email" or "html".
"""

from __future__ import annotations

import re


class DomainFilter:
    def __init__(self, keywords: list[str] | tuple[str, ...], penalty: float = 1.0) -> None:
        self.keywords: tuple[str, ...] = tuple(k.lower().strip() for k in keywords if k.strip())
        self.penalty = penalty
        self._re: re.Pattern[str] | None = (
            re.compile(r"\b(" + "|".join(re.escape(k) for k in self.keywords) + r")\b", re.I)
            if self.keywords
            else None
        )

    @classmethod
    def from_pipeline(cls, pipeline: object) -> DomainFilter:
        return cls(
            getattr(pipeline, "domain_keywords", []) or [],
            float(getattr(pipeline, "domain_penalty", 1.0) or 1.0),
        )

    @property
    def active(self) -> bool:
        return self._re is not None and self.penalty < 1.0

    def matches(self, *texts: str) -> bool:
        if self._re is None:
            return True
        return bool(self._re.search(" ".join(t for t in texts if t)))

    def factor(self, *texts: str) -> float:
        """1.0 when the role is on-domain, else ``penalty``."""
        return 1.0 if self.matches(*texts) else self.penalty
