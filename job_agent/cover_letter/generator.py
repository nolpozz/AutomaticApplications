"""Cover-letter generator.

Mirrors the resume generator: LLM path with strict anti-hallucination / anti-
cliche rules, and a deterministic Jinja fallback drawing on the same real
material and the user's writing samples. Supports multiple templates.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from job_agent.config.logging import get_logger
from job_agent.documents.render import DocumentRenderer
from job_agent.knowledge.loader import KnowledgeBase, Profile
from job_agent.llm.base import LLMProvider
from job_agent.llm.prompts import PromptRegistry
from job_agent.models.domain import GeneratedDocument, Job, ParsedJob, RetrievedKnowledge

logger = get_logger(__name__)


class CoverLetterGenerator:
    def __init__(
        self,
        llm: LLMProvider,
        prompts: PromptRegistry,
        renderer: DocumentRenderer,
        templates_dir: Path | str,
        *,
        template_name: str = "cover_letter.md.j2",
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
        knowledge: KnowledgeBase,
        *,
        formats: list[str] | None = None,
        template_name: str | None = None,
    ) -> GeneratedDocument:
        formats = formats or ["md", "docx", "pdf"]
        profile: Profile = knowledge.profile
        experience_items = [i.text for i in (retrieved.experience + retrieved.projects)][:6]
        context: dict[str, Any] = dict(
            title=job.title,
            company=job.company,
            requirements=(parsed.required_skills[:8] or parsed.keywords[:8]),
            candidate_name=profile.name,
            experience=experience_items,
            motivation=profile.motivation or "I'm drawn to the problems this team works on.",
            writing_samples=knowledge.writing_samples(),
            profile=profile,
            date=_today(),
        )

        rendered = self.prompts.render("cover_letter", **context)
        body = self.llm.complete_text(
            rendered.messages(), fallback=lambda: self._render_body(context)
        ).strip()
        if not body:
            body = self._render_body(context)

        # Wrap the letter body in the chosen template (header/greeting/signoff).
        markdown = self._wrap(template_name or self.template_name, context, body)
        basename = _basename(job, "cover-letter")
        paths = self.renderer.render(markdown, basename, formats)
        logger.info("Generated cover letter for %s (%s)", job.title, ", ".join(paths))
        return GeneratedDocument(
            job_id=job.id,
            kind="cover_letter",
            markdown=markdown,
            paths=paths,
            prompt_version=rendered.version,
        )

    def _render_body(self, context: dict) -> str:
        # Deterministic, cliche-free body assembled from real material.
        exp = context["experience"]
        lead = exp[0] if exp else "my recent work"
        second = exp[1] if len(exp) > 1 else ""
        reqs = ", ".join(context["requirements"][:4]) or "this work"
        paras = [
            f"I'm applying for the {context['title']} role at {context['company']}. "
            f"{context['motivation']}",
            f"Most recently, {lead}",
            (f"Earlier, {second}" if second else ""),
            f"The overlap with what you need — {reqs} — is close, and I'd welcome the "
            f"chance to talk about how I could contribute.",
        ]
        return "\n\n".join(p for p in paras if p.strip())

    def _wrap(self, template_name: str, context: dict, body: str) -> str:
        try:
            template = self._env.get_template(template_name)
        except Exception as exc:
            logger.warning("Template %s not found (%s); using raw body", template_name, exc)
            return body
        return template.render(body=body, **context).strip()


def _today() -> str:
    from datetime import date

    return date.today().strftime("%B %d, %Y")


def _basename(job: Job, kind: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", f"{job.company}-{job.title}".lower()).strip("-")
    return f"{slug[:60]}-{kind}-{job.id[:8]}"
