"""Tests for narrative-block cover letters and role targeting."""

from __future__ import annotations

from job_agent.classifier.classifier import JobClassifier
from job_agent.cover_letter.blocks import (
    NarrativeBlock,
    assemble,
    derive_job_tags,
    load_blocks,
    select_blocks,
)
from job_agent.cover_letter.generator import CoverLetterGenerator
from job_agent.documents.render import DocumentRenderer
from job_agent.embeddings.service import EmbeddingService
from job_agent.models.domain import ExperienceLevel, Job, ParsedJob
from job_agent.parser.llm_parser import JobParser
from job_agent.retrieval.retriever import Retriever

_BLOCKS_MD = """
# Blocks

### opening-a
- **type:** opening
- **tags:** ml, llm
Applying for {{ROLE}} at {{COMPANY}}. {{HOOK}}

### body-research
- **type:** body
- **tags:** research, interp, nlp
I did interpretability research on multilingual models.

### body-product
- **type:** body
- **tags:** product, startup, llm
I shipped an LLM feature to enterprise users at a startup.

### body-optimization
- **type:** body
- **tags:** optimization, data
I applied MILP to logistics and saved money.

### closing-a
- **type:** closing
- **tags:** general
Thanks for your consideration.
"""


def test_load_blocks_parses_types_and_tags(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "narrative_blocks.md"
    path.write_text(_BLOCKS_MD, encoding="utf-8")
    blocks = load_blocks(path)
    assert len(blocks) == 5
    opening = next(b for b in blocks if b.name == "opening-a")
    assert opening.type == "opening"
    assert opening.tags == {"ml", "llm"}


def test_load_blocks_missing_file_returns_empty(tmp_path) -> None:  # type: ignore[no-untyped-def]
    assert load_blocks(tmp_path / "nope.md") == []


def test_select_blocks_matches_tags_and_avoids_redundancy() -> None:
    blocks = load_blocks_from_string()
    # A research/NLP job should pull the research body, not the optimization one.
    selected = select_blocks(blocks, {"research", "nlp", "interp"})
    types = [b.type for b in selected]
    assert types[0] == "opening" and types[-1] == "closing"
    body_names = {b.name for b in selected if b.type == "body"}
    assert "body-research" in body_names
    assert "body-optimization" not in body_names


def test_assemble_fills_slots() -> None:
    blocks = load_blocks_from_string()
    tags = {"research", "nlp"}
    letter = assemble(blocks, tags, company="Acme", role="ML Engineer", hook="I love your work.")
    assert "{{COMPANY}}" not in letter and "{{ROLE}}" not in letter and "{{HOOK}}" not in letter
    assert "Acme" in letter and "ML Engineer" in letter and "I love your work." in letter


def test_derive_job_tags_from_description() -> None:
    job = Job(
        title="ML Research Intern",
        company="X",
        url="u",
        source="s",
        description="interpretability of large language models and NLP evaluation",
    )
    tags = derive_job_tags(job, ParsedJob(required_skills=["llm", "nlp"]))
    assert "interp" in tags and "llm" in tags and "nlp" in tags


def test_generator_uses_blocks_when_provided(  # type: ignore[no-untyped-def]
    tmp_path, settings, repo, knowledge, llm, prompts
) -> None:
    service = EmbeddingService.from_settings(settings, repo)
    service.index_knowledge(knowledge)
    job = Job(
        title="NLP Research Intern",
        company="Acme",
        url="u",
        source="s",
        description="interpretability and evaluation of language models",
    )
    parsed, _ = JobParser(llm, prompts).parse(job)
    retrieved = Retriever(service, knowledge).retrieve(job, parsed)
    gen = CoverLetterGenerator(
        llm,
        prompts,
        DocumentRenderer(tmp_path / "docs"),
        settings.storage.templates_path,
        blocks=load_blocks_from_string(),
    )
    doc = gen.generate(job, parsed, retrieved, knowledge, formats=["md"])
    assert doc.prompt_version == "cover_letter_blocks.v1"
    assert "Acme" in doc.markdown


def test_targeting_penalizes_off_target_roles(  # type: ignore[no-untyped-def]
    llm, prompts, knowledge
) -> None:
    parsed = ParsedJob(
        required_skills=["python", "pytorch", "nlp"], programming_languages=["python"]
    )
    intern = Job(
        title="ML Research Intern",
        company="X",
        url="u1",
        source="s",
        description="summer internship in NLP",
        experience_level=ExperienceLevel.INTERN,
    )
    senior = Job(
        title="Senior ML Engineer",
        company="X",
        url="u2",
        source="s",
        description="lead our ML team",
        experience_level=ExperienceLevel.SENIOR,
    )
    clf = JobClassifier(
        llm,
        prompts,
        knowledge,
        target_levels=["intern"],
        target_keywords=["intern", "internship", "summer"],
        target_description="Master's-level internships",
    )
    intern_score, _ = clf.classify(intern, parsed)
    senior_score, _ = clf.classify(senior, parsed)
    assert intern_score.overall_score > senior_score.overall_score


def load_blocks_from_string() -> list[NarrativeBlock]:
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "b.md"
        p.write_text(_BLOCKS_MD, encoding="utf-8")
        return load_blocks(p)
