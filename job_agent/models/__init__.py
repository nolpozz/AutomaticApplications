"""Shared domain models — the typed contracts between pipeline stages."""

from job_agent.models.domain import (
    ClassifierScore,
    EmploymentType,
    ExperienceLevel,
    GeneratedDocument,
    Job,
    JobState,
    KnowledgeItem,
    ParsedJob,
    Recommendation,
    RemoteType,
    RetrievedKnowledge,
    ScoredNeighbor,
    new_id,
)

__all__ = [
    "ClassifierScore",
    "EmploymentType",
    "ExperienceLevel",
    "GeneratedDocument",
    "Job",
    "JobState",
    "KnowledgeItem",
    "ParsedJob",
    "Recommendation",
    "RemoteType",
    "RetrievedKnowledge",
    "ScoredNeighbor",
    "new_id",
]
