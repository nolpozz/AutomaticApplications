"""Tailored cover-letter generation (free-form or narrative-block assembly)."""

from job_agent.cover_letter.blocks import (
    NarrativeBlock,
    assemble,
    derive_job_tags,
    load_blocks,
    select_blocks,
)
from job_agent.cover_letter.generator import CoverLetterGenerator

__all__ = [
    "CoverLetterGenerator",
    "NarrativeBlock",
    "assemble",
    "derive_job_tags",
    "load_blocks",
    "select_blocks",
]
