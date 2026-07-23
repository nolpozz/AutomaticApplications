"""Company-prestige signal.

Ranks employers into tiers so FAANG+ and top AI labs surface highest, high-growth
startups/unicorns next, and everything else unweighted. The tier drives two things:

  * a score boost applied after classification (FAANG+ > high-growth), so
    prestigious employers rank at the top of the review queue; and
  * a per-company cap multiplier in the ranking stage, so a prestigious company
    keeps more of its roles instead of being trimmed to the flat top-N.

Matching is on word boundaries over a normalized company name, so "meta" matches
"Meta" / "Meta Platforms" but not "metabolic".
"""

from __future__ import annotations

import re

# Big tech + frontier AI labs.
FAANG_PLUS: tuple[str, ...] = (
    "google",
    "alphabet",
    "youtube",
    "deepmind",
    "waymo",
    "meta",
    "facebook",
    "instagram",
    "apple",
    "amazon",
    "aws",
    "amazon web services",
    "netflix",
    "microsoft",
    "linkedin",
    "nvidia",
    "openai",
    "anthropic",
    "spotify",
    "tiktok",
    "bytedance",
    "tesla",
)

# High-growth startups / unicorns (AI-heavy).
HIGH_GROWTH: tuple[str, ...] = (
    "scale ai",
    "scale",
    "databricks",
    "cohere",
    "mistral",
    "perplexity",
    "hugging face",
    "huggingface",
    "runway",
    "runwayml",
    "figure",
    "anduril",
    "ramp",
    "stripe",
    "notion",
    "rippling",
    "sierra",
    "anysphere",
    "cursor",
    "mercor",
    "glean",
    "harvey",
    "character ai",
    "character.ai",
    "adept",
    "together ai",
    "fireworks",
    "groq",
    "cerebras",
    "sambanova",
    "wandb",
    "weights & biases",
    "weights and biases",
    "pinecone",
    "replit",
    "vercel",
    "snowflake",
    "confluent",
    "datadog",
    "coinbase",
    "robinhood",
    "brex",
)


def _pattern(terms: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile(r"\b(" + "|".join(re.escape(t) for t in terms) + r")\b", re.I)


class CompanyPrestige:
    def __init__(
        self,
        *,
        boost_faang: float = 0.0,
        boost_growth: float = 0.0,
        cap_multiplier: int = 1,
        extra_faang: tuple[str, ...] = (),
        extra_growth: tuple[str, ...] = (),
    ) -> None:
        self.boost_faang = boost_faang
        self.boost_growth = boost_growth
        self.cap_multiplier = max(1, cap_multiplier)
        self._faang = _pattern(FAANG_PLUS + tuple(e.lower() for e in extra_faang))
        self._growth = _pattern(HIGH_GROWTH + tuple(e.lower() for e in extra_growth))

    @classmethod
    def from_pipeline(cls, pipeline: object) -> CompanyPrestige:
        boost = float(getattr(pipeline, "prestige_boost", 0.0) or 0.0)
        return cls(
            boost_faang=boost,
            boost_growth=round(boost * 0.6, 4),  # high-growth ranks below FAANG+
            cap_multiplier=int(getattr(pipeline, "prestige_cap_multiplier", 1) or 1),
            extra_faang=tuple(getattr(pipeline, "prestige_extra_faang", []) or []),
            extra_growth=tuple(getattr(pipeline, "prestige_extra_growth", []) or []),
        )

    @property
    def active(self) -> bool:
        return self.boost_faang != 0.0 or self.boost_growth != 0.0 or self.cap_multiplier > 1

    def tier(self, company: str) -> str | None:
        if company and self._faang.search(company):
            return "faang"
        if company and self._growth.search(company):
            return "growth"
        return None

    def score_boost(self, company: str) -> tuple[float, str | None]:
        tier = self.tier(company)
        if tier == "faang":
            return self.boost_faang, "faang"
        if tier == "growth":
            return self.boost_growth, "growth"
        return 0.0, None

    def cap_for(self, company: str, base_cap: int) -> int:
        """The per-company cap for this company (multiplied for prestigious ones)."""
        return base_cap * self.cap_multiplier if self.tier(company) else base_cap
