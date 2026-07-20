"""Repository: the only sanctioned way to read and mutate the database.

Design principle #6/#7: components never touch each other's files or tables
directly. They call repository methods, which (a) enforce invariants like
deduplication and version bumping and (b) write an audit ``LogRecord`` for every
modification. This keeps the SQLite database the single source of truth and
makes every change traceable.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from job_agent.config.logging import get_logger
from job_agent.database.models import (
    Application,
    ClassifierScoreRecord,
    Company,
    CoverLetterVersion,
    Document,
    Embedding,
    JobRecord,
    JobSource,
    LogRecord,
    ParsedJobRecord,
    ResumeVersion,
)
from job_agent.models.domain import (
    ClassifierScore,
    GeneratedDocument,
    Job,
    JobState,
    ParsedJob,
)

logger = get_logger(__name__)


class Repository:
    """Thin, well-typed data-access layer around a SQLAlchemy session."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # -- audit log ----------------------------------------------------------
    def log(
        self,
        component: str,
        action: str,
        message: str = "",
        *,
        job_id: str | None = None,
        level: str = "INFO",
        context: dict[str, Any] | None = None,
    ) -> None:
        record = LogRecord(
            component=component,
            action=action,
            message=message,
            job_id=job_id,
            level=level,
            context=_jsonable(context or {}),
        )
        self.session.add(record)
        logger.log(
            getattr(__import__("logging"), level, 20), "[%s] %s %s", component, action, message
        )

    # -- companies ----------------------------------------------------------
    def upsert_company(self, name: str, **fields: Any) -> Company:
        company = self.session.scalar(select(Company).where(Company.name == name))
        if company is None:
            company = Company(name=name, **fields)
            self.session.add(company)
            self.session.flush()
            self.log("repository", "company_created", name, context={"company": name})
        else:
            for key, value in fields.items():
                if value is not None:
                    setattr(company, key, value)
        return company

    # -- job sources --------------------------------------------------------
    def upsert_job_source(self, name: str, slug: str | None = None, **fields: Any) -> JobSource:
        stmt = select(JobSource).where(JobSource.name == name, JobSource.slug == slug)
        source = self.session.scalar(stmt)
        if source is None:
            source = JobSource(name=name, slug=slug, **fields)
            self.session.add(source)
            self.session.flush()
        return source

    # -- jobs ---------------------------------------------------------------
    def find_job_by_dedup_key(self, key: str) -> JobRecord | None:
        return self.session.scalar(select(JobRecord).where(JobRecord.dedup_key == key))

    def add_job(self, job: Job) -> tuple[JobRecord, bool]:
        """Insert a job unless an identical one already exists.

        Returns ``(record, created)`` where ``created`` is False for duplicates.
        """
        key = job.dedup_key()
        existing = self.find_job_by_dedup_key(key)
        if existing is not None:
            return existing, False

        company = self.upsert_company(job.company)
        record = JobRecord(
            id=job.id,
            title=job.title,
            company_name=job.company,
            company_id=company.id,
            description=job.description,
            location=job.location,
            salary=job.salary,
            employment_type=_enum_value(job.employment_type),
            experience_level=_enum_value(job.experience_level),
            remote=_enum_value(job.remote),
            visa_sponsorship=job.visa_sponsorship,
            url=job.url,
            date_posted=job.date_posted,
            source=job.source,
            external_id=job.external_id,
            dedup_key=key,
            raw=job.raw,
            state=JobState.DISCOVERED.value,
        )
        self.session.add(record)
        self.session.flush()
        self.log(
            "repository",
            "job_added",
            job.title,
            job_id=record.id,
            context={"company": job.company, "source": job.source},
        )
        return record, True

    def get_job(self, job_id: str) -> JobRecord | None:
        return self.session.get(JobRecord, job_id)

    def list_jobs(
        self,
        *,
        state: JobState | None = None,
        states: Sequence[JobState] | None = None,
        limit: int | None = None,
    ) -> list[JobRecord]:
        stmt = select(JobRecord).order_by(JobRecord.created_at.desc())
        if state is not None:
            stmt = stmt.where(JobRecord.state == state.value)
        if states is not None:
            stmt = stmt.where(JobRecord.state.in_([s.value for s in states]))
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.session.scalars(stmt))

    def set_state(self, job: JobRecord, new_state: JobState, *, error: str | None = None) -> None:
        old = job.state
        job.state = new_state.value
        job.error = error
        self.session.add(job)
        self.log(
            "repository",
            "state_change",
            f"{old} -> {new_state.value}",
            job_id=job.id,
            level="ERROR" if error else "INFO",
            context={"from": old, "to": new_state.value, "error": error},
        )

    # -- parsed jobs --------------------------------------------------------
    def save_parsed(
        self, job_id: str, parsed: ParsedJob, prompt_version: str | None = None
    ) -> ParsedJobRecord:
        existing = self.session.scalar(
            select(ParsedJobRecord).where(ParsedJobRecord.job_id == job_id)
        )
        if existing is None:
            existing = ParsedJobRecord(job_id=job_id)
            self.session.add(existing)
        existing.data = parsed.model_dump()
        existing.prompt_version = prompt_version
        self.session.flush()
        self.log("repository", "parsed_saved", job_id=job_id)
        return existing

    def get_parsed(self, job_id: str) -> ParsedJob | None:
        rec = self.session.scalar(select(ParsedJobRecord).where(ParsedJobRecord.job_id == job_id))
        return ParsedJob.model_validate(rec.data) if rec else None

    # -- classifier ---------------------------------------------------------
    def save_classifier(
        self, job_id: str, score: ClassifierScore, prompt_version: str | None = None
    ) -> ClassifierScoreRecord:
        existing = self.session.scalar(
            select(ClassifierScoreRecord).where(ClassifierScoreRecord.job_id == job_id)
        )
        if existing is None:
            existing = ClassifierScoreRecord(job_id=job_id)
            self.session.add(existing)
        existing.technical_match = score.technical_match
        existing.experience_match = score.experience_match
        existing.education_match = score.education_match
        existing.research_match = score.research_match
        existing.interest_match = score.interest_match
        existing.interview_probability = score.interview_probability
        existing.overall_score = score.overall_score
        existing.recommendation = _enum_value(score.recommendation)
        existing.reasons = score.reasons
        existing.prompt_version = prompt_version
        self.session.flush()
        self.log(
            "repository", "classifier_saved", f"score={score.overall_score:.2f}", job_id=job_id
        )
        return existing

    def get_classifier(self, job_id: str) -> ClassifierScore | None:
        rec = self.session.scalar(
            select(ClassifierScoreRecord).where(ClassifierScoreRecord.job_id == job_id)
        )
        if rec is None:
            return None
        return ClassifierScore(
            technical_match=rec.technical_match,
            experience_match=rec.experience_match,
            education_match=rec.education_match,
            research_match=rec.research_match,
            interest_match=rec.interest_match,
            interview_probability=rec.interview_probability,
            overall_score=rec.overall_score,
            recommendation=rec.recommendation,  # type: ignore[arg-type]
            reasons=list(rec.reasons or []),
        )

    # -- document versions --------------------------------------------------
    def _next_version(self, model: type, job_id: str) -> int:
        current = self.session.scalar(
            select(func.max(model.version)).where(model.job_id == job_id)  # type: ignore[attr-defined]
        )
        return int(current or 0) + 1

    def add_resume_version(self, doc: GeneratedDocument) -> ResumeVersion:
        version = self._next_version(ResumeVersion, doc.job_id)
        rec = ResumeVersion(
            id=doc.id,
            job_id=doc.job_id,
            version=version,
            markdown=doc.markdown,
            md_path=doc.paths.get("md"),
            docx_path=doc.paths.get("docx"),
            pdf_path=doc.paths.get("pdf"),
            prompt_version=doc.prompt_version,
        )
        self.session.add(rec)
        self.session.flush()
        self.log("repository", "resume_version_added", f"v{version}", job_id=doc.job_id)
        return rec

    def add_cover_letter_version(
        self, doc: GeneratedDocument, template_name: str | None = None
    ) -> CoverLetterVersion:
        version = self._next_version(CoverLetterVersion, doc.job_id)
        rec = CoverLetterVersion(
            id=doc.id,
            job_id=doc.job_id,
            version=version,
            markdown=doc.markdown,
            md_path=doc.paths.get("md"),
            docx_path=doc.paths.get("docx"),
            pdf_path=doc.paths.get("pdf"),
            prompt_version=doc.prompt_version,
            template_name=template_name,
        )
        self.session.add(rec)
        self.session.flush()
        self.log("repository", "cover_letter_version_added", f"v{version}", job_id=doc.job_id)
        return rec

    def latest_resume(self, job_id: str) -> ResumeVersion | None:
        return self.session.scalar(
            select(ResumeVersion)
            .where(ResumeVersion.job_id == job_id)
            .order_by(ResumeVersion.version.desc())
        )

    def latest_cover_letter(self, job_id: str) -> CoverLetterVersion | None:
        return self.session.scalar(
            select(CoverLetterVersion)
            .where(CoverLetterVersion.job_id == job_id)
            .order_by(CoverLetterVersion.version.desc())
        )

    # -- applications -------------------------------------------------------
    def upsert_application(self, job_id: str, **fields: Any) -> Application:
        app = self.session.scalar(select(Application).where(Application.job_id == job_id))
        if app is None:
            app = Application(job_id=job_id, **fields)
            self.session.add(app)
        else:
            for key, value in fields.items():
                if value is not None:
                    setattr(app, key, value)
        self.session.flush()
        self.log("repository", "application_upserted", job_id=job_id, context=fields)
        return app

    def list_applications(self, status: str | None = None) -> list[Application]:
        stmt = select(Application).order_by(Application.updated_at.desc())
        if status:
            stmt = stmt.where(Application.status == status)
        return list(self.session.scalars(stmt))

    def applications_submitted_today(self) -> int:
        start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = (
            select(func.count()).select_from(Application).where(Application.submitted_at >= start)
        )
        return int(self.session.scalar(stmt) or 0)

    # -- documents registry -------------------------------------------------
    def add_document(
        self,
        *,
        job_id: str | None,
        kind: str,
        fmt: str,
        path: str,
        version: int = 1,
        meta: dict[str, Any] | None = None,
    ) -> Document:
        doc = Document(
            job_id=job_id, kind=kind, fmt=fmt, path=path, version=version, meta=meta or {}
        )
        self.session.add(doc)
        self.session.flush()
        return doc

    # -- embeddings ---------------------------------------------------------
    def upsert_embedding(
        self,
        *,
        owner_type: str,
        owner_id: str,
        model: str,
        dimension: int,
        vector: list[float],
        text: str = "",
        meta: dict[str, Any] | None = None,
    ) -> Embedding:
        stmt = select(Embedding).where(
            Embedding.owner_type == owner_type, Embedding.owner_id == owner_id
        )
        rec = self.session.scalar(stmt)
        if rec is None:
            rec = Embedding(owner_type=owner_type, owner_id=owner_id)
            self.session.add(rec)
        rec.model = model
        rec.dimension = dimension
        rec.vector = vector
        rec.text = text
        rec.meta = meta or {}
        self.session.flush()
        return rec

    def list_embeddings(self, owner_type: str) -> list[Embedding]:
        return list(
            self.session.scalars(select(Embedding).where(Embedding.owner_type == owner_type))
        )

    def get_embedding(self, owner_type: str, owner_id: str) -> Embedding | None:
        return self.session.scalar(
            select(Embedding).where(
                Embedding.owner_type == owner_type, Embedding.owner_id == owner_id
            )
        )

    # -- aggregate counts (used by analytics) -------------------------------
    def count_jobs_by_state(self) -> dict[str, int]:
        rows = self.session.execute(
            select(JobRecord.state, func.count()).group_by(JobRecord.state)
        ).all()
        return {state: int(count) for state, count in rows}


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _jsonable(value: Any) -> Any:
    """Recursively convert a value into something JSON-serializable for logs."""
    from datetime import date, datetime
    from enum import Enum

    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
