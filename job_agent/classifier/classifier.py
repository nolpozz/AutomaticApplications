"""LLM-based job-fit classifier with a reproducible heuristic fallback.

Scores are in [0, 1] across five dimensions plus an interview-probability
estimate and an overall score. The heuristic fallback is fully deterministic
(pure function of the job, its parsed requirements, and the knowledge base), so
mock-mode runs and tests are reproducible.
"""

from __future__ import annotations

import re
from typing import Any

from job_agent.classifier.boost import ScoreBoost
from job_agent.classifier.domain import DomainFilter
from job_agent.classifier.prestige import CompanyPrestige
from job_agent.classifier.targeting import LevelTargeting, job_level
from job_agent.config.logging import get_logger
from job_agent.knowledge.loader import KnowledgeBase
from job_agent.llm.base import LLMProvider
from job_agent.llm.prompts import PromptRegistry
from job_agent.models.domain import ClassifierScore, Job, ParsedJob, Recommendation

logger = get_logger(__name__)

_DEGREE_RANK = {"bachelor's": 1, "master's": 2, "phd": 3}
_WEIGHTS = {
    "technical": 0.35,
    "experience": 0.20,
    "education": 0.10,
    "research": 0.10,
    "interest": 0.25,
}
# The five fit dimensions, in ClassifierScore field order. The LLM (and the
# deterministic heuristic) rate each on a 1-100 scale; we divide by _SCALE and
# apply _WEIGHTS OURSELVES to compute the overall score. The model never returns
# an overall, so a user's preference weights are the ones applied for every
# provider — ratings stay consistent whichever LLM produced the dimensions.
_SUBSCORES = ("technical", "experience", "education", "research", "interest")
_SCALE = 100.0


