"""ORM models — the persistent schema and single source of truth.

Tables: companies, job_sources, jobs, parsed_jobs, classifier_scores,
resume_versions, cover_letter_versions, applications, documents, logs,
embeddings. All carry UUID PKs and timestamps (via mixins).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON as SAJSON
from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from job_agent.database.base import Base, TimestampMixin, UUIDMixin
from job_agent.models.domain import JobState


class Company(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)

    jobs: Mapped[list[JobRecord]] = relationship(back_populates="company_ref")


class JobSource(UUIDMixin, TimestampMixin, Base):
    """A configured board/company endpoint that scrapers pull from."""

    __tablename__ = "job_sources"

    name: Mapped[str] = mapped_column(String(128), index=True)  # e.g. "greenhouse"
    slug: Mapped[str | None] = mapped_column(String(255), nullable=True)  # board token
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict[str, Any]] = mapped_column(SAJSON, default=dict)


class JobRecord(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "jobs"

    title: Mapped[str] = mapped_column(String(512), index=True)
    company_name: Mapped[str] = mapped_column(String(255), index=True)
    company_id: Mapped[str | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    salary: Mapped[str | None] = mapped_column(String(255), nullable=True)
    employment_type: Mapped[str] = mapped_column(String(32), default="unknown")
    experience_level: Mapped[str] = mapped_column(String(32), default="unknown")
    remote: Mapped[str] = mapped_column(String(16), default="unknown")
    visa_sponsorship: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    url: Mapped[str] = mapped_column(String(1024))
    date_posted: Mapped[datetime | None] = mapped_column(nullable=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    external_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    dedup_key: Mapped[str] = mapped_column(String(1024), index=True)
    raw: Mapped[dict[str, Any]] = mapped_column(SAJSON, default=dict)

    state: Mapped[str] = mapped_column(String(32), default=JobState.DISCOVERED.value, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    company_ref: Mapped[Company | None] = relationship(back_populates="jobs")
    parsed: Mapped[ParsedJobRecord | None] = relationship(
        back_populates="job", uselist=False, cascade="all, delete-orphan"
    )
    classifier_score: Mapped[ClassifierScoreRecord | None] = relationship(
        back_populates="job", uselist=False, cascade="all, delete-orphan"
    )
    resume_versions: Mapped[list[ResumeVersion]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    cover_letter_versions: Mapped[list[CoverLetterVersion]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    application: Mapped[Application | None] = relationship(
        back_populates="job", uselist=False, cascade="all, delete-orphan"
    )


class ParsedJobRecord(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "parsed_jobs"

    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    data: Mapped[dict[str, Any]] = mapped_column(SAJSON, default=dict)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    job: Mapped[JobRecord] = relationship(back_populates="parsed")


class ClassifierScoreRecord(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "classifier_scores"

    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    technical_match: Mapped[float] = mapped_column(Float, default=0.0)
    experience_match: Mapped[float] = mapped_column(Float, default=0.0)
    education_match: Mapped[float] = mapped_column(Float, default=0.0)
    research_match: Mapped[float] = mapped_column(Float, default=0.0)
    interest_match: Mapped[float] = mapped_column(Float, default=0.0)
    interview_probability: Mapped[float] = mapped_column(Float, default=0.0)
    overall_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    recommendation: Mapped[str] = mapped_column(String(32), default="maybe")
    reasons: Mapped[list[str]] = mapped_column(SAJSON, default=list)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    job: Mapped[JobRecord] = relationship(back_populates="classifier_score")


class _DocumentVersionBase(UUIDMixin, TimestampMixin):
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    markdown: Mapped[str] = mapped_column(Text, default="")
    md_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    docx_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    pdf_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ResumeVersion(_DocumentVersionBase, Base):
    __tablename__ = "resume_versions"

    job: Mapped[JobRecord] = relationship(back_populates="resume_versions")


class CoverLetterVersion(_DocumentVersionBase, Base):
    __tablename__ = "cover_letter_versions"

    template_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    job: Mapped[JobRecord] = relationship(back_populates="cover_letter_versions")


class Application(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "applications"

    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True, unique=True)
    status: Mapped[str] = mapped_column(String(32), default="prepared", index=True)
    stage: Mapped[str] = mapped_column(String(32), default=JobState.READY_FOR_REVIEW.value)
    resume_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    cover_letter_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    job: Mapped[JobRecord] = relationship(back_populates="application")


class Document(UUIDMixin, TimestampMixin, Base):
    """Generic registry of every artifact written to disk."""

    __tablename__ = "documents"

    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(64), index=True)  # resume/cover_letter/raw_job...
    fmt: Mapped[str] = mapped_column(String(16))  # md | docx | pdf | json
    path: Mapped[str] = mapped_column(String(1024))
    version: Mapped[int] = mapped_column(Integer, default=1)
    meta: Mapped[dict[str, Any]] = mapped_column(SAJSON, default=dict)


class Embedding(UUIDMixin, TimestampMixin, Base):
    """Vector storage backend when FAISS is not used (SQLite is the default)."""

    __tablename__ = "embeddings"

    owner_type: Mapped[str] = mapped_column(String(32), index=True)  # job | knowledge
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    model: Mapped[str] = mapped_column(String(128))
    dimension: Mapped[int] = mapped_column(Integer)
    vector: Mapped[list[float]] = mapped_column(SAJSON)
    text: Mapped[str] = mapped_column(Text, default="")
    meta: Mapped[dict[str, Any]] = mapped_column(SAJSON, default=dict)


class LogRecord(UUIDMixin, TimestampMixin, Base):
    """Structured audit log of every database modification and pipeline action."""

    __tablename__ = "logs"

    level: Mapped[str] = mapped_column(String(16), default="INFO", index=True)
    component: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    message: Mapped[str] = mapped_column(Text, default="")
    context: Mapped[dict[str, Any]] = mapped_column(SAJSON, default=dict)
