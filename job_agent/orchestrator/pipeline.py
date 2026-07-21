"""The orchestrator: builds every component and drives jobs through the states.

One :class:`Pipeline` owns the session-independent pieces (knowledge base, LLM,
prompts, renderer). For each unit of work it opens a session and builds a
:class:`PipelineContext` of session-bound components. Progress is committed after
every job, so a crash never loses completed work and the next run resumes
cleanly (each stage only picks up jobs in its expected state).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from job_agent.analytics.analytics import Analytics, Stats
from job_agent.classifier.classifier import JobClassifier
from job_agent.config.logging import get_logger
from job_agent.config.settings import Settings, get_settings
from job_agent.cover_letter.blocks import load_blocks
from job_agent.cover_letter.generator import CoverLetterGenerator
from job_agent.database.base import Database
from job_agent.database.models import JobRecord
from job_agent.database.repository import Repository
from job_agent.dedupe.detector import DuplicateDetector
from job_agent.documents.render import DocumentRenderer
from job_agent.embeddings.service import EmbeddingService
from job_agent.excel.sync import ExcelSynchronizer
from job_agent.knowledge.loader import KnowledgeBase, load_knowledge_base
from job_agent.llm.factory import build_llm
from job_agent.llm.prompts import get_prompt_registry
from job_agent.models.domain import (
    EmploymentType,
    ExperienceLevel,
    Job,
    JobState,
    ParsedJob,
    RemoteType,
)
from job_agent.parser.llm_parser import JobParser
from job_agent.resume.generator import ResumeGenerator
from job_agent.retrieval.retriever import Retriever
from job_agent.tracker.tracker import ApplicationTracker

logger = get_logger(__name__)


@dataclass
class PipelineContext:
    settings: Settings
    repo: Repository
    kb: KnowledgeBase
    embeddings: EmbeddingService
    retriever: Retriever
    parser: JobParser
    classifier: JobClassifier
    resume: ResumeGenerator
    cover: CoverLetterGenerator
    dedupe: DuplicateDetector
    tracker: ApplicationTracker


@dataclass
class RunReport:
    scraped: int = 0
    new: int = 0
    duplicates: int = 0
    parsed: int = 0
    embedded: int = 0
    classified: int = 0
    rejected: int = 0
    resumes: int = 0
    cover_letters: int = 0
    ready_for_review: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"scraped={self.scraped} new={self.new} dup={self.duplicates} "
            f"parsed={self.parsed} classified={self.classified} rejected={self.rejected} "
            f"resumes={self.resumes} cover_letters={self.cover_letters} "
            f"ready={self.ready_for_review} errors={len(self.errors)}"
        )


class Pipeline:
    def __init__(
        self, settings: Settings | None = None, *, formats: list[str] | None = None
    ) -> None:
        self.settings = settings or get_settings()
        self.settings.ensure_directories()
        self.db = Database(self.settings.storage.sqlite_path)
        self.db.create_all()
        self.kb = load_knowledge_base(self.settings.storage.user_data_path)
        self.llm = build_llm(self.settings)
        self.prompts = get_prompt_registry(self.settings.storage.prompts_path)
        self.renderer = DocumentRenderer(self.settings.storage.documents_path)
        self.formats = formats or ["md", "docx", "pdf"]
        # Load the user's narrative blocks for cover-letter assembly (optional).
        self.cover_blocks = load_blocks(
            self.settings.storage.user_data_path / "narrative_blocks.md"
        )

    # -- context ------------------------------------------------------------
    def context(self, session: Session) -> PipelineContext:
        repo = Repository(session)
        emb = EmbeddingService.from_settings(self.settings, repo)
        templates = self.settings.storage.templates_path
        return PipelineContext(
            settings=self.settings,
            repo=repo,
            kb=self.kb,
            embeddings=emb,
            retriever=Retriever(emb, self.kb),
            parser=JobParser(self.llm, self.prompts),
            classifier=JobClassifier(
                self.llm,
                self.prompts,
                self.kb,
                target_levels=self.settings.pipeline.target_experience_levels,
                target_keywords=self.settings.pipeline.target_keywords,
                target_description=self.settings.pipeline.target_description,
            ),
            resume=ResumeGenerator(self.llm, self.prompts, self.renderer, templates),
            cover=CoverLetterGenerator(
                self.llm, self.prompts, self.renderer, templates, blocks=self.cover_blocks
            ),
            dedupe=DuplicateDetector(
                repo, emb, similarity_threshold=self.settings.pipeline.dedup_similarity_threshold
            ),
            tracker=ApplicationTracker(
                repo, max_per_day=self.settings.pipeline.max_applications_per_day
            ),
        )

    def _ensure_knowledge_indexed(self, ctx: PipelineContext) -> None:
        if not ctx.repo.list_embeddings("knowledge"):
            ctx.embeddings.index_knowledge(self.kb)

    # -- public stage entrypoints (each manages its own session) ------------
    def scrape(self, *, boards: list[str] | None = None, offline: bool | None = None) -> RunReport:
        report = RunReport()
        with self.db.session_scope() as session:
            ctx = self.context(session)
            self._scrape_into(ctx, report, boards=boards, offline=offline)
        self._maybe_sync_excel()
        return report

    def parse_pending(self) -> RunReport:
        return self._run_stage(JobState.DISCOVERED, self._parse_job, "parsed")

    def embed_pending(self) -> RunReport:
        return self._run_stage(JobState.PARSED, self._embed_job, "embedded")

    def classify_pending(self) -> RunReport:
        return self._run_stage(JobState.EMBEDDED, self._classify_job, "classified")

    def generate_resumes(self) -> RunReport:
        return self._run_stage(JobState.READY_FOR_RESUME, self._resume_job, "resumes")

    def generate_cover_letters(self) -> RunReport:
        return self._run_stage(JobState.RESUME_GENERATED, self._cover_job, "cover_letters")

    def run(
        self,
        *,
        boards: list[str] | None = None,
        offline: bool | None = None,
        resume_after_failure: bool = True,
    ) -> RunReport:
        """Run the full automated pipeline end to end."""
        report = RunReport()
        with self.db.session_scope() as session:
            ctx = self.context(session)
            self._ensure_knowledge_indexed(ctx)
            self._scrape_into(ctx, report, boards=boards, offline=offline)
            session.commit()
            stages: list[tuple[JobState, Callable[[PipelineContext, JobRecord], None], str]] = [
                (JobState.DISCOVERED, self._parse_job, "parsed"),
                (JobState.PARSED, self._embed_job, "embedded"),
                (JobState.EMBEDDED, self._classify_job, "classified"),
                (JobState.READY_FOR_RESUME, self._resume_job, "resumes"),
                (JobState.RESUME_GENERATED, self._cover_job, "cover_letters"),
            ]
            for state, fn, counter in stages:
                self._drain(ctx, session, state, fn, counter, report, resume_after_failure)
            report.rejected = ctx.repo.count_jobs_by_state().get(JobState.REJECTED.value, 0)
            report.ready_for_review = ctx.repo.count_jobs_by_state().get(
                JobState.READY_FOR_REVIEW.value, 0
            )
        self._maybe_sync_excel()
        logger.info("Pipeline run complete: %s", report.summary())
        return report

    def sync_excel(self) -> str:
        with self.db.session_scope() as session:
            path = ExcelSynchronizer(Repository(session), self.settings.storage.excel_path).sync()
        return str(path)

    def stats(self) -> Stats:
        with self.db.session_scope() as session:
            return Analytics(Repository(session)).compute()

    # -- scraping -----------------------------------------------------------
    def _scrape_into(
        self,
        ctx: PipelineContext,
        report: RunReport,
        *,
        boards: list[str] | None,
        offline: bool | None,
    ) -> None:
        from job_agent.scrapers.registry import build_scrapers

        scrapers = build_scrapers(self.settings, only=boards, offline=offline)
        limit = self.settings.pipeline.max_jobs
        for scraper in scrapers:
            for job in scraper.fetch():
                report.scraped += 1
                match = ctx.dedupe.find_duplicate(job)
                if match is not None:
                    report.duplicates += 1
                    continue
                ctx.repo.add_job(job)
                report.new += 1
                if report.new >= limit:
                    logger.info("Reached max_jobs=%d; stopping scrape", limit)
                    return

    # -- stage runners ------------------------------------------------------
    def _run_stage(
        self, state: JobState, fn: Callable[[PipelineContext, JobRecord], None], counter: str
    ) -> RunReport:
        report = RunReport()
        with self.db.session_scope() as session:
            ctx = self.context(session)
            self._ensure_knowledge_indexed(ctx)
            self._drain(ctx, session, state, fn, counter, report, resume_after_failure=True)
        self._maybe_sync_excel()
        return report

    def _drain(
        self,
        ctx: PipelineContext,
        session: Session,
        state: JobState,
        fn: Callable[[PipelineContext, JobRecord], None],
        counter: str,
        report: RunReport,
        resume_after_failure: bool,
    ) -> None:
        for job in ctx.repo.list_jobs(state=state):
            try:
                fn(ctx, job)
                setattr(report, counter, getattr(report, counter) + 1)
                session.commit()
            except Exception as exc:
                session.rollback()
                msg = f"{state.value} stage failed for job {job.id}: {exc}"
                logger.exception(msg)
                report.errors.append(msg)
                # Record the error on the job without advancing its state.
                fresh = ctx.repo.get_job(job.id)
                if fresh is not None:
                    fresh.error = str(exc)
                    session.commit()
                if not resume_after_failure:
                    raise

    # -- per-job stage implementations --------------------------------------
    def _parse_job(self, ctx: PipelineContext, job: JobRecord) -> None:
        domain = _to_domain(job)
        parsed, version = ctx.parser.parse(domain)
        ctx.repo.save_parsed(job.id, parsed, version)
        ctx.repo.set_state(job, JobState.PARSED)

    def _embed_job(self, ctx: PipelineContext, job: JobRecord) -> None:
        ctx.embeddings.index_job(_to_domain(job))
        ctx.repo.set_state(job, JobState.EMBEDDED)

    def _classify_job(self, ctx: PipelineContext, job: JobRecord) -> None:
        parsed = ctx.repo.get_parsed(job.id) or ParsedJob()
        score, version = ctx.classifier.classify(_to_domain(job), parsed)
        ctx.repo.save_classifier(job.id, score, version)
        ctx.repo.set_state(job, JobState.CLASSIFIED)
        if score.passes(self.settings.pipeline.classifier_threshold):
            ctx.repo.set_state(job, JobState.READY_FOR_RESUME)
        else:
            ctx.repo.set_state(job, JobState.REJECTED)

    def _resume_job(self, ctx: PipelineContext, job: JobRecord) -> None:
        self._ensure_knowledge_indexed(ctx)
        domain = _to_domain(job)
        parsed = ctx.repo.get_parsed(job.id) or ParsedJob()
        retrieved = ctx.retriever.retrieve(domain, parsed)
        doc = ctx.resume.generate(domain, parsed, retrieved, self.kb.profile, formats=self.formats)
        ctx.repo.add_resume_version(doc)
        self._register_documents(ctx, job.id, "resume", doc.paths)
        ctx.repo.set_state(job, JobState.RESUME_GENERATED)

    def _cover_job(self, ctx: PipelineContext, job: JobRecord) -> None:
        self._ensure_knowledge_indexed(ctx)
        domain = _to_domain(job)
        parsed = ctx.repo.get_parsed(job.id) or ParsedJob()
        retrieved = ctx.retriever.retrieve(domain, parsed)
        doc = ctx.cover.generate(domain, parsed, retrieved, self.kb, formats=self.formats)
        rec = ctx.repo.add_cover_letter_version(doc)
        self._register_documents(ctx, job.id, "cover_letter", doc.paths)
        ctx.repo.set_state(job, JobState.COVER_LETTER_GENERATED)

        # Hand off to human review: create the application record.
        resume = ctx.repo.latest_resume(job.id)
        ctx.repo.upsert_application(
            job.id,
            status="prepared",
            stage=JobState.READY_FOR_REVIEW.value,
            resume_version_id=resume.id if resume else None,
            cover_letter_version_id=rec.id,
        )
        ctx.repo.set_state(job, JobState.READY_FOR_REVIEW)

    def _register_documents(
        self, ctx: PipelineContext, job_id: str, kind: str, paths: dict[str, str]
    ) -> None:
        for fmt, path in paths.items():
            ctx.repo.add_document(job_id=job_id, kind=kind, fmt=fmt, path=path)

    def _maybe_sync_excel(self) -> None:
        if self.settings.pipeline.auto_sync_excel:
            try:
                self.sync_excel()
            except Exception as exc:
                logger.warning("Excel auto-sync failed: %s", exc)


def _to_domain(record: JobRecord) -> Job:
    """Reconstruct a domain Job from its ORM record."""
    return Job(
        id=record.id,
        title=record.title,
        company=record.company_name,
        description=record.description,
        location=record.location,
        salary=record.salary,
        employment_type=_enum(EmploymentType, record.employment_type),
        experience_level=_enum(ExperienceLevel, record.experience_level),
        remote=_enum(RemoteType, record.remote),
        visa_sponsorship=record.visa_sponsorship,
        url=record.url,
        date_posted=record.date_posted,
        source=record.source,
        external_id=record.external_id,
        raw=record.raw or {},
    )


def _enum(enum_cls, value):  # type: ignore[no-untyped-def]
    try:
        return enum_cls(value)
    except ValueError:
        return enum_cls.UNKNOWN
