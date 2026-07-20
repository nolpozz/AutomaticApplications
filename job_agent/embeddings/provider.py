"""Embedding providers.

The mock provider produces a deterministic hashed bag-of-words vector: shared
vocabulary between two texts yields real cosine similarity, so retrieval behaves
sensibly with zero downloads. Installing ``sentence-transformers`` swaps in real
semantic embeddings via config alone.
"""

from __future__ import annotations

import abc
import hashlib
import math
import re

from job_agent.config.logging import get_logger

logger = get_logger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9+#]+")


class EmbeddingProvider(abc.ABC):
    model: str
    dimension: int

    @abc.abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class MockEmbedding(EmbeddingProvider):
    """Deterministic hashed bag-of-words embedding with L2 normalization."""

    def __init__(self, model: str = "mock-hash", dimension: int = 384) -> None:
        self.model = model
        self.dimension = dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_text(t) for t in texts]

    def _embed_text(self, text: str) -> list[float]:
        vec = [0.0] * self.dimension
        tokens = _TOKEN_RE.findall(text.lower())
        for token in tokens:
            digest = hashlib.md5(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


class SentenceTransformerEmbedding(EmbeddingProvider):
    """Real semantic embeddings via sentence-transformers (lazy loaded)."""

    def __init__(
        self, model: str = "sentence-transformers/all-MiniLM-L6-v2", dimension: int = 384
    ) -> None:
        self.model = model
        self.dimension = dimension
        self._st = None

    def _load(self):  # type: ignore[no-untyped-def]
        if self._st is None:
            from sentence_transformers import SentenceTransformer

            self._st = SentenceTransformer(self.model)
            self.dimension = self._st.get_sentence_embedding_dimension()
        return self._st

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        vectors = model.encode(texts, normalize_embeddings=True)
        return [list(map(float, v)) for v in vectors]


def build_embedding_provider(provider: str, model: str, dimension: int) -> EmbeddingProvider:
    if provider == "sentence-transformers":
        return SentenceTransformerEmbedding(model=model, dimension=dimension)
    if provider != "mock":
        logger.warning("Unknown embedding provider %r; using mock", provider)
    return MockEmbedding(model="mock-hash", dimension=dimension)
