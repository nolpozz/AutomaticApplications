"""Duplicate detection across URL, natural key, title/company, and semantics.

Layers, cheapest first:

1. Exact ``dedup_key`` (external id or URL) — handled at insert by the repository.
2. Normalized company + title match.
3. Semantic similarity of the job text (when embeddings are available), guarding
   against reposts with reworded titles.

Also enforces "never apply twice" by checking existing applications for the same
normalized company+title.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from job_agent.config.logging import get_logger
from job_agent.database.models import JobRecord
from job_agent.database.repository import Repository
from job_agent.embeddings.service import EmbeddingService
from job_agent.models.domain import Job

logger = get_logger(__name__)


@dataclass
class DuplicateMatch:
    job_id: str
    reason: str
    score: float = 1.0


class DuplicateDetector:
    def __init__(
        self,
        repository: Repository,
        embeddings: EmbeddingService | None = None,
        *,
        similarity_threshold: float = 0.92,
    ) -> None:
        self.repo = repository
        self.embeddings = embeddings
        self.similarity_threshold = similarity_threshold

    def find_duplicate(self, job: Job) -> DuplicateMatch | None:
        # 1. Exact natural key.
        existing = self.repo.find_job_by_dedup_key(job.dedup_key())
        if existing is not None:
            return DuplicateMatch(existing.id, "exact_key")

        # 2. Normalized company + title.
        norm_company = _norm(job.company)
        norm_title = _norm(job.title)
        for candidate in self.repo.list_jobs():
            if (
                _norm(candidate.company_name) == norm_company
                and _norm(candidate.title) == norm_title
            ):
                return DuplicateMatch(candidate.id, "company_title")

        # 3. Semantic near-duplicate.
        if self.embeddings is not None:
            hits = self.embeddings.query_jobs(
                f"{job.title} {job.company} {job.description}", top_k=1
            )
            if hits and hits[0].score >= self.similarity_threshold:
                return DuplicateMatch(hits[0].owner_id, "semantic", hits[0].score)

        return None

    def already_applied(self, job: Job) -> JobRecord | None:
        """True-ish if we've already prepared/submitted an application here."""
        norm_company = _norm(job.company)
        norm_title = _norm(job.title)
        for app in self.repo.list_applications():
            record = self.repo.get_job(app.job_id)
            if record is None:
                continue
            if _norm(record.company_name) == norm_company and _norm(record.title) == norm_title:
                return record
        return None


def _norm(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"\(.*?\)", "", value)  # drop parentheticals like "(Remote)"
    value = re.sub(r"[^a-z0-9 ]", "", value)
    return re.sub(r"\s+", " ", value).strip()
