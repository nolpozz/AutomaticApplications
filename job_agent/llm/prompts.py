"""Versioned prompt registry (design principle #5).

Prompt templates live as files under ``job_agent/llm/prompts/`` named
``<name>.v<N>.txt``. Each file has a ``===SYSTEM===`` and a ``===USER===``
section, both Jinja2 templates. The registry loads them, tracks versions, and
renders with a context. Callers request a prompt by name; the highest version is
used unless one is pinned. Every rendered prompt reports the version string
(``name.vN``) so it can be stored alongside the artifact it produced.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, StrictUndefined

from job_agent.config.logging import get_logger
from job_agent.llm.base import LLMMessage

logger = get_logger(__name__)

_FILENAME_RE = re.compile(r"^(?P<name>[a-z0-9_]+)\.v(?P<version>\d+)\.txt$")
_SECTION_RE = re.compile(r"===SYSTEM===(?P<system>.*?)===USER===(?P<user>.*)", re.DOTALL)


@dataclass
class RenderedPrompt:
    system: str
    user: str
    version: str  # e.g. "parse_job.v1"

    def messages(self) -> list[LLMMessage]:
        msgs: list[LLMMessage] = []
        if self.system.strip():
            msgs.append(LLMMessage(role="system", content=self.system.strip()))
        msgs.append(LLMMessage(role="user", content=self.user.strip()))
        return msgs


class PromptRegistry:
    def __init__(self, prompts_dir: Path | str) -> None:
        self.dir = Path(prompts_dir)
        self._env = Environment(undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True)
        self._index: dict[str, dict[int, Path]] = {}
        self._scan()

    def _scan(self) -> None:
        self._index.clear()
        if not self.dir.exists():
            logger.warning("Prompt directory %s does not exist", self.dir)
            return
        for path in self.dir.glob("*.txt"):
            match = _FILENAME_RE.match(path.name)
            if not match:
                continue
            name = match.group("name")
            version = int(match.group("version"))
            self._index.setdefault(name, {})[version] = path

    def available(self) -> dict[str, list[int]]:
        return {name: sorted(versions) for name, versions in self._index.items()}

    def latest_version(self, name: str) -> int:
        if name not in self._index:
            raise KeyError(f"No prompt named {name!r}; available: {sorted(self._index)}")
        return max(self._index[name])

    def render(self, name: str, *, version: int | None = None, **context: object) -> RenderedPrompt:
        if name not in self._index:
            raise KeyError(f"No prompt named {name!r}; available: {sorted(self._index)}")
        version = version or self.latest_version(name)
        path = self._index[name].get(version)
        if path is None:
            raise KeyError(f"Prompt {name!r} has no version {version}")
        raw = path.read_text(encoding="utf-8")
        match = _SECTION_RE.search(raw)
        if not match:
            raise ValueError(f"Prompt file {path} missing ===SYSTEM===/===USER=== sections")
        system = self._env.from_string(match.group("system")).render(**context)
        user = self._env.from_string(match.group("user")).render(**context)
        return RenderedPrompt(system=system, user=user, version=f"{name}.v{version}")


_registry: PromptRegistry | None = None


def get_prompt_registry(prompts_dir: Path | str | None = None) -> PromptRegistry:
    global _registry
    if prompts_dir is not None:
        return PromptRegistry(prompts_dir)
    if _registry is None:
        default_dir = Path(__file__).parent / "prompts"
        _registry = PromptRegistry(default_dir)
    return _registry
