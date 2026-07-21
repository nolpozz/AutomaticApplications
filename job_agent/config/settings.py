"""Centralized, layered configuration.

Precedence (highest first):

1. Environment variables (prefixed ``JOB_AGENT_``, nested with ``__``).
2. ``config/config.yaml`` (or the file named by ``JOB_AGENT_CONFIG_FILE``).
3. Built-in defaults defined on the models below.

Every component receives its configuration through :func:`get_settings`; nothing
reads ``os.environ`` directly. This keeps configuration testable (build a
``Settings`` in a test and inject it) and makes the full surface discoverable in
one place.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, TypeAlias

import yaml
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import (
    BaseSettings,
    NoDecode,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

# NoDecode makes pydantic-settings accept comma-separated env values for list
# fields (parsed into a list by the validator below) instead of requiring JSON.
StrList: TypeAlias = Annotated[list[str], NoDecode]


class LLMSettings(BaseSettings):
    provider: str = "mock"  # openai | anthropic | gemini | ollama | vllm | mock
    model: str = "claude-opus-4-8"  # default model (used by document generation)
    # Optional per-stage overrides. Cheap stages (parse/classify) can use a
    # smaller model while the résumé/cover letter use the strong default.
    parse_model: str | None = None
    classify_model: str | None = None
    resume_model: str | None = None
    cover_letter_model: str | None = None
    temperature: float = 0.2
    max_tokens: int = 4096
    max_retries: int = 3
    timeout_seconds: int = 60
    ollama_base_url: str = "http://localhost:11434"
    vllm_base_url: str = "http://localhost:8000/v1"

    def model_for(self, stage: str) -> str:
        """Return the model for a stage, falling back to the default model."""
        return getattr(self, f"{stage}_model", None) or self.model


class EmbeddingSettings(BaseSettings):
    provider: str = "mock"  # sentence-transformers | mock
    model: str = "sentence-transformers/all-MiniLM-L6-v2"
    dimension: int = 384
    backend: str = "sqlite"  # sqlite | faiss


class StorageSettings(BaseSettings):
    sqlite_path: Path = Path("./data/job_agent.db")
    faiss_path: Path = Path("./data/faiss")
    excel_path: Path = Path("./data/job_agent.xlsx")
    checkpoint_path: Path = Path("./data/checkpoints.sqlite")
    documents_path: Path = Path("./data/documents")
    user_data_path: Path = Path("./user_data")
    templates_path: Path = Path("./templates")
    prompts_path: Path = Path("./job_agent/llm/prompts")


# Comprehensive default coverage of ML / AI research + engineering role titles.
# Every search-based board (amazon, netflix, google, ...) searches each of these
# unless a board overrides ``extra.queries``. This is the single place that
# controls "which roles do we look for".
DEFAULT_SEARCH_QUERIES = [
    "machine learning engineer",
    "machine learning intern",
    "ai engineer",
    "ai research",
    "research scientist",
    "research engineer",
    "applied scientist",
    "applied machine learning",
    "deep learning",
    "nlp engineer",
    "large language models",
    "generative ai",
    "computer vision",
    "ml infrastructure",
    "ai research intern",
    "data scientist",
]


class PipelineSettings(BaseSettings):
    max_jobs: int = 50
    classifier_threshold: float = 0.65
    max_applications_per_day: int = 20
    enabled_boards: StrList = Field(default_factory=lambda: ["greenhouse", "lever", "ashby", "yc"])
    auto_sync_excel: bool = True
    dedup_similarity_threshold: float = 0.92

    # After embedding + ranking, only the top-N most relevant roles per company
    # proceed to the expensive LLM stages (parse/classify/generate). The rest are
    # marked DEPRIORITIZED. Set 0 to disable the per-company cap.
    top_per_company: int = 5

    # The role titles searched across all search-based boards.
    search_queries: StrList = Field(default_factory=lambda: list(DEFAULT_SEARCH_QUERIES))

    # Role targeting. When set, the classifier prefers roles matching these
    # experience levels / keywords and penalizes clearly-mismatched roles (e.g.
    # senior full-time roles when you only want internships). Empty = no targeting.
    target_experience_levels: StrList = Field(default_factory=list)  # e.g. ["intern"]
    target_keywords: StrList = Field(default_factory=list)  # e.g. ["intern", "internship"]
    target_description: str = ""  # human phrase shown to the LLM, e.g. "Master's-level internships"

    @field_validator(
        "enabled_boards",
        "search_queries",
        "target_experience_levels",
        "target_keywords",
        mode="before",
    )
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


class Settings(BaseSettings):
    """Root settings object. Access nested groups as ``settings.llm`` etc."""

    model_config = SettingsConfigDict(
        env_prefix="JOB_AGENT_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm: LLMSettings = Field(default_factory=LLMSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    pipeline: PipelineSettings = Field(default_factory=PipelineSettings)

    log_level: str = "INFO"
    log_json: bool = False

    # Provider API keys (read from the conventional un-prefixed env vars too).
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
    anthropic_api_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    google_api_key: SecretStr | None = Field(default=None, alias="GOOGLE_API_KEY")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Insert a YAML source below env/dotenv but above defaults."""
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            _YamlSource(settings_cls),
            file_secret_settings,
        )

    def ensure_directories(self) -> None:
        """Create the directories the app writes to, idempotently."""
        for path in (
            self.storage.sqlite_path.parent,
            self.storage.faiss_path,
            self.storage.excel_path.parent,
            self.storage.documents_path,
            self.storage.checkpoint_path.parent,
        ):
            Path(path).mkdir(parents=True, exist_ok=True)


class _YamlSource(PydanticBaseSettingsSource):
    """Loads settings from a YAML file if present."""

    def get_field_value(
        self, field: Any, field_name: str
    ) -> tuple[Any, str, bool]:  # pragma: no cover
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        config_file = os.environ.get("JOB_AGENT_CONFIG_FILE", "config/config.yaml")
        path = Path(config_file)
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not isinstance(data, dict):
            raise ValueError(f"Config file {path} must contain a mapping at the top level")
        return data


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton (cached)."""
    settings = Settings()
    return settings


def reload_settings() -> Settings:
    """Clear the cache and rebuild settings (used by tests and the CLI)."""
    get_settings.cache_clear()
    return get_settings()
