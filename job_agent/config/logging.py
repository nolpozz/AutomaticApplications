"""Logging configuration: rotating files + optional structured JSON output.

Call :func:`configure_logging` once at process start (the CLI does this). Every
module obtains a logger via ``logging.getLogger(__name__)`` and never uses
``print``.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record for machine-readable logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Attach any structured extras passed via ``logger.info(..., extra={"ctx": {...}})``.
        ctx = getattr(record, "ctx", None)
        if isinstance(ctx, dict):
            payload["ctx"] = ctx
        return json.dumps(payload, default=str)


def configure_logging(
    level: str = "INFO",
    *,
    log_dir: Path | str = "data/logs",
    json_output: bool = False,
) -> None:
    """Configure root logging with a console handler and a rotating file handler."""
    global _CONFIGURED
    root = logging.getLogger()
    root.setLevel(level.upper())

    # Remove pre-existing handlers so repeated calls (tests, notebooks) are safe.
    for handler in list(root.handlers):
        root.removeHandler(handler)

    console = logging.StreamHandler()
    text_fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    console.setFormatter(JsonFormatter() if json_output else text_fmt)
    root.addHandler(console)

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        log_path / "job_agent.log",
        maxBytes=5_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(JsonFormatter())
    root.addHandler(file_handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger, configuring logging with defaults if not yet done."""
    if not _CONFIGURED:
        configure_logging()
    return logging.getLogger(name)
