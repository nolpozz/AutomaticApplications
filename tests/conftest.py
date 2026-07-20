"""Shared pytest fixtures.

Everything runs against a temporary SQLite database and the mock LLM/embedding
providers, so tests are hermetic, fast, and reproducible.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from job_agent.config.settings import (
    EmbeddingSettings,
    LLMSettings,
    PipelineSettings,
    Settings,
    StorageSettings,
)
from job_agent.database.base import Database
from job_agent.database.repository import Repository
from job_agent.knowledge.loader import load_knowledge_base
from job_agent.llm.factory import build_llm
from job_agent.llm.prompts import get_prompt_registry
from job_agent.models.domain import Job

REPO_ROOT = Path(__file__).resolve().parents[1]
# A fixed, committed persona for tests — independent of the private `user_data/`
# (gitignored) and of the shipped `user_data.example/`, so tests are hermetic and
# pass on a fresh clone.
TEST_USER_DATA = REPO_ROOT / "tests" / "data" / "user_data"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    data = tmp_path / "data"
    return Settings(
        llm=LLMSettings(provider="mock", model="mock-model"),
        embedding=EmbeddingSettings(provider="mock", dimension=128, backend="sqlite"),
        storage=StorageSettings(
            sqlite_path=data / "job_agent.db",
            faiss_path=data / "faiss",
            excel_path=data / "job_agent.xlsx",
            checkpoint_path=data / "checkpoints.sqlite",
            documents_path=data / "documents",
            user_data_path=TEST_USER_DATA,
            templates_path=REPO_ROOT / "templates",
            prompts_path=REPO_ROOT / "job_agent" / "llm" / "prompts",
        ),
        pipeline=PipelineSettings(
            enabled_boards=["greenhouse", "lever"],
            auto_sync_excel=False,
            max_jobs=25,
        ),
    )


@pytest.fixture
def database() -> Database:
    db = Database(":memory:")
    db.create_all()
    return db


@pytest.fixture
def repo(database: Database) -> Iterator[Repository]:
    session = database.session()
    try:
        yield Repository(session)
        session.commit()
    finally:
        session.close()


@pytest.fixture
def knowledge():  # type: ignore[no-untyped-def]
    return load_knowledge_base(TEST_USER_DATA, use_cache=False)


@pytest.fixture
def llm(settings: Settings):  # type: ignore[no-untyped-def]
    return build_llm(settings)


@pytest.fixture
def prompts():  # type: ignore[no-untyped-def]
    return get_prompt_registry(REPO_ROOT / "job_agent" / "llm" / "prompts")


@pytest.fixture
def sample_job() -> Job:
    return Job(
        title="Machine Learning Engineer, NLP",
        company="Test Corp",
        source="greenhouse",
        url="https://example.com/jobs/1",
        description=(
            "We need 3+ years building NLP and LLM systems in Python and PyTorch. "
            "RAG and retrieval a plus. BS in Computer Science required. Research a bonus.\n"
            "- Train and evaluate models\n- Build retrieval pipelines"
        ),
    )
