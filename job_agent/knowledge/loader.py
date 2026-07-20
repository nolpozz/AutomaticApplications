"""Load the user's knowledge base from Markdown/YAML into typed items.

No resume content is hardcoded anywhere in the codebase (design requirement).
Everything the agent knows about the user comes from ``user_data/``:

    user_data/
      profile.yaml                 # name, contact, headline, summary, motivation
      experience/*.md|*.yaml
      projects/*.md|*.yaml
      education/  skills/  awards/  coursework/  certifications/
      publications/  resume_bullets/  cover_letter_examples/

Markdown files are split into items by ``## headings`` when present, otherwise by
bullet lines, otherwise treated as a single item. YAML files may hold a list of
``{title, text, tags}`` objects or a single object.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from job_agent.config.logging import get_logger
from job_agent.models.domain import KnowledgeItem

logger = get_logger(__name__)

# Folder name -> canonical category label.
_CATEGORIES = {
    "experience": "experience",
    "projects": "project",
    "education": "education",
    "skills": "skill",
    "awards": "award",
    "coursework": "course",
    "certifications": "certification",
    "publications": "research",
    "resume_bullets": "resume_bullet",
    "cover_letter_examples": "writing_sample",
}


@dataclass
class Profile:
    name: str = "Your Name"
    email: str = ""
    phone: str = ""
    location: str = ""
    headline: str = ""
    summary: str = ""
    motivation: str = ""
    links: dict[str, str] = field(default_factory=dict)

    def header_markdown(self) -> str:
        contact = " | ".join(x for x in [self.email, self.phone, self.location] if x)
        links = " | ".join(f"[{k}]({v})" for k, v in self.links.items())
        lines = [f"# {self.name}"]
        if self.headline:
            lines.append(f"*{self.headline}*")
        if contact:
            lines.append(contact)
        if links:
            lines.append(links)
        return "\n\n".join(lines)


class KnowledgeBase:
    """In-memory view of the user's background, loaded from disk."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.profile = Profile()
        self.items: list[KnowledgeItem] = []

    def load(self) -> KnowledgeBase:
        self._load_profile()
        self.items = []
        for folder, category in _CATEGORIES.items():
            directory = self.root / folder
            if not directory.exists():
                continue
            for path in sorted(directory.glob("*")):
                if path.suffix.lower() in {".yaml", ".yml"}:
                    self.items.extend(self._parse_yaml(path, category))
                elif path.suffix.lower() in {".md", ".markdown", ".txt"}:
                    self.items.extend(self._parse_markdown(path, category))
        logger.info("Loaded %d knowledge items from %s", len(self.items), self.root)
        return self

    # -- accessors used by retrieval / generators ---------------------------
    def by_category(self, *categories: str) -> list[KnowledgeItem]:
        wanted = set(categories)
        return [item for item in self.items if item.category in wanted]

    def writing_samples(self, limit: int = 2) -> str:
        samples = self.by_category("writing_sample")[:limit]
        return "\n\n---\n\n".join(s.text for s in samples) or "(no writing samples provided)"

    def profile_summary(self) -> str:
        """A compact textual profile for the classifier prompt."""
        skills = ", ".join(i.title for i in self.by_category("skill"))
        edu = "; ".join(i.title for i in self.by_category("education"))
        exp = "; ".join(i.title for i in self.by_category("experience"))
        parts = [
            f"Name: {self.profile.name}",
            f"Headline: {self.profile.headline}",
            f"Summary: {self.profile.summary}",
            f"Education: {edu}",
            f"Experience: {exp}",
            f"Skills: {skills}",
        ]
        return "\n".join(p for p in parts if p.split(": ", 1)[-1].strip())

    # -- parsing helpers ----------------------------------------------------
    def _load_profile(self) -> None:
        path = self.root / "profile.yaml"
        if not path.exists():
            path = self.root / "profile.yml"
        if not path.exists():
            logger.warning("No profile.yaml found in %s; using defaults", self.root)
            return
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        self.profile = Profile(
            name=data.get("name", "Your Name"),
            email=data.get("email", ""),
            phone=data.get("phone", ""),
            location=data.get("location", ""),
            headline=data.get("headline", ""),
            summary=data.get("summary", ""),
            motivation=data.get("motivation", ""),
            links=data.get("links", {}) or {},
        )

    def _parse_yaml(self, path: Path, category: str) -> list[KnowledgeItem]:
        data: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        entries: list[dict[str, Any]]
        if isinstance(data, list):
            entries = [e for e in data if isinstance(e, dict)]
        elif isinstance(data, dict) and "items" in data:
            entries = [e for e in data["items"] if isinstance(e, dict)]
        elif isinstance(data, dict):
            entries = [data]
        else:
            return []
        items = []
        for entry in entries:
            items.append(
                KnowledgeItem(
                    category=category,
                    title=str(entry.get("title") or entry.get("name") or path.stem),
                    text=str(entry.get("text") or entry.get("description") or ""),
                    tags=[str(t) for t in (entry.get("tags") or [])],
                    metadata={
                        k: v
                        for k, v in entry.items()
                        if k not in {"title", "name", "text", "description", "tags"}
                    },
                )
            )
        return items

    def _parse_markdown(self, path: Path, category: str) -> list[KnowledgeItem]:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return []
        sections = re.split(r"^##\s+", text, flags=re.MULTILINE)
        items: list[KnowledgeItem] = []
        # Sectioned document.
        if len(sections) > 1:
            for section in sections[1:]:
                lines = section.strip().splitlines()
                title = lines[0].strip() if lines else path.stem
                body = "\n".join(lines[1:]).strip()
                items.append(self._make_item(category, title, body))
            return items
        # Bullet list -> one item per bullet (good for resume_bullets/skills).
        bullets = [m.group(1).strip() for m in re.finditer(r"^[-*]\s+(.*)$", text, re.MULTILINE)]
        if bullets and category in {"resume_bullet", "skill", "award", "certification", "course"}:
            for bullet in bullets:
                items.append(self._make_item(category, bullet.split(":")[0][:60], bullet))
            return items
        # Otherwise, whole file is one item.
        first_heading = re.search(r"^#\s+(.*)$", text, re.MULTILINE)
        title = first_heading.group(1).strip() if first_heading else path.stem.replace("_", " ")
        items.append(self._make_item(category, title, text))
        return items

    @staticmethod
    def _make_item(category: str, title: str, text: str) -> KnowledgeItem:
        tags = _extract_tech_tags(f"{title} {text}")
        return KnowledgeItem(category=category, title=title.strip(), text=text.strip(), tags=tags)


