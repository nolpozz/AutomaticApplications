"""Application tracker: the human-in-the-loop stage transitions.

The orchestrator drives jobs up to ``READY_FOR_REVIEW``. From there a person
(via CLI/dashboard) approves, submits, and records outcomes. This module owns
those transitions and enforces the daily submission cap.
"""

from __future__ import annotations

from datetime import datetime, timezone

from job_agent.config.logging import get_logger
from job_agent.database.repository import Repository
from job_agent.models.domain import JobState

logger = get_logger(__name__)


class DailyLimitReached(RuntimeError):
    """Raised when the max-applications-per-day cap is hit."""


class ApplicationTracker:
    def __init__(self, repository: Repository, *, max_per_day: int = 20) -> None:
        self.repo = repository
        self.max_per_day = max_per_day

    def approve(self, job_id: str, *, note: str | None = None) -> None:
        job = self._job(job_id)
        self.repo.upsert_application(
            job_id, status="approved", stage=JobState.APPROVED.value, notes=note
        )
        self.repo.set_state(job, JobState.APPROVED)

    def submit(self, job_id: str, *, note: str | None = None) -> None:
        if self.repo.applications_submitted_today() >= self.max_per_day:
            raise DailyLimitReached(f"Daily cap of {self.max_per_day} applications reached")
        job = self._job(job_id)
        self.repo.upsert_application(
            job_id,
            status="submitted",
            stage=JobState.SUBMITTED.value,
            submitted_at=datetime.now(timezone.utc),
            notes=note,
        )
        self.repo.set_state(job, JobState.SUBMITTED)
        logger.info("Submitted application for job %s", job_id)

    def record_outcome(self, job_id: str, outcome: str, *, note: str | None = None) -> None:
        """outcome in {rejected, interview, offer, archived}."""
        mapping = {
            "rejected": JobState.REJECTED_BY_COMPANY,
            "interview": JobState.INTERVIEW,
            "offer": JobState.OFFER,
            "archived": JobState.ARCHIVED,
        }
        state = mapping.get(outcome)
        if state is None:
            raise ValueError(f"Unknown outcome {outcome!r}; expected {sorted(mapping)}")
        job = self._job(job_id)
        self.repo.upsert_application(
            job_id,
            status=outcome,
            stage=state.value,
            responded_at=datetime.now(timezone.utc),
            notes=note,
        )
        self.repo.set_state(job, state)

    def add_note(self, job_id: str, note: str) -> None:
        self.repo.upsert_application(job_id, notes=note)

    def _job(self, job_id: str):  # type: ignore[no-untyped-def]
        job = self.repo.get_job(job_id)
        if job is None:
            raise KeyError(f"No job with id {job_id}")
        return job
