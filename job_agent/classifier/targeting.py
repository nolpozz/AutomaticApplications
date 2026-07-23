"""Role-level targeting.

Down-weights roles that don't match the desired experience level / keywords (e.g.
full-time roles when the candidate wants internships). Applied as a multiplier on
the base score *before* prestige, so a prestige boost ranks on-target roles highest
but cannot lift an off-target role over the threshold.

Shared by the classifier (classify time) and scripts/rescore (offline re-score) so
both compute the exact same adjustment.
"""

from __future__ import annotations

import re


class LevelTargeting:
    def __init__(self, levels: list[str], keywords: list[str]) -> None:
        self.levels = {s.lower() for s in levels}
        self.keywords = {s.lower().strip() for s in keywords if s.strip()}
        # Match keywords on word boundaries so short tokens like "ms" match the
        # degree "MS" but not the substring inside "teams" / "systems".
        self._re: re.Pattern[str] | None = (
            re.compile(r"\b(" + "|".join(re.escape(k) for k in self.keywords) + r")\b", re.I)
            if self.keywords
            else None
        )

    @classmethod
    def from_pipeline(cls, pipeline: object) -> LevelTargeting:
        return cls(
            list(getattr(pipeline, "target_experience_levels", []) or []),
            list(getattr(pipeline, "target_keywords", []) or []),
        )

    @property
    def active(self) -> bool:
        return bool(self.levels or self._re is not None)

    def factor(self, *, level: str, title: str, description: str = "") -> float:
        """1.0 for on-target roles; a penalty (<1) for off-target ones.

        Keywords are matched on the TITLE only — role type ("intern", "co-op",
        "student researcher") lives in the title, whereas a description mentioning
        "graduate degree" does not make a full-time posting an internship.
        """
        if not self.active:
            return 1.0
        if level.lower() in self.levels or (self._re is not None and self._re.search(title)):
            return 1.0
        if level.lower() in {"senior", "staff", "principal"}:
            return 0.5
        return 0.6

    def describe(self) -> str:
        bits = sorted(self.levels | self.keywords)
        return ", ".join(bits)


def job_level(job: object) -> str:
    """Extract a comparable level string from a Job's experience_level field."""
    lvl = getattr(job, "experience_level", "")
    return lvl.value if hasattr(lvl, "value") else str(lvl)
