"""Embedding, vector-store, and retrieval tests."""

from __future__ import annotations

from job_agent.embeddings.provider import MockEmbedding
from job_agent.embeddings.service import EmbeddingService
from job_agent.embeddings.store import SQLiteVectorStore
from job_agent.parser.llm_parser import JobParser
from job_agent.retrieval.retriever import Retriever


def test_mock_embedding_similarity_reflects_overlap() -> None:
    emb = MockEmbedding(dimension=256)
    a = emb.embed_one("python pytorch machine learning nlp")
    b = emb.embed_one("python pytorch deep learning nlp")
    c = emb.embed_one("gardening cooking travel photography")
    import numpy as np

    def cos(x, y):  # type: ignore[no-untyped-def]
        return float(np.dot(x, y))

    assert cos(a, b) > cos(a, c)


def test_vector_store_search(repo) -> None:  # type: ignore[no-untyped-def]
    emb = MockEmbedding(dimension=128)
    store = SQLiteVectorStore(repo, model=emb.model, dimension=emb.dimension)
    for i, text in enumerate(["python ml", "java backend", "nlp rag llm"]):
        store.add("knowledge", f"k{i}", emb.embed_one(text), text, {})
    hits = store.search("knowledge", emb.embed_one("nlp retrieval llm"), top_k=1)
    assert hits and hits[0].owner_id == "k2"


def test_retriever_returns_relevant_buckets(repo, settings, knowledge, llm, prompts, sample_job):  # type: ignore[no-untyped-def]
    service = EmbeddingService.from_settings(settings, repo)
    service.index_knowledge(knowledge)
    parsed, _ = JobParser(llm, prompts).parse(sample_job)
    retrieved = Retriever(service, knowledge).retrieve(sample_job, parsed)
    assert retrieved.experience
    assert retrieved.skills
    # Only real items are ever returned.
    ids = {i.id for i in knowledge.items}
    assert all(i.id in ids for i in retrieved.all_items())
