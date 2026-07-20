"""Resume and cover-letter generation tests."""

from __future__ import annotations

from job_agent.cover_letter.generator import CoverLetterGenerator
from job_agent.documents.render import DocumentRenderer
from job_agent.embeddings.service import EmbeddingService
from job_agent.parser.llm_parser import JobParser
from job_agent.resume.generator import ResumeGenerator
from job_agent.retrieval.retriever import Retriever


def _setup(tmp_path, settings, repo, knowledge, llm, prompts, sample_job):  # type: ignore[no-untyped-def]
    service = EmbeddingService.from_settings(settings, repo)
    service.index_knowledge(knowledge)
    parsed, _ = JobParser(llm, prompts).parse(sample_job)
    retrieved = Retriever(service, knowledge).retrieve(sample_job, parsed)
    renderer = DocumentRenderer(tmp_path / "docs")
    return parsed, retrieved, renderer


def test_resume_generation_uses_real_material(  # type: ignore[no-untyped-def]
    tmp_path, settings, repo, knowledge, llm, prompts, sample_job
) -> None:
    parsed, retrieved, renderer = _setup(
        tmp_path, settings, repo, knowledge, llm, prompts, sample_job
    )
    gen = ResumeGenerator(llm, prompts, renderer, settings.storage.templates_path)
    doc = gen.generate(sample_job, parsed, retrieved, knowledge.profile, formats=["md"])
    assert doc.kind == "resume"
    assert doc.prompt_version == "resume.v1"
    assert knowledge.profile.name in doc.markdown  # header is the real user
    assert "md" in doc.paths


def test_cover_letter_avoids_cliches(  # type: ignore[no-untyped-def]
    tmp_path, settings, repo, knowledge, llm, prompts, sample_job
) -> None:
    parsed, retrieved, renderer = _setup(
        tmp_path, settings, repo, knowledge, llm, prompts, sample_job
    )
    gen = CoverLetterGenerator(llm, prompts, renderer, settings.storage.templates_path)
    doc = gen.generate(sample_job, parsed, retrieved, knowledge, formats=["md"])
    lowered = doc.markdown.lower()
    for cliche in ["i am writing to express", "hit the ground running", "synergy"]:
        assert cliche not in lowered
    assert sample_job.company in doc.markdown


def test_cover_letter_supports_multiple_templates(  # type: ignore[no-untyped-def]
    tmp_path, settings, repo, knowledge, llm, prompts, sample_job
) -> None:
    parsed, retrieved, renderer = _setup(
        tmp_path, settings, repo, knowledge, llm, prompts, sample_job
    )
    gen = CoverLetterGenerator(llm, prompts, renderer, settings.storage.templates_path)
    formal = gen.generate(
        sample_job,
        parsed,
        retrieved,
        knowledge,
        formats=["md"],
        template_name="cover_letter_formal.md.j2",
    )
    assert "Re: Application for" in formal.markdown
