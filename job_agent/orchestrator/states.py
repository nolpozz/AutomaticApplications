"""The pipeline state machine: states and allowed transitions.

Because each stage only ever picks up jobs in the *right* current state and
advances them, the whole pipeline is resumable for free: re-running continues
from wherever each job got to, and a job that failed a stage simply stays in its
prior state and is retried next run.
"""

from __future__ import annotations

from job_agent.models.domain import JobState

# Allowed forward (and outcome) transitions.
TRANSITIONS: dict[JobState, set[JobState]] = {
    JobState.DISCOVERED: {JobState.PARSED, JobState.ARCHIVED},
    JobState.PARSED: {JobState.EMBEDDED, JobState.ARCHIVED},
    JobState.EMBEDDED: {JobState.CLASSIFIED, JobState.ARCHIVED},
    JobState.CLASSIFIED: {JobState.READY_FOR_RESUME, JobState.REJECTED, JobState.ARCHIVED},
    JobState.REJECTED: {JobState.ARCHIVED},
    JobState.READY_FOR_RESUME: {JobState.RESUME_GENERATED, JobState.ARCHIVED},
    JobState.RESUME_GENERATED: {JobState.COVER_LETTER_GENERATED, JobState.ARCHIVED},
    JobState.COVER_LETTER_GENERATED: {JobState.READY_FOR_REVIEW, JobState.ARCHIVED},
    JobState.READY_FOR_REVIEW: {JobState.APPROVED, JobState.ARCHIVED},
    JobState.APPROVED: {JobState.SUBMITTED, JobState.ARCHIVED},
    JobState.SUBMITTED: {
        JobState.REJECTED_BY_COMPANY,
        JobState.INTERVIEW,
        JobState.OFFER,
        JobState.ARCHIVED,
    },
    JobState.INTERVIEW: {JobState.OFFER, JobState.REJECTED_BY_COMPANY, JobState.ARCHIVED},
    JobState.OFFER: {JobState.ARCHIVED},
    JobState.REJECTED_BY_COMPANY: {JobState.ARCHIVED},
    JobState.ARCHIVED: set(),
}

# The automated portion of the pipeline the orchestrator drives, in order.
AUTOMATED_FLOW = [
    JobState.DISCOVERED,
    JobState.PARSED,
    JobState.EMBEDDED,
    JobState.CLASSIFIED,
    JobState.READY_FOR_RESUME,
    JobState.RESUME_GENERATED,
    JobState.COVER_LETTER_GENERATED,
]


def can_transition(current: JobState, target: JobState) -> bool:
    return target in TRANSITIONS.get(current, set())
