"""Embedding pipeline: providers, vector stores, and a unifying service."""

from job_agent.embeddings.provider import (
    EmbeddingProvider,
    MockEmbedding,
    SentenceTransformerEmbedding,
    build_embedding_provider,
)
from job_agent.embeddings.service import EmbeddingService
from job_agent.embeddings.store import (
    FaissVectorStore,
    SQLiteVectorStore,
    VectorHit,
    VectorStore,
    build_vector_store,
)

__all__ = [
    "EmbeddingProvider",
    "EmbeddingService",
    "FaissVectorStore",
    "MockEmbedding",
    "SQLiteVectorStore",
    "SentenceTransformerEmbedding",
    "VectorHit",
    "VectorStore",
    "build_embedding_provider",
    "build_vector_store",
]
