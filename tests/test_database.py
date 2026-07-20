"""Repository / database tests."""

from __future__ import annotations

from job_agent.database.repository import Repository
from job_agent.models.domain import (
    ClassifierScore,
    GeneratedDocument,
    Job,
    JobState,
    ParsedJob,
    Recommendation,
)


def _job(**kw: object) -> Job:
    base = dict(title="ML Engineer", company="Acme", url="https://acme/1", source="greenhouse")
    base.update(kw)
    return Job(**base)  # type: ignore[arg-type]


def test_add_job_dedupes(repo: Repository) -> None:
    _rec, created = repo.add_job(_job())
    assert created is True
    _, created_again = repo.add_job(_job())
    assert created_again is False
    assert len(repo.list_jobs()) == 1


def test_state_change_logged(repo: Repository) -> None:
    rec, _ = repo.add_job(_job())
    repo.set_state(rec, JobState.PARSED)
    assert repo.get_job(rec.id).state == JobState.PARSED.value


def test_document_versions_increment(repo: Repository) -> None:
    rec, _ = repo.add_job(_job())
    for _i in range(3):
        repo.add_resume_version(GeneratedDocument(job_id=rec.id, kind="resume", markdown="x"))
    latest = repo.latest_resume(rec.id)
    assert latest.version == 3


def test_classifier_round_trip(repo: Repository) -> None:
    rec, _ = repo.add_job(_job())
    repo.save_classifier(
        rec.id, ClassifierScore(overall_score=0.7, recommendation=Recommendation.APPLY)
    )
    got = repo.get_classifier(rec.id)
    assert got is not None
    assert got.overall_score == 0.7
    assert got.recommendation == Recommendation.APPLY


def test_parsed_round_trip(repo: Repository) -> None:
    rec, _ = repo.add_job(_job())
    repo.save_parsed(rec.id, ParsedJob(required_skills=["python"], years_experience=3))
    parsed = repo.get_parsed(rec.id)
    assert parsed is not None
    assert parsed.required_skills == ["python"]
    assert parsed.years_experience == 3


def test_embedding_upsert_and_list(repo: Repository) -> None:
    repo.upsert_embedding(
        owner_type="knowledge",
        owner_id="k1",
        model="m",
        dimension=3,
        vector=[0.1, 0.2, 0.3],
        text="hi",
    )
    repo.upsert_embedding(
        owner_type="knowledge",
        owner_id="k1",
        model="m",
        dimension=3,
        vector=[0.4, 0.5, 0.6],
        text="bye",
    )  # update, not insert
    rows = repo.list_embeddings("knowledge")
    assert len(rows) == 1
    assert rows[0].vector == [0.4, 0.5, 0.6]
