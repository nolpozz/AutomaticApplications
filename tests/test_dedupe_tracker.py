"""Duplicate detection and application tracker tests."""

from __future__ import annotations

import pytest

from job_agent.dedupe.detector import DuplicateDetector
from job_agent.models.domain import Job, JobState
from job_agent.tracker.tracker import ApplicationTracker, DailyLimitReached


def _job(title: str, company: str, url: str) -> Job:
    return Job(title=title, company=company, url=url, source="greenhouse")


def test_detects_exact_and_title_duplicates(repo) -> None:  # type: ignore[no-untyped-def]
    repo.add_job(_job("ML Engineer", "Acme", "https://acme/1"))
    detector = DuplicateDetector(repo)
    # Same URL.
    assert detector.find_duplicate(_job("Anything", "X", "https://acme/1")) is not None
    # Same normalized company + title, different URL.
    dup = detector.find_duplicate(_job("ML Engineer (Remote)", "Acme", "https://acme/2"))
    assert dup is not None and dup.reason == "company_title"
    # Genuinely new.
    assert detector.find_duplicate(_job("Data Scientist", "Beta", "https://beta/1")) is None


def test_tracker_full_lifecycle(repo) -> None:  # type: ignore[no-untyped-def]
    rec, _ = repo.add_job(_job("ML Engineer", "Acme", "https://acme/1"))
    tracker = ApplicationTracker(repo, max_per_day=5)
    tracker.approve(rec.id)
    assert repo.get_job(rec.id).state == JobState.APPROVED.value
    tracker.submit(rec.id)
    assert repo.get_job(rec.id).state == JobState.SUBMITTED.value
    tracker.record_outcome(rec.id, "interview")
    assert repo.get_job(rec.id).state == JobState.INTERVIEW.value


def test_tracker_daily_limit(repo) -> None:  # type: ignore[no-untyped-def]
    tracker = ApplicationTracker(repo, max_per_day=1)
    a, _ = repo.add_job(_job("A", "C1", "https://c/1"))
    b, _ = repo.add_job(_job("B", "C2", "https://c/2"))
    tracker.submit(a.id)
    with pytest.raises(DailyLimitReached):
        tracker.submit(b.id)


def test_tracker_rejects_unknown_outcome(repo) -> None:  # type: ignore[no-untyped-def]
    rec, _ = repo.add_job(_job("A", "C1", "https://c/1"))
    with pytest.raises(ValueError):
        ApplicationTracker(repo).record_outcome(rec.id, "banana")