class JobClassifier:
    def __init__(
        self,
        llm: LLMProvider,
        prompts: PromptRegistry,
        knowledge: KnowledgeBase,
        *,
        target_levels: list[str] | None = None,
        target_keywords: list[str] | None = None,
        target_description: str = "",
        boost: ScoreBoost | None = None,
        domain: DomainFilter | None = None,
        prestige: CompanyPrestige | None = None,
    ) -> None:
        self.llm = llm
        self.prompts = prompts
        self.knowledge = knowledge
        self._vocab = _candidate_vocabulary(knowledge)
        self._blob = _candidate_blob(knowledge)
        self._years = _candidate_years(knowledge)
        self._degree = _candidate_degree_rank(knowledge)
        self._has_research = bool(knowledge.by_category("research"))
        self._target_levels = {t.lower() for t in (target_levels or [])}
        self._target_keywords = {t.lower() for t in (target_keywords or [])}
        self._target_description = target_description.strip()
        self._targeting = LevelTargeting(target_levels or [], target_keywords or [])
        self._boost = boost
        self._domain = domain
        self._prestige = prestige

    def classify(self, job: Job, parsed: ParsedJob) -> tuple[ClassifierScore, str]:
        rendered = self.prompts.render(
            "classify_job",
            candidate_profile=self.knowledge.profile_summary(),
            title=job.title,
            company=job.company,
            required_skills=parsed.required_skills,
            preferred_skills=parsed.preferred_skills,
            years_experience=parsed.years_experience,
            programming_languages=parsed.programming_languages,
            frameworks=parsed.frameworks,
            degree_requirements=parsed.degree_requirements,
            research_requirements=parsed.research_requirements,
            target_preference=self._target_preference(),
        )
        data = self.llm.complete_json(
            rendered.messages(), fallback=lambda: self._heuristic(job, parsed), temperature=0.0
        )
        score = _coerce(data, self, job, parsed)
        score = self._finalize(score, job, parsed)
        return score, rendered.version

    def _finalize(self, score: ClassifierScore, job: Job, parsed: ParsedJob) -> ClassifierScore:
        """Adjust the base score: role-targeting penalty, then domain penalty, then
        company prestige, then location/keyword boosts. Prestige is applied AFTER
        the targeting penalty, so it ranks on-target (intern) roles highest but
        cannot rescue off-target (e.g. full-time) roles over the threshold."""
        overall = score.overall_score
        score.base_score = overall  # pre-adjustment score, for a consistent re-score
        notes: list[str] = []
        level_factor = self._targeting.factor(
            level=job_level(job), title=job.title, description=job.description
        )
        if level_factor < 1.0:
            overall = round(overall * level_factor, 4)
            notes.append(f"Off-target for {self._target_preference()}; x{level_factor:g}")
        if self._domain and self._domain.active:
            factor = self._domain.factor(domain_text(job, parsed))
            if factor < 1.0:
                overall = round(overall * factor, 4)
                notes.append(f"Off-domain (no ML/AI signal); x{factor:g}")
        if self._prestige and self._prestige.active:
            bonus, tier = self._prestige.score_boost(job.company)
            if bonus:
                overall = min(1.0, round(overall + bonus, 4))
                notes.append(f"Prestige boost +{bonus:g} ({tier})")
        if self._boost and self._boost.active:
            overall, boost_notes = self._boost.apply(
                overall, title=job.title, location=job.location or ""
            )
            notes += boost_notes
        if overall == score.overall_score:
            return score
        score.overall_score = overall
        score.recommendation = _recommend(overall)
        score.interview_probability = round(overall * 0.6, 4)
        score.reasons = list(score.reasons) + notes
        return score

    def _target_preference(self) -> str:
        if self._target_description:
            return self._target_description
        if self._target_levels or self._target_keywords:
            bits = sorted(self._target_levels | self._target_keywords)
            return "roles matching: " + ", ".join(bits)
        return ""

    def _heuristic(self, job: Job, parsed: ParsedJob) -> dict[str, Any]:
        required = _normalize(
            parsed.required_skills + parsed.programming_languages + parsed.frameworks
        )
        preferred = _normalize(parsed.preferred_skills + parsed.keywords)

        technical = _coverage(required, self._vocab, self._blob)
        if preferred:
            technical = 0.8 * technical + 0.2 * _coverage(preferred, self._vocab, self._blob)

        # Experience: reward meeting or slightly missing the requirement.
        if parsed.years_experience is None or self._years is None:
            experience = 0.7
        elif self._years >= parsed.years_experience:
            experience = 1.0
        else:
            gap = parsed.years_experience - self._years
            experience = max(0.0, 1.0 - 0.2 * gap)

        # Education: meet-or-exceed the highest required degree.
        required_degree = max(
            (_DEGREE_RANK.get(d.lower(), 0) for d in parsed.degree_requirements), default=0
        )
        if required_degree == 0:
            education = 0.9
        elif self._degree >= required_degree:
            education = 1.0
        else:
            education = max(0.0, 1.0 - 0.35 * (required_degree - self._degree))

        research = (
            1.0 if not parsed.research_requirements else (0.85 if self._has_research else 0.3)
        )

        interest = _token_overlap(
            f"{job.title} {' '.join(parsed.keywords)}",
            " ".join(sorted(self._vocab)),
        )
        interest = min(1.0, 0.4 + interest)  # a floor of baseline interest

        # Emit the five dimensions on the same 1-100 wire scale the LLM uses, so a
        # single path (_coerce -> _weighted_overall) normalizes and applies
        # _WEIGHTS for every provider. The overall score, recommendation, and
        # interview probability are derived there, not here — role targeting and
        # the other ranking adjustments then run in _finalize.
        reasons = _reasons(required, self._vocab, self._blob, parsed, self._years)
        return {
            "technical_match": round(technical * _SCALE, 2),
            "experience_match": round(experience * _SCALE, 2),
            "education_match": round(education * _SCALE, 2),
            "research_match": round(research * _SCALE, 2),
            "interest_match": round(interest * _SCALE, 2),
            "reasons": reasons,
        }


def domain_text(job: Job, parsed: ParsedJob | None) -> str:
    """Concatenated text used for the domain-relevance check (title + description
    + parsed skills). Shared by the classifier and the offline re-score."""
    parts = [job.title, job.description or ""]
    if parsed is not None:
        parts += parsed.required_skills + parsed.preferred_skills
        parts += parsed.keywords + parsed.frameworks + parsed.programming_languages
    return " ".join(p for p in parts if p)


def _recommend(overall: float) -> Recommendation:
    if overall >= 0.8:
        return Recommendation.STRONG_APPLY
    if overall >= 0.65:
        return Recommendation.APPLY
    if overall >= 0.45:
        return Recommendation.MAYBE
    return Recommendation.SKIP


# -- candidate signal extraction -------------------------------------------
def _candidate_vocabulary(kb: KnowledgeBase) -> set[str]:
    vocab: set[str] = set()
    for item in kb.items:
        vocab.update(_normalize([item.title]))
        vocab.update(item.tags)
        vocab.update(_normalize(re.findall(r"[a-zA-Z+#]+", item.text)))
    return {v for v in vocab if len(v) > 1}


def _candidate_blob(kb: KnowledgeBase) -> str:
    """Lowercased text of the whole background, for phrase-level skill matching."""
    parts = [kb.profile.summary, kb.profile.headline]
    for item in kb.items:
        parts.append(item.title)
        parts.append(item.text)
        parts.extend(item.tags)
    return " \n ".join(p for p in parts if p).lower()


