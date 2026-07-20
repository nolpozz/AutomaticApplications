"""Domain models shared across every component.

These Pydantic models are the *contracts* between pipeline stages. Components
never touch each other's internals; they exchange these typed objects (and the
database records derived from them). Keeping them here, dependency-free, means a
scraper, the classifier and the dashboard can all agree on what a "Job" is
without importing one another.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    """Generate a fresh UUID4 string primary key."""
    return str(uuid4())


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------
class RemoteType(str, enum.Enum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class EmploymentType(str, enum.Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    UNKNOWN = "unknown"


class ExperienceLevel(str, enum.Enum):
    INTERN = "intern"
    ENTRY = "entry"
    MID = "mid"
    SENIOR = "senior"
    STAFF = "staff"
    UNKNOWN = "unknown"


class Recommendation(str, enum.Enum):
    STRONG_APPLY = "strong_apply"
    APPLY = "apply"
    MAYBE = "maybe"
    SKIP = "skip"


class JobState(str, enum.Enum):
    """Lifecycle states for a job in the pipeline state machine.

    The ordering here also encodes forward progress through the happy path;
    see :mod:`job_agent.orchestrator.states` for allowed transitions.
    """

    DISCOVERED = "DISCOVERED"
    PARSED = "PARSED"
    EMBEDDED = "EMBEDDED"
    CLASSIFIED = "CLASSIFIED"
    REJECTED = "REJECTED"
    READY_FOR_RESUME = "READY_FOR_RESUME"
    RESUME_GENERATED = "RESUME_GENERATED"
    COVER_LETTER_GENERATED = "COVER_LETTER_GENERATED"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    APPROVED = "APPROVED"
    SUBMITTED = "SUBMITTED"
    REJECTED_BY_COMPANY = "REJECTED_BY_COMPANY"
    INTERVIEW = "INTERVIEW"
    OFFER = "OFFER"
    ARCHIVED = "ARCHIVED"


# ---------------------------------------------------------------------------
# Core domain objects
# ---------------------------------------------------------------------------
class Job(BaseModel):
    """A normalized job posting, as emitted by any scraper.

    Every scraper, regardless of source, must produce this shape. Downstream
    stages depend only on these fields, never on source-specific structure.
    """

    model_config = ConfigDict(use_enum_values=False)

    id: str = Field(default_factory=new_id)
    title: str
    company: str
    description: str = ""
    location: str | None = None
    salary: str | None = None
    employment_type: EmploymentType = EmploymentType.UNKNOWN
    experience_level: ExperienceLevel = ExperienceLevel.UNKNOWN
    remote: RemoteType = RemoteType.UNKNOWN
    visa_sponsorship: bool | None = None
    url: str
    date_posted: datetime | None = None
    source: str
    # Stable natural key used for deduplication; derived from url when absent.
    external_id: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
    scraped_at: datetime = Field(default_factory=_utcnow)

    def dedup_key(self) -> str:
        """Best-effort stable identity for a posting."""
        return (self.external_id or self.url or f"{self.company}:{self.title}").strip().lower()


class ParsedJob(BaseModel):
    """Structured requirements extracted from a job description by the LLM."""

    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    years_experience: int | None = None
    programming_languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    degree_requirements: list[str] = Field(default_factory=list)
    research_requirements: list[str] = Field(default_factory=list)
    security_clearance: str | None = None
    visa_sponsorship: bool | None = None
    industry: str | None = None
    keywords: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)


class ClassifierScore(BaseModel):
    """Reproducible fit assessment produced by the classifier."""

    technical_match: float = 0.0
    experience_match: float = 0.0
    education_match: float = 0.0
    research_match: float = 0.0
    interest_match: float = 0.0
    interview_probability: float = 0.0
    overall_score: float = 0.0
    recommendation: Recommendation = Recommendation.MAYBE
    reasons: list[str] = Field(default_factory=list)

    def passes(self, threshold: float) -> bool:
        return self.overall_score >= threshold and self.recommendation != Recommendation.SKIP


class KnowledgeItem(BaseModel):
    """A single unit of the user's background (a bullet, project, course...)."""

    id: str = Field(default_factory=new_id)
    category: str  # experience | project | skill | education | research | course | award ...
    title: str
    text: str
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def embedding_text(self) -> str:
        tag_str = f" ({', '.join(self.tags)})" if self.tags else ""
        return f"{self.title}: {self.text}{tag_str}"


class RetrievedKnowledge(BaseModel):
    """Knowledge items selected as relevant to a specific job, grouped by kind."""

    projects: list[KnowledgeItem] = Field(default_factory=list)
    resume_bullets: list[KnowledgeItem] = Field(default_factory=list)
    skills: list[KnowledgeItem] = Field(default_factory=list)
    experience: list[KnowledgeItem] = Field(default_factory=list)
    research: list[KnowledgeItem] = Field(default_factory=list)
    courses: list[KnowledgeItem] = Field(default_factory=list)

    def all_items(self) -> list[KnowledgeItem]:
        return [
            *self.experience,
            *self.projects,
            *self.research,
            *self.resume_bullets,
            *self.skills,
            *self.courses,
        ]


class GeneratedDocument(BaseModel):
    """Metadata + content for a generated resume or cover letter version."""

    id: str = Field(default_factory=new_id)
    job_id: str
    kind: str  # "resume" | "cover_letter"
    version: int = 1
    markdown: str
    paths: dict[str, str] = Field(default_factory=dict)  # {"md": ..., "docx": ..., "pdf": ...}
    prompt_version: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)


class ScoredNeighbor(BaseModel):
    """A knowledge item plus its similarity to a query, for retrieval output."""

    item: KnowledgeItem
    score: float