# A small technology lexicon lets us tag items for keyword-based retrieval
# fallback (used when embeddings are the mock provider).
_TECH_LEXICON = {
    "python",
    "java",
    "c++",
    "c",
    "go",
    "rust",
    "typescript",
    "javascript",
    "sql",
    "pytorch",
    "tensorflow",
    "jax",
    "scikit-learn",
    "sklearn",
    "numpy",
    "pandas",
    "transformers",
    "huggingface",
    "langchain",
    "llm",
    "nlp",
    "rag",
    "cv",
    "kubernetes",
    "docker",
    "aws",
    "gcp",
    "azure",
    "spark",
    "hadoop",
    "airflow",
    "fastapi",
    "flask",
    "django",
    "react",
    "postgres",
    "redis",
    "faiss",
    "ml",
    "machine learning",
    "deep learning",
    "reinforcement learning",
    "research",
}


def _extract_tech_tags(text: str) -> list[str]:
    lower = text.lower()
    return sorted({tech for tech in _TECH_LEXICON if tech in lower})


_kb_cache: dict[str, KnowledgeBase] = {}


def load_knowledge_base(root: Path | str, *, use_cache: bool = True) -> KnowledgeBase:
    key = str(Path(root).resolve())
    if use_cache and key in _kb_cache:
        return _kb_cache[key]
    kb = KnowledgeBase(root).load()
    _kb_cache[key] = kb
    return kb
