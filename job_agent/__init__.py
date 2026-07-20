"""job_agent — an AI-powered job discovery, tailoring, and tracking pipeline.

SQLite is the single source of truth; Excel is a generated projection. Every
pipeline stage is resumable, every artifact is stored, and every LLM prompt is
versioned. See ``docs/architecture.md`` for the full design.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
