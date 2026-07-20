"""Analytics computed from the database."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select

from job_agent.database.models import (
    ClassifierScoreRecord,
    JobRecord,
    ParsedJobRecord,
)
from job_agent.database.repository import Repository
from job_agent.models.domain import JobState


@dataclass
class Stats:
    jobs_discovered: int = 0
    jobs_parsed: int = 0
    jobs_classified: int = 0
    jobs_rejected: int = 0
    applications_prepared: int = 0
    applications_submitted: int = 0
    interviews: int = 0
    offers: int = 0
    interview_rate: float = 0.0
    offer_rate: float = 0.0
    avg_classifier_score: float = 0.0
    avg_response_time_days: float = 0.0
    by_state: dict[str, int] = field(default_factory=dict)
    top_matching_companies: list[tuple[str, float]] = field(default_factory=list)
    top_matching_skills: list[tuple[str, int]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "jobs_discovered": self.jobs_discovered,
            "jobs_parsed": self.jobs_parsed,
            "jobs_classified": self.jobs_classified,
            "jobs_rejected": self.jobs_rejected,
            "applications_prepared": self.applications_prepared,
            "applications_submitted": self.applications_submitted,
            "interviews": self.interviews,
            "offers": self.offers,
            "interview_rate": self.interview_rate,
            "offer_rate": self.offer_rate,
            "avg_classifier_score": self.avg_classifier_score,
            "avg_response_time_days": self.avg_response_time_days,
            "by_state": self.by_state,
            "top_matching_companies": self.top_matching_companies,
            "top_matching_skills": self.top_matching_skills,
        }

    def as_rows(self) -> list[tuple[str, Any]]:
        rows: list[tuple[str, Any]] = [
            ("Jobs discovered", self.jobs_discovered),
            ("Jobs parsed", self.jobs_parsed),
            ("Jobs classified", self.jobs_classified),
            ("Jobs rejected", self.jobs_rejected),
            ("Applications prepared", self.applications_prepared),
            ("Applications submitted", self.applications_submitted),
            ("Interviews", self.interviews),
            ("Offers", self.offers),
            ("Interview rate", f"{self.interview_rate:.1%}"),
            ("Offer rate", f"{self.offer_rate:.1%}"),
            ("Avg classifier score", round(self.avg_classifier_score, 3)),
            ("Avg response time (days)", round(self.avg_response_time_days, 1)),
        ]
        for company, score in self.top_matching_companies:
            rows.append((f"Top company: {company}", round(score, 3)))
        for skill, count in self.top_matching_skills:
            rows.append((f"Top skill: {skill}", count))
        return rows


class Analytics:
    def __init__(self, repository: Repository) -> None:
        self.repo = repository
        self.session = repository.session

    def compute(self) -> Stats:
        s = Stats()
        s.by_state = self.repo.count_jobs_by_state()
        s.jobs_discovered = int(
            self.session.scalar(select(func.count()).select_from(JobRecord)) or 0
        )
        s.jobs_parsed = int(
            self.session.scalar(select(func.count()).select_from(ParsedJobRecord)) or 0
        )
        s.jobs_classified = int(
            self.session.scalar(select(func.count()).select_from(ClassifierScoreRecord)) or 0
        )
        s.jobs_rejected = s.by_state.get(JobState.REJECTED.value, 0)

        apps = self.repo.list_applications()
        s.applications_prepared = len(apps)
        submitted = [a for a in apps if a.submitted_at is not None]
        s.applications_submitted = len(submitted)
        s.interviews = s.by_state.get(JobState.INTERVIEW.value, 0)
        s.offers = s.by_state.get(JobState.OFFER.value, 0)
        if s.applications_submitted:
            s.interview_rate = s.interviews / s.applications_submitted
            s.offer_rate = s.offers / s.applications_submitted

        avg = self.session.scalar(select(func.avg(ClassifierScoreRecord.overall_score)))
        s.avg_classifier_score = float(avg or 0.0)

        deltas: list[float] = []
        for a in submitted:
            if a.submitted_at is not None and a.responded_at is not None:
                deltas.append((a.responded_at - a.submitted_at).total_seconds() / 86400)
        s.avg_response_time_days = sum(deltas) / len(deltas) if deltas else 0.0

        s.top_matching_companies = self._top_companies()
        s.top_matching_skills = self._top_skills()
        return s

    def _top_companies(self, limit: int = 5) -> list[tuple[str, float]]:
        rows = self.session.execute(
            select(JobRecord.company_name, func.avg(ClassifierScoreRecord.overall_score))
            .join(ClassifierScoreRecord, ClassifierScoreRecord.job_id == JobRecord.id)
            .group_by(JobRecord.company_name)
            .order_by(func.avg(ClassifierScoreRecord.overall_score).desc())
            .limit(limit)
        ).all()
        return [(name, float(score)) for name, score in rows]

    def _top_skills(self, limit: int = 10) -> list[tuple[str, int]]:
        counter: Counter[str] = Counter()
        for parsed in self.session.scalars(select(ParsedJobRecord)):
            for skill in (parsed.data or {}).get("required_skills", []):
                counter[str(skill).lower()] += 1
        return counter.most_common(limit)
