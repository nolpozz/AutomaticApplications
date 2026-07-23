"""Post-classification score boosts.

The classifier produces a base ``overall_score`` in [0, 1] (from the LLM or the
heuristic fallback). A ``ScoreBoost`` adds small, transparent bonuses on top of
that base — for roles in preferred locations and for roles whose title contains
preferred keywords — capped so a boost can nudge a borderline role over the line
but never dominate the fit signal.

The same object is used at classify time (future runs) and by ``scripts/rescore``
to re-rank an already-classified database without any LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoreBoost:
    locations: tuple[str, ...] = ()
    location_boost: float = 0.0
    keywords: tuple[str, ...] = ()
    keyword_boost: float = 0.0
    cap: float = 0.1

    @classmethod
    def from_pipeline(cls, pipeline: object) -> ScoreBoost:
        """Build from a PipelineSettings-like object (duck-typed for reuse)."""
        return cls(
            locations=tuple(s.lower() for s in getattr(pipeline, "target_locations", []) or []),
            location_boost=float(getattr(pipeline, "location_boost", 0.0) or 0.0),
            keywords=tuple(s.lower() for s in getattr(pipeline, "boost_keywords", []) or []),
            keyword_boost=float(getattr(pipeline, "keyword_boost", 0.0) or 0.0),
            cap=float(getattr(pipeline, "boost_cap", 0.1) or 0.0),
        )

    @property
    def active(self) -> bool:
        loc_on = bool(self.locations) and self.location_boost != 0.0
        kw_on = bool(self.keywords) and self.keyword_boost != 0.0
        return loc_on or kw_on

    def compute(self, *, title: str, location: str) -> tuple[float, list[str]]:
        """Return (bonus, human-readable reasons) for one role."""
        bonus = 0.0
        reasons: list[str] = []
        loc = (location or "").lower()
        if self.locations and self.location_boost and any(t in loc for t in self.locations):
            bonus += self.location_boost
            reasons.append(f"Location boost +{self.location_boost:.2f} ({location})")
        text = (title or "").lower()
        hits = [k for k in self.keywords if k in text]
        if hits and self.keyword_boost:
            kb = min(self.keyword_boost * len(hits), self.cap)
            bonus += kb
            reasons.append(f"Role boost +{kb:.2f} ({', '.join(hits)})")
        bonus = min(bonus, self.cap)
        return round(bonus, 4), reasons

    def apply(self, overall: float, *, title: str, location: str) -> tuple[float, list[str]]:
        """Return (boosted_score, reasons); score is clamped to [0, 1]."""
        bonus, reasons = self.compute(title=title, location=location)
        return min(1.0, round(overall + bonus, 4)), reasons
