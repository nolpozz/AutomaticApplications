#!/usr/bin/env python3
"""Re-score an already-classified database with the current boosts and domain gate.

Re-applies the configured domain-relevance penalty and location/keyword boosts
(settings.pipeline.*) to every job that already has a classifier score — NO LLM
calls, no re-scraping, no document regeneration. Each job's *base* (pre-adjust)
score is remembered in job.raw["base_score"], so this is idempotent and safe to
run repeatedly after tuning the values.

Side effects on state (so `job-agent review` reflects the new scores):
  * previously-PASSED jobs pushed below threshold (e.g. off-domain generic SWE
    roles) are ARCHIVED — their documents stay on disk but they leave the review
    queue. See them with `job-agent review --state ARCHIVED`.
  * previously-REJECTED jobs lifted over threshold are reported so you can review
    them (`job-agent review --state REJECTED`) and decide case by case.

Usage:
    python3 scripts/rescore.py    # re-score, archive off-domain, re-rank Excel
"""

from __future__ import annotations

from job_agent.classifier.boost import ScoreBoost
from job_agent.classifier.classifier import _recommend, domain_text
from job_agent.classifier.domain import DomainFilter
from job_agent.classifier.prestige import CompanyPrestige
from job_agent.classifier.targeting import LevelTargeting, job_level
from job_agent.config.settings import get_settings
from job_agent.database.base import Database
from job_agent.database.repository import Repository
from job_agent.excel.sync import ExcelSynchronizer
from job_agent.models.domain import JobState

_PASSED = {
    JobState.READY_FOR_REVIEW.value,
    JobState.READY_FOR_RESUME.value,
    JobState.RESUME_GENERATED.value,
    JobState.COVER_LETTER_GENERATED.value,
}
_NOTE_PREFIXES = ("Off-target", "Off-domain", "Location boost", "Role boost", "Prestige boost")


def main() -> None:
    settings = get_settings()
    boost = ScoreBoost.from_pipeline(settings.pipeline)
    domain = DomainFilter.from_pipeline(settings.pipeline)
    prestige = CompanyPrestige.from_pipeline(settings.pipeline)
    targeting = LevelTargeting.from_pipeline(settings.pipeline)
    thr = settings.pipeline.classifier_threshold

    if not any([boost.active, domain.active, prestige.active, targeting.active]):
        print("No active boosts, domain gate, prestige, or targeting configured. Nothing to do.")
        return

    print(
        f"Threshold={thr}  boost={boost.active}  domain={domain.active}  prestige={prestige.active}"
    )
    if domain.active:
        print(
            f"Domain penalty x{domain.penalty} when none of {len(domain.keywords)} keywords match."
        )
    print()

    db = Database(settings.storage.sqlite_path)
    changed = 0
    newly_qualifying: list[tuple[float, float, str, str, str]] = []
    archived: list[tuple[float, float, str, str]] = []

    with db.session_scope() as session:
        repo = Repository(session)
        for job in repo.list_jobs():
            score = repo.get_classifier(job.id)
            if score is None:
                continue
            raw = dict(job.raw or {})
            base = float(raw.get("base_score", score.overall_score))
            raw["base_score"] = base
            job.raw = raw  # reassign so the JSON column is marked dirty

            notes: list[str] = []
            adjusted = base
            if targeting.active:
                lf = targeting.factor(
                    level=job_level(job), title=job.title, description=job.description or ""
                )
                if lf < 1.0:
                    adjusted = round(adjusted * lf, 4)
                    notes.append(f"Off-target ({targeting.describe()}); x{lf:g}")
            if domain.active:
                factor = domain.factor(domain_text(job, repo.get_parsed(job.id)))
                if factor < 1.0:
                    adjusted = round(adjusted * factor, 4)
                    notes.append(f"Off-domain (no ML/AI signal); x{factor:g}")
            if prestige.active:
                bonus, tier = prestige.score_boost(job.company_name)
                if bonus:
                    adjusted = min(1.0, round(adjusted + bonus, 4))
                    notes.append(f"Prestige boost +{bonus:g} ({tier})")
            final, boost_notes = boost.apply(adjusted, title=job.title, location=job.location or "")
            notes += boost_notes

            if final != score.overall_score:
                score.overall_score = final
                score.recommendation = _recommend(final)
                score.interview_probability = round(final * 0.6, 4)
                score.reasons = [
                    r for r in score.reasons if not r.startswith(_NOTE_PREFIXES)
                ] + notes
                repo.save_classifier(job.id, score)
                changed += 1

            if job.state == JobState.REJECTED.value and final >= thr:
                newly_qualifying.append(
                    (base, final, job.company_name, job.title, job.location or "")
                )
            elif job.state in _PASSED and final < thr:
                archived.append((base, final, job.company_name, job.title))
                repo.set_state(job, JobState.ARCHIVED)  # off-domain; leaves review queue

        # Re-rank the workbook so boosted roles float up and archived ones drop out.
        ExcelSynchronizer(repo, settings.storage.excel_path).sync()

    print(f"Re-scored {changed} job(s).\n")

    archived.sort()
    print(f"{len(archived)} previously-PASSED job(s) ARCHIVED (dropped below {thr}):")
    for base, final, comp, title in archived[:40]:
        print(f"  {base:.2f} -> {final:.2f}  {comp} — {title}")

    newly_qualifying.sort(reverse=True)
    print(f"\n{len(newly_qualifying)} previously-REJECTED job(s) now cross {thr}:")
    for base, final, comp, title, loc in newly_qualifying[:40]:
        tag = f"  [{loc}]" if loc else ""
        print(f"  {base:.2f} -> {final:.2f}  {comp} — {title}{tag}")


if __name__ == "__main__":
    main()
