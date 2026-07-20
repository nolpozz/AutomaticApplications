"""LLM-based job-description parser with a deterministic heuristic fallback.

The heuristic (``_heuristic_parse``) doubles as the mock-provider behavior and as
the safety net when a real model returns unparseable output. It uses small
lexicons and regexes — good enough to keep the pipeline meaningful offline.
"""

from __future__ import annotations

import re
from typing import Any

from job_agent.config.logging import get_logger
from job_agent.llm.base import LLMProvider
from job_agent.llm.prompts import PromptRegistry
from job_agent.models.domain import Job, ParsedJob

logger = get_logger(__name__)

_LANGUAGES = [
    "python",
    "java",
    "javascript",
    "typescript",
    "c++",
    "c#",
    "go",
    "golang",
    "rust",
    "scala",
    "ruby",
    "swift",
    "kotlin",
    "r",
    "sql",
    "matlab",
    "julia",
]
_FRAMEWORKS = [
    "pytorch",
    "tensorflow",
    "jax",
    "keras",
    "scikit-learn",
    "sklearn",
    "pandas",
    "numpy",
    "spark",
    "hadoop",
    "airflow",
    "kubernetes",
    "docker",
    "fastapi",
    "flask",
    "django",
    "react",
    "node",
    "langchain",
    "huggingface",
    "transformers",
    "ray",
    "kubeflow",
    "mlflow",
    "faiss",
    "spacy",
]
_SKILLS = [
    "machine learning",
    "deep learning",
    "nlp",
    "natural language processing",
    "computer vision",
    "reinforcement learning",
    "rag",
    "retrieval",
    "llm",
    "large language models",
    "data pipelines",
    "mlops",
    "distributed systems",
    "statistics",
    "recommendation systems",
    "information retrieval",
    "embeddings",
    "data science",
    "model evaluation",
    "feature engineering",
    "a/b testing",
    # Marketing / growth skills
    "marketing",
    "digital marketing",
    "social media",
    "content marketing",
    "email marketing",
    "seo",
    "sem",
    "paid social",
    "google ads",
    "google analytics",
    "market research",
    "brand",
    "copywriting",
    "hubspot",
    "canva",
    "crm",
]
_DEGREE_PATTERNS = {
    "PhD": r"\bph\.?d\b|\bdoctorate\b",
    "Master's": r"\bmaster'?s\b|\bm\.?s\.?\b|\bmsc\b",
    "Bachelor's": r"\bbachelor'?s\b|\bb\.?s\.?\b|\bbsc\b|\bundergraduate\b",
}


class JobParser:
    def __init__(self, llm: LLMProvider, prompts: PromptRegistry) -> None:
        self.llm = llm
        self.prompts = prompts

    def parse(self, job: Job) -> tuple[ParsedJob, str]:
        rendered = self.prompts.render(
            "parse_job",
            title=job.title,
            company=job.company,
            location=job.location,
            description=job.description or job.title,
        )
        data = self.llm.complete_json(rendered.messages(), fallback=lambda: _heuristic_parse(job))
        parsed = _coerce(data, job)
        return parsed, rendered.version


def _heuristic_parse(job: Job) -> dict[str, Any]:
    text = f"{job.title}\n{job.description}".lower()

    def present(terms: list[str]) -> list[str]:
        return [t for t in terms if re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", text)]

    languages = present(_LANGUAGES)
    frameworks = present(_FRAMEWORKS)
    skills = present(_SKILLS)

    years = None
    match = re.search(r"(\d+)\+?\s*(?:years|yrs)", text)
    if match:
        years = int(match.group(1))

    degrees = [label for label, pat in _DEGREE_PATTERNS.items() if re.search(pat, text)]

    visa = None
    if re.search(r"no\s+(?:visa\s+)?sponsorship|not\s+(?:able|eligible)\s+to\s+sponsor", text):
        visa = False
    elif re.search(r"visa\s+sponsorship|will\s+sponsor|sponsorship\s+available", text):
        visa = True

    clearance = None
    if re.search(r"clearance|ts/sci|secret\b", text):
        clearance = "required"

    research = []
    if re.search(r"\bresearch\b|publication|paper|neurips|icml|acl\b", text):
        research.append("research experience or publications")

    responsibilities = [
        line.strip("-*• ").strip()
        for line in job.description.splitlines()
        if line.strip().startswith(("-", "*", "•")) and len(line.strip()) > 3
    ][:10]

    keywords = sorted(set(skills + frameworks + languages))

    return {
        "required_skills": (skills + frameworks)[:12],
        "preferred_skills": languages,
        "years_experience": years,
        "programming_languages": languages,
        "frameworks": frameworks,
        "degree_requirements": degrees,
        "research_requirements": research,
        "security_clearance": clearance,
        "visa_sponsorship": visa,
        "industry": None,
        "keywords": keywords,
        "responsibilities": responsibilities,
        "technologies": frameworks + languages,
    }


def _coerce(data: dict[str, Any], job: Job) -> ParsedJob:
    try:
        return ParsedJob.model_validate(data)
    except Exception as exc:
        logger.warning("Parsed data invalid (%s); falling back to heuristic", exc)
        return ParsedJob.model_validate(_heuristic_parse(job))
