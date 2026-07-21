"""Narrative-block cover-letter assembly.

Instead of writing a letter from scratch, this assembles one from the user's
pre-written, reusable paragraphs ("narrative blocks"), each tagged by theme.
Given a job, it picks one OPENING, two to three BODY blocks whose tags best match
the role (avoiding blocks that repeat the same evidence), and one CLOSING, then
fills the ``{{COMPANY}}``/``{{ROLE}}``/``{{HOOK}}`` slots. ``{{HOOK}}`` — the one
genuinely company-specific sentence — is written fresh each time (by the LLM,
with a deterministic fallback).

Block file format (Markdown)::

    ### opening-applied-systems
    - **type:** opening
    - **tags:** ml, llm, agents, product
    I am excited to apply for the {{ROLE}} position at {{COMPANY}}. ... {{HOOK}}
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from job_agent.config.logging import get_logger
from job_agent.models.domain import Job, ParsedJob

logger = get_logger(__name__)

# The tag vocabulary used to match blocks to jobs.
TAG_VOCAB = {
    "ml",
    "llm",
    "interp",
    "agents",
    "nlp",
    "research",
    "swe",
    "product",
    "optimization",
    "data",
    "linguistics",
    "startup",
    "fullstack",
    "evaluation",
}

# Signals (substrings) that imply each tag, matched against the job text.
_TAG_SIGNALS: dict[str, tuple[str, ...]] = {
    "ml": ("machine learning", "ml engineer", "deep learning", "pytorch", "model training"),
    "llm": ("llm", "large language model", "language model", "gpt", "fine-tun", "transformer"),
    "interp": ("interpretability", "mechanistic", "activation", "probe", "alignment"),
    "agents": ("agent", "langgraph", "langchain", "multi-agent", "tool use", "orchestration"),
    "nlp": ("nlp", "natural language", "retrieval", "rag", "embedding", "search", "text"),
    "research": ("research", "publication", "paper", "phd", "scientist"),
    "swe": ("software engineer", "backend", "api", "distributed", "infrastructure", "platform"),
    "product": ("product", "customer", "user-facing", "ship", "growth"),
    "optimization": ("optimization", "operations research", "milp", "routing", "logistics"),
    "data": ("data scientist", "data science", "sql", "analytics", "pipeline", "experimentation"),
    "linguistics": ("linguist", "syntax", "semantics", "phonetic", "multilingual"),
    "startup": ("startup", "founding", "early-stage", "seed", "series a"),
    "fullstack": ("full stack", "full-stack", "frontend", "front-end", "react", "vue"),
    "evaluation": ("evaluation", "eval", "benchmark", "quality"),
}


@dataclass
class NarrativeBlock:
    name: str
    type: str  # opening | body | closing
    tags: set[str] = field(default_factory=set)
    text: str = ""


_HEADER_RE = re.compile(r"^###\s+(.+?)\s*$")
# Matches both `- **type:** opening` and `- **type**: opening`.
_META_RE = re.compile(r"^-\s*\*\*(?P<key>type|tags):?\*\*:?\s*(?P<val>.+?)\s*$", re.IGNORECASE)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def load_blocks(path: Path | str) -> list[NarrativeBlock]:
    """Parse narrative blocks from a Markdown file. Returns [] if missing/empty."""
    p = Path(path)
    if not p.exists():
        return []
    text = _COMMENT_RE.sub("", p.read_text(encoding="utf-8"))
    blocks: list[NarrativeBlock] = []
    current: NarrativeBlock | None = None
    body_lines: list[str] = []

    def _flush() -> None:
        if current is not None:
            current.text = " ".join(ln.strip() for ln in body_lines if ln.strip()).strip()
            if current.type and current.text:
                blocks.append(current)

    for line in text.splitlines():
        header = _HEADER_RE.match(line)
        if header:
            _flush()
            current = NarrativeBlock(name=header.group(1), type="")
            body_lines = []
            continue
        if current is None:
            continue
        if line.startswith("## "):  # a section header ends the block region
            _flush()
            current = None
            continue
        meta = _META_RE.match(line)
        if meta:
            key, val = meta.group("key").lower(), meta.group("val")
            if key == "type":
                current.type = val.strip().lower()
            else:
                current.tags = {t.strip().lower() for t in val.split(",") if t.strip()}
            continue
        body_lines.append(line)
    _flush()
    logger.info("Loaded %d narrative blocks from %s", len(blocks), p)
    return blocks


def derive_job_tags(job: Job, parsed: ParsedJob | None) -> set[str]:
    """Infer which block tags a job is about, from its text and parsed fields."""
    haystack = " ".join(
        [job.title, job.description]
        + (parsed.required_skills + parsed.preferred_skills + parsed.keywords if parsed else [])
    ).lower()
    tags = {tag for tag, signals in _TAG_SIGNALS.items() if any(s in haystack for s in signals)}
    return tags or {"ml"}  # never empty, so matching still works


def _score(block: NarrativeBlock, job_tags: set[str]) -> int:
    return len(block.tags & job_tags)


def select_blocks(
    blocks: list[NarrativeBlock], job_tags: set[str], *, max_body: int = 3
) -> list[NarrativeBlock]:
    """Choose opening + best-matching, non-redundant bodies + closing."""
    openings = [b for b in blocks if b.type == "opening"]
    bodies = [b for b in blocks if b.type == "body"]
    closings = [b for b in blocks if b.type == "closing"]

    chosen: list[NarrativeBlock] = []
    if openings:
        chosen.append(max(openings, key=lambda b: (_score(b, job_tags), -len(b.tags))))

    # Greedily add the highest-scoring bodies that actually match the job,
    # skipping ones that mostly repeat the evidence of an already-chosen body
    # (tag Jaccard > 0.6). Non-matching (zero-overlap) bodies are not padded in.
    scored = sorted(bodies, key=lambda b: _score(b, job_tags), reverse=True)
    picked_bodies: list[NarrativeBlock] = []
    for block in scored:
        if len(picked_bodies) >= max_body:
            break
        if _score(block, job_tags) == 0:
            continue
        if any(_jaccard(block.tags, pb.tags) > 0.6 for pb in picked_bodies):
            continue
        picked_bodies.append(block)
    # Guarantee at least one body if any exist (fall back to the best-scoring).
    if bodies and not picked_bodies:
        picked_bodies.append(scored[0])
    chosen.extend(picked_bodies)

    if closings:
        chosen.append(max(closings, key=lambda b: (_score(b, job_tags), -len(b.tags))))
    return chosen


def assemble(
    blocks: list[NarrativeBlock], job_tags: set[str], *, company: str, role: str, hook: str
) -> str:
    selected = select_blocks(blocks, job_tags)
    filled = [_fill(b.text, company=company, role=role, hook=hook) for b in selected]
    return "\n\n".join(p for p in filled if p.strip()).strip()


def _fill(text: str, *, company: str, role: str, hook: str) -> str:
    out = text.replace("{{COMPANY}}", company).replace("{{ROLE}}", role)
    out = out.replace("{{HOOK}}", hook)
    return re.sub(r"\s+", " ", out).strip()


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
