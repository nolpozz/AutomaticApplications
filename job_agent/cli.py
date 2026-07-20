"""Command-line interface for the job agent.

Every command is a thin wrapper over :class:`~job_agent.orchestrator.Pipeline`
and the tracker, so the CLI carries no business logic of its own. Automated
stages accept ``--resume-after-failure/--stop-on-failure``.
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from job_agent.config.logging import configure_logging
from job_agent.config.settings import get_settings, reload_settings
from job_agent.database.base import Database
from job_agent.database.repository import Repository
from job_agent.models.domain import JobState
from job_agent.orchestrator.pipeline import Pipeline
from job_agent.scrapers.registry import available_boards
from job_agent.tracker.tracker import ApplicationTracker, DailyLimitReached

app = typer.Typer(add_completion=False, help="AI-powered job application agent.")
console = Console()


def _parse_list(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


@app.callback()
def _main(
    log_level: str | None = typer.Option(None, help="Override log level (DEBUG/INFO/...)."),
) -> None:
    settings = reload_settings()
    configure_logging(log_level or settings.log_level, json_output=settings.log_json)


def _pipeline(formats: str | None = None) -> Pipeline:
    fmt = _parse_list(formats)
    return Pipeline(get_settings(), formats=fmt)


def _print_report(title: str, report) -> None:  # type: ignore[no-untyped-def]
    console.print(f"[bold green]{title}[/bold green]: {report.summary()}")
    for err in report.errors[:10]:
        console.print(f"  [red]•[/red] {err}")


# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------
@app.command()
def pipeline(
    boards: str | None = typer.Option(None, help="Comma-separated board names to use."),
    offline: bool = typer.Option(True, help="Use deterministic sample data instead of network."),
    resume_after_failure: bool = typer.Option(True, help="Continue past per-job failures."),
    formats: str | None = typer.Option(None, help="Doc formats, e.g. 'md,docx,pdf'."),
) -> None:
    """Run the full automated pipeline: scrape → parse → embed → classify → docs."""
    report = _pipeline(formats).run(
        boards=_parse_list(boards),
        offline=offline if offline else None,
        resume_after_failure=resume_after_failure,
    )
    _print_report("Pipeline", report)


@app.command()
def scrape(
    boards: str | None = typer.Option(None, help="Comma-separated board names."),
    offline: bool = typer.Option(True, help="Use sample data instead of network."),
) -> None:
    """Discover jobs from the enabled boards."""
    report = _pipeline().scrape(boards=_parse_list(boards), offline=offline if offline else None)
    _print_report("Scrape", report)


@app.command()
def parse(resume_after_failure: bool = typer.Option(True)) -> None:
    """Parse requirements from all discovered jobs."""
    _print_report("Parse", _pipeline().parse_pending())


@app.command()
def embed(resume_after_failure: bool = typer.Option(True)) -> None:
    """Compute embeddings for all parsed jobs."""
    _print_report("Embed", _pipeline().embed_pending())


@app.command()
def classify(resume_after_failure: bool = typer.Option(True)) -> None:
    """Classify all embedded jobs and route them for review or rejection."""
    _print_report("Classify", _pipeline().classify_pending())


@app.command(name="generate-resume")
def generate_resume(
    resume_after_failure: bool = typer.Option(True),
    formats: str | None = typer.Option(None, help="Doc formats, e.g. 'md,docx,pdf'."),
) -> None:
    """Generate tailored resumes for jobs that passed classification."""
    _print_report("Resumes", _pipeline(formats).generate_resumes())


@app.command(name="generate-cover-letter")
def generate_cover_letter(
    resume_after_failure: bool = typer.Option(True),
    formats: str | None = typer.Option(None, help="Doc formats, e.g. 'md,docx,pdf'."),
) -> None:
    """Generate tailored cover letters and hand jobs off for review."""
    _print_report("Cover letters", _pipeline(formats).generate_cover_letters())


# ---------------------------------------------------------------------------
# Review & tracking
# ---------------------------------------------------------------------------
@app.command()
def review(
    state: str = typer.Option("READY_FOR_REVIEW", help="Which stage to list."),
    limit: int = typer.Option(50),
) -> None:
    """List jobs at a given stage (default: awaiting your review)."""
    settings = get_settings()
    db = Database(settings.storage.sqlite_path)
    db.create_all()
    with db.session_scope() as session:
        repo = Repository(session)
        jobs = repo.list_jobs(state=JobState(state), limit=limit)
        table = Table(title=f"Jobs in state {state}")
        for col in ("ID", "Company", "Position", "Score", "Rec", "Resume", "Cover"):
            table.add_column(col, overflow="fold")
        for job in jobs:
            score = repo.get_classifier(job.id)
            resume = repo.latest_resume(job.id)
            cover = repo.latest_cover_letter(job.id)
            table.add_row(
                job.id[:8],
                job.company_name,
                job.title,
                f"{score.overall_score:.2f}" if score else "-",
                score.recommendation.value if score else "-",
                f"v{resume.version}" if resume else "-",
                f"v{cover.version}" if cover else "-",
            )
        console.print(table)


@app.command()
def approve(job_id: str, note: str | None = typer.Option(None)) -> None:
    """Approve a prepared application."""
    _with_tracker(lambda t: t.approve(job_id, note=note), f"Approved {job_id}")


@app.command()
def submit(job_id: str, note: str | None = typer.Option(None)) -> None:
    """Mark an application as submitted (respects the daily cap)."""

    def action(t: ApplicationTracker) -> None:
        try:
            t.submit(job_id, note=note)
        except DailyLimitReached as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(1) from exc

    _with_tracker(action, f"Submitted {job_id}")


@app.command()
def outcome(
    job_id: str,
    result: str = typer.Argument(..., help="rejected | interview | offer | archived"),
    note: str | None = typer.Option(None),
) -> None:
    """Record a company's response to a submitted application."""
    _with_tracker(
        lambda t: t.record_outcome(job_id, result, note=note), f"Recorded {result} for {job_id}"
    )