def _candidate_years(kb: KnowledgeBase) -> int | None:
    text = f"{kb.profile.summary} {kb.profile.headline}".lower()
    match = re.search(r"(\d+)\s*\+?\s*years", text)
    return int(match.group(1)) if match else None


def _candidate_degree_rank(kb: KnowledgeBase) -> int:
    text = " ".join(i.text.lower() for i in kb.by_category("education"))
    rank = 0
    if re.search(r"ph\.?d|doctorate", text):
        rank = max(rank, 3)
    if re.search(r"master|m\.?s\.?|msc", text):
        rank = max(rank, 2)
    if re.search(r"bachelor|b\.?s\.?|bsc", text):
        rank = max(rank, 1)
    return rank


# -- generic text helpers ---------------------------------------------------
def _normalize(terms: list[str]) -> set[str]:
    return {t.strip().lower() for t in terms if t and t.strip()}


def _skill_matches(term: str, vocab: set[str], blob: str) -> bool:
    """A required skill counts only if it appears as a whole word/phrase in the
    candidate's background (or is an exact vocab token). Loose substring matching
    is deliberately avoided — e.g. the candidate token "data" must NOT satisfy a
    "data science" requirement."""
    if term in vocab:
        return True
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", blob))


def _coverage(required: set[str], vocab: set[str], blob: str) -> float:
    if not required:
        return 0.6  # no explicit requirements -> mildly positive, not a free pass
    hits = sum(1 for r in required if _skill_matches(r, vocab, blob))
    return hits / len(required)


def _token_overlap(a: str, b: str) -> float:
    ta = set(re.findall(r"[a-z0-9]+", a.lower()))
    tb = set(re.findall(r"[a-z0-9]+", b.lower()))
    if not ta:
        return 0.0
    return len(ta & tb) / len(ta)


def _reasons(
    required: set[str], vocab: set[str], blob: str, parsed: ParsedJob, years: int | None
) -> list[str]:
    matched = sorted(r for r in required if _skill_matches(r, vocab, blob))
    missing = sorted(r for r in required if not _skill_matches(r, vocab, blob))
    reasons: list[str] = []
    if matched:
        reasons.append(f"Strong overlap on: {', '.join(matched[:6])}")
    if missing:
        reasons.append(f"Gaps to note: {', '.join(missing[:5])}")
    if parsed.years_experience and years is not None:
        reasons.append(f"Requires {parsed.years_experience}y; candidate ~{years}y")
    if parsed.research_requirements:
        reasons.append("Role expects research experience")
    return reasons or ["Assessed on available signals"]


def _read_subscores(data: dict[str, Any]) -> dict[str, float]:
    """Read the five dimension ratings and normalize to [0, 1].

    The LLM (and the heuristic) return each dimension on a 1-100 scale; dividing by
    ``_SCALE`` and clamping yields the internal [0, 1] representation. Missing or
    non-numeric values degrade to 0.0 rather than raising, so a partial model
    response still produces a usable score.
    """
    out: dict[str, float] = {}
    for name in _SUBSCORES:
        try:
            val = float(data.get(f"{name}_match", 0.0)) / _SCALE
        except (TypeError, ValueError):
            val = 0.0
        out[name] = max(0.0, min(1.0, val))
    return out


def _weighted_overall(sub: dict[str, float]) -> float:
    """Combine the five [0, 1] dimension scores with ``_WEIGHTS``.

    This is the ONE place the overall fit score is computed, for every provider.
    The LLM supplies only the dimension ratings, never the overall, so the user's
    preference weights are always the weights applied.
    """
    return round(sum(_WEIGHTS[name] * sub[name] for name in _WEIGHTS), 4)


def _coerce(
    data: dict[str, Any], clf: JobClassifier, job: Job, parsed: ParsedJob
) -> ClassifierScore:
    """Build a ClassifierScore from raw classifier output (LLM or heuristic).

    Applies our own weighting to the model's 1-100 dimension ratings so the overall
    score is deterministic and provider-independent. Output missing all five
    dimensions falls back to the deterministic heuristic.
    """
    if not isinstance(data, dict) or not any(f"{n}_match" in data for n in _SUBSCORES):
        logger.warning("Classifier output missing dimension ratings; using heuristic")
        data = clf._heuristic(job, parsed)
    sub = _read_subscores(data)
    overall = _weighted_overall(sub)
    reasons = data.get("reasons")
    if not isinstance(reasons, list) or not reasons:
        reasons = ["Assessed on available signals"]
    return ClassifierScore(
        technical_match=sub["technical"],
        experience_match=sub["experience"],
        education_match=sub["education"],
        research_match=sub["research"],
        interest_match=sub["interest"],
        overall_score=overall,
        interview_probability=round(overall * 0.6, 4),
        recommendation=_recommend(overall),
        reasons=[str(r) for r in reasons][:6],
    )
