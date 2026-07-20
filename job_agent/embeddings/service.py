"""High-level embedding service tying a provider to a vector store."""

from __future__ import annotations

from job_agent.config.logging import get_logger
from job_agent.config.settings import Settings
from job_agent.database.repository import Repository
from job_agent.embeddings.provider import EmbeddingProvider, build_embedding_provider
from job_agent.embeddings.store import VectorHit, VectorStore, build_vector_store
from job_agent.knowledge.loader import KnowledgeBase
from job_agent.models.domain import Job

logger = get_logger(__name__)


class EmbeddingService:
    def __init__(self, provider: EmbeddingProvider, store: VectorStore) -> None:
        self.provider = provider
        self.store = store

    @classmethod
    def from_settings(cls, settings: Settings, repository: Repository) -> EmbeddingService:
        provider = build_embedding_provider(
            settings.embedding.provider, settings.embedding.model, settings.embedding.dimension
        )
        store = build_vector_store(
            settings.embedding.backend,
            repository,
            provider.model,
            provider.dimension,
            faiss_path=settings.storage.faiss_path,
        )
        return cls(provider, store)

    # -- indexing -----------------------------------------------------------
    def index_knowledge(self, kb: KnowledgeBase) -> int:
        texts = [item.embedding_text() for item in kb.items]
        if not texts:
            return 0
        vectors = self.provider.embed(texts)
        for item, vector in zip(kb.items, vectors, strict=False):
            self.store.add(
                "knowledge",
                item.id,
                vector,
                item.embedding_text(),
                {"category": item.category, "title": item.title},
            )
        logger.info("Indexed %d knowledge embeddings", len(texts))
        return len(texts)

    def index_job(self, job: Job) -> list[float]:
        vector = self.provider.embed_one(_job_text(job))
        self.store.add("job", job.id, vector, _job_text(job)[:500], {"title": job.title})
        return vector

    def embed_text(self, text: str) -> list[float]:
        return self.provider.embed_one(text)

    # -- querying -----------------------------------------------------------
    def query_knowledge(self, text: str, top_k: int = 8) -> list[VectorHit]:
        return self.store.search("knowledge", self.provider.embed_one(text), top_k)

    def query_jobs(self, text: str, top_k: int = 5) -> list[VectorHit]:
        return self.store.search("job", self.provider.embed_one(text), top_k)


def _job_text(job: Job) -> str:
    return f"{job.title}\n{job.company}\n{job.description}"
