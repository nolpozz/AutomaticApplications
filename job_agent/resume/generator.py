"""Resume generator.

Produces a tailored resume by (a) prompting the LLM with ONLY the retrieved,
real material and strict "never invent" rules, or (b) — in mock mode or on
failure — deterministically rendering a Jinja template from the same material.
Either way, no experience is invented: both paths consume the identical set of
real knowledge items. Every version is stored (versioning handled by the repo).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from job_agent.config.logging import get_logger
from job_agent.documents.render import DocumentRenderer
from job_agent.knowledge.loader import Profile
from job_agent.llm.base import LLMProvider
from job_agent.llm.prompts import PromptRegistry
from job_agent.models.domain import GeneratedDocument, Job, ParsedJob, RetrievedKnowledge

logger = get_logger(__name__)


class ResumeGenerator:
    def __init__(
        self,
        llm: LLMProvider,
        prompts: PromptRegistry,
        renderer: DocumentRenderer,
        templates_dir: Path | str,
        *,
        template_name: str = "resume.md.j2",
    ) -> None:
        self.llm = llm
        self.prompts = prompts
        self.renderer = renderer
        self.template_name = template_name
        self._env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=select_autoescape(enabled_extensions=()),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def generate(
        self,
        job: Job,
        parsed: ParsedJob,
        retrieved: RetrievedKnowledge,
        profile: Profile,
        *,
        formats: list[str] | None = None,
    ) -> GeneratedDocument:
        formats = formats or ["md", "docx", "pdf"]
        requirements = parsed.required_skills[:10] or parsed.keywords[:10]
        context: dict[str, Any] = dict(
            title=job.title,
            company=job.company,
            requirements=requirements,
            header=profile.header_markdown(),
            profile=profile,
            summary=profile.summary,
            experience=[i.text for i in retrieved.experience],
            projects=[i.text for i in retrieved.projects],
            skills=[i.title for i in retrieved.skills],
            education=[],  # filled from profile-independent items if present
            resume_bullets=[i.text for i in retrieved.resume_bullets],
        )

        rendered = self.prompts.render("resume", **context)
        markdown = self.llm.complete_text(
            rendered.messages(), fallback=lambda: self._render_template(context)
        ).strip()
        if not markdown:
            markdown = self._render_template(context)

        basename = _basename(job, "resume")
        paths = self.renderer.render(markdown, basename, formats)
        logger.info("Generated resume for %s (%s)", job.title, ", ".join(paths))
        return GeneratedDocument(
            job_id=job.id,
            kind="resume",
            markdown=markdown,
            paths=paths,
            prompt_version=rendered.version,
        )

    def _render_template(self, context: dict) -> str:
        template = self._env.get_template(self.template_name)
        return template.render(**context).strip()


def _basename(job: Job, kind: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", f"{job.company}-{job.title}".lower()).strip("-")
    return f"{slug[:60]}-{kind}-{job.id[:8]}"