def _with_tracker(action, success_msg: str) -> None:  # type: ignore[no-untyped-def]
    settings = get_settings()
    db = Database(settings.storage.sqlite_path)
    db.create_all()
    with db.session_scope() as session:
        tracker = ApplicationTracker(
            Repository(session), max_per_day=settings.pipeline.max_applications_per_day
        )
        action(tracker)
    console.print(f"[green]{success_msg}[/green]")
    if settings.pipeline.auto_sync_excel:
        _pipeline().sync_excel()


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
@app.command(name="sync-excel")
def sync_excel() -> None:
    """Regenerate the Excel workbook from SQLite."""
    path = _pipeline().sync_excel()
    console.print(f"[green]Synced[/green] -> {path}")


@app.command()
def stats() -> None:
    """Print pipeline analytics."""
    s = _pipeline().stats()
    table = Table(title="Analytics")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    for key, value in s.as_rows():
        table.add_row(str(key), str(value))
    console.print(table)


@app.command(name="init-db")
def init_db() -> None:
    """Create the database schema and required directories."""
    settings = get_settings()
    settings.ensure_directories()
    Database(settings.storage.sqlite_path).create_all()
    console.print("[green]Database initialized.[/green]")


@app.command()
def boards() -> None:
    """List available job boards."""
    console.print(", ".join(available_boards()))


@app.command()
def dashboard(
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8000),
) -> None:
    """Launch the local web dashboard (requires the 'dashboard' extra)."""
    try:
        import uvicorn
    except ImportError:
        console.print("[red]Install the dashboard extra:[/red] pip install -e '.[dashboard]'")
        raise typer.Exit(1) from None
    from job_agent.dashboard.app import create_app

    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":  # pragma: no cover
    app()
