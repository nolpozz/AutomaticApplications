"""Cover-letter generator.

Two modes:

* **Narrative-block assembly** (preferred, when the user supplies narrative
  blocks): the letter is assembled from the user's own pre-written, tagged
  paragraphs, with only the one company-specific ``{{HOOK}}`` sentence written
  fresh by the LLM. This follows the user's cover-letter "system" exactly.
* **Free generation** (fallback, when no blocks are configured): LLM writes the
  body under strict anti-cliche / anti-hallucination rules, with a deterministic
  template fallback.

Supports multiple templates (header/greeting/signoff wrapping).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from job_agent.config.logging import get_logger
from job_agent.cover_letter.blocks import NarrativeBlock, assemble, derive_job_tags
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
        blocks: list[NarrativeBlock] | None = None,
    ) -> None:
        self.llm = llm
        self.prompts = prompts
        self.renderer = renderer
        self.template_name = template_name
        self.blocks = blocks or []
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

        if self.blocks:
            body, prompt_version = self._assemble_from_blocks(job, parsed, profile, context)
        else:
            rendered = self.prompts.render("cover_letter", **context)
            body = self.llm.complete_text(
                rendered.messages(), fallback=lambda: self._render_body(context)
            ).strip()
            if not body:
                body = self._render_body(context)
            prompt_version = rendered.version

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
            prompt_version=prompt_version,
        )

    def _assemble_from_blocks(
        self, job: Job, parsed: ParsedJob, profile: Profile, context: dict
    ) -> tuple[str, str]:
        job_tags = derive_job_tags(job, parsed)
        hook = self._write_hook(job, parsed, profile)
        body = assemble(self.blocks, job_tags, company=job.company, role=job.title, hook=hook)
        logger.info(
            "Assembled cover letter from narrative blocks (tags: %s)", ", ".join(sorted(job_tags))
        )
        return body, "cover_letter_blocks.v1"

    def _write_hook(self, job: Job, parsed: ParsedJob, profile: Profile) -> str:
        """Write the single company-specific hook sentence (fresh every time)."""
        focus = profile.headline or profile.summary[:200]
        rendered = self.prompts.render(
            "cover_letter_hook",
            company=job.company,
            title=job.title,
            requirements=(parsed.required_skills[:6] or parsed.keywords[:6]),
            candidate_focus=focus,
        )

        def _fallback() -> str:
            reqs = ", ".join(parsed.required_skills[:3] or parsed.keywords[:3]) or "this work"
            return (
                f"The work at {job.company} on {reqs} lines up closely with where I've "
                f"chosen to focus, which is why this role stood out to me."
            )

        hook = self.llm.complete_text(rendered.messages(), fallback=_fallback).strip()
        # Keep it to a single clean sentence.
        return hook.split("\n")[0].strip().strip('"')

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
