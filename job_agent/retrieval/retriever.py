"""Retrieval: select only the user material relevant to a specific job.

Given a job (and its parsed requirements), we build a query, run nearest-neighbor
search over the indexed knowledge base, and return the top items grouped by kind.
This keeps prompts small and focused — only relevant, real material reaches the
LLM (design requirement for the resume/cover-letter generators).
"""

from __future__ import annotations

from dataclasses import dataclass

from job_agent.config.logging import get_logger
from job_agent.embeddings.service import EmbeddingService
from job_agent.knowledge.loader import KnowledgeBase
from job_agent.models.domain import Job, KnowledgeItem, ParsedJob, RetrievedKnowledge

logger = get_logger(__name__)

# Which knowledge categories flow into which retrieval bucket, and how many.
_BUCKETS = {
    "experience": ("experience", 4),
    "projects": ("project", 3),
    "skills": ("skill", 8),
    "research": ("research", 2),
    "courses": ("course", 4),
    "resume_bullets": ("resume_bullet", 6),
}


@dataclass
class Retriever:
    embeddings: EmbeddingService
    knowledge: KnowledgeBase

    def __post_init__(self) -> None:
        self._by_id: dict[str, KnowledgeItem] = {item.id: item for item in self.knowledge.items}

    def build_query(self, job: Job, parsed: ParsedJob | None) -> str:
        parts = [job.title, job.company]
        if parsed:
            parts += parsed.required_skills + parsed.preferred_skills
            parts += parsed.programming_languages + parsed.frameworks + parsed.keywords
        # Fall back to description snippet when little structure is available.
        if not parsed or not (parsed.required_skills or parsed.keywords):
            parts.append(job.description[:500])
        return " ".join(parts)

    def retrieve(
        self, job: Job, parsed: ParsedJob | None = None, *, pool: int = 40
    ) -> RetrievedKnowledge:
        query = self.build_query(job, parsed)
        hits = self.embeddings.query_knowledge(query, top_k=pool)

        # Preserve ranking; bucket by category with per-bucket caps.
        ranked: list[KnowledgeItem] = []
        for hit in hits:
            item = self._by_id.get(hit.owner_id)
            if item is not None:
                ranked.append(item)

        result = RetrievedKnowledge()
        target = {field: cat for field, (cat, _) in _BUCKETS.items()}
        caps = {field: cap for field, (_, cap) in _BUCKETS.items()}
        for field, category in target.items():
            selected = [i for i in ranked if i.category == category][: caps[field]]
            setattr(result, field, selected)

        logger.info(
            "Retrieved for %s: %d exp, %d proj, %d skills, %d bullets",
            job.title,
            len(result.experience),
            len(result.projects),
            len(result.skills),
            len(result.resume_bullets),
        )
        return result
