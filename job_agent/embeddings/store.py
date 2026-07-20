"""Vector stores providing nearest-neighbor retrieval.

Two backends implement the same :class:`VectorStore` interface:

* :class:`SQLiteVectorStore` — persists vectors in the ``embeddings`` table (via
  the repository) and searches with NumPy. The default; no extra dependencies.
* :class:`FaissVectorStore` — an in-memory FAISS index for larger corpora,
  enabled by installing ``faiss-cpu`` and setting ``embedding.backend=faiss``.

Both are populated from the same source of truth, so switching is transparent.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from job_agent.config.logging import get_logger
from job_agent.database.repository import Repository

logger = get_logger(__name__)


@dataclass
class VectorHit:
    owner_id: str
    score: float
    text: str
    meta: dict


class VectorStore(abc.ABC):
    @abc.abstractmethod
    def add(
        self, owner_type: str, owner_id: str, vector: list[float], text: str, meta: dict
    ) -> None: ...

    @abc.abstractmethod
    def search(self, owner_type: str, query: list[float], top_k: int) -> list[VectorHit]: ...


class SQLiteVectorStore(VectorStore):
    """Persists to SQLite and searches with cosine similarity in NumPy."""

    def __init__(self, repository: Repository, model: str, dimension: int) -> None:
        self.repo = repository
        self.model = model
        self.dimension = dimension

    def add(
        self, owner_type: str, owner_id: str, vector: list[float], text: str, meta: dict
    ) -> None:
        self.repo.upsert_embedding(
            owner_type=owner_type,
            owner_id=owner_id,
            model=self.model,
            dimension=self.dimension,
            vector=vector,
            text=text,
            meta=meta,
        )

    def search(self, owner_type: str, query: list[float], top_k: int) -> list[VectorHit]:
        rows = self.repo.list_embeddings(owner_type)
        if not rows:
            return []
        matrix = np.array([r.vector for r in rows], dtype=np.float32)
        q = np.array(query, dtype=np.float32)
        scores = _cosine(matrix, q)
        order = np.argsort(-scores)[:top_k]
        return [
            VectorHit(
                owner_id=rows[i].owner_id,
                score=float(scores[i]),
                text=rows[i].text,
                meta=rows[i].meta or {},
            )
            for i in order
        ]


class FaissVectorStore(VectorStore):
    """In-memory FAISS index, persisted to disk. Requires ``faiss-cpu``."""

    def __init__(self, path: Path | str, dimension: int) -> None:
        import faiss  # lazy import

        self._faiss = faiss
        self.path = Path(path)
        self.dimension = dimension
        self._index = faiss.IndexFlatIP(dimension)
        self._ids: list[str] = []
        self._texts: list[str] = []
        self._meta: list[dict] = []

    def add(
        self, owner_type: str, owner_id: str, vector: list[float], text: str, meta: dict
    ) -> None:
        vec = np.array([vector], dtype=np.float32)
        self._index.add(vec)
        self._ids.append(owner_id)
        self._texts.append(text)
        self._meta.append(meta)

    def search(self, owner_type: str, query: list[float], top_k: int) -> list[VectorHit]:
        if self._index.ntotal == 0:
            return []
        q = np.array([query], dtype=np.float32)
        scores, idx = self._index.search(q, min(top_k, self._index.ntotal))
        hits = []
        for score, i in zip(scores[0], idx[0], strict=False):
            if i < 0:
                continue
            hits.append(
                VectorHit(
                    owner_id=self._ids[i],
                    score=float(score),
                    text=self._texts[i],
                    meta=self._meta[i],
                )
            )
        return hits


def _cosine(matrix: np.ndarray, query: np.ndarray) -> np.ndarray:
    q_norm = np.linalg.norm(query) or 1.0
    m_norm = np.linalg.norm(matrix, axis=1)
    m_norm[m_norm == 0] = 1.0
    return (matrix @ query) / (m_norm * q_norm)


def build_vector_store(
    backend: str,
    repository: Repository,
    model: str,
    dimension: int,
    faiss_path: Path | None = None,
) -> VectorStore:
    if backend == "faiss":
        try:
            return FaissVectorStore(faiss_path or Path("./data/faiss"), dimension)
        except Exception as exc:
            logger.warning("FAISS unavailable (%s); using SQLite vector store", exc)
    return SQLiteVectorStore(repository, model=model, dimension=dimension)
