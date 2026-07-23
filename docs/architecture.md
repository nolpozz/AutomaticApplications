# Architecture

## Principles

1. **SQLite is the single source of truth.** Every fact about jobs, scores,
   documents, and applications lives in the database. Excel is regenerated *from*
   it and never read back.
2. **Components communicate only through typed interfaces and database records.**
   No component writes another's files or tables; all writes go through the
   `Repository`, which also writes an audit log for every modification.
3. **Every stage is resumable.** State lives on the `jobs.state` column; a stage
   only picks up jobs in its expected state, so re-running continues where it
   left off and failures are retried.
4. **Every artifact is stored** (parsed JSON, scores, resume/cover versions, and
   a `documents` registry of files on disk).
5. **Every LLM prompt is versioned** (`name.vN`), and the version is stored on
   the artifact it produced.

## Layered view

```
        ┌──────────────────────────── CLI (typer) ────────────────────────────┐
        │  pipeline · scrape · parse · classify · generate-* · review · stats  │
        └───────────────────────────────┬─────────────────────────────────────┘
                                         │
                         ┌───────────────▼───────────────┐
                         │   Orchestrator (Pipeline)      │   state machine
                         │   builds a PipelineContext     │   + resumability
                         └───┬───────┬───────┬───────┬────┘
             ┌───────────────┘       │       │       └───────────────┐
        ┌────▼────┐   ┌──────────┐   │   ┌───▼──────┐         ┌───────▼────────┐
        │Scrapers │   │ Parser   │   │   │Classifier│         │ Resume / Cover │
        │(boards) │   │ (LLM)    │   │   │ (LLM)    │         │ (LLM)          │
        └────┬────┘   └────┬─────┘   │   └────┬─────┘         └───────┬────────┘
             │             │         │        │                       │
        ┌────▼─────────────▼─────────▼────────▼───────────────────────▼───────┐
        │                     Repository  (all reads/writes + audit log)       │
        └──────────────────────────────┬───────────────────────────────────────┘
                                        ▼
                                 SQLite database
                                        │
             ┌──────────────────────────┼───────────────────────────┐
             ▼                          ▼                           ▼
       Excel synchronizer         Analytics                    Dashboard
```

Cross-cutting services: **LLM layer** (provider abstraction + versioned prompts),
**Embeddings** (provider + vector store), **Knowledge base** (loads `user_data/`),
**Retrieval** (job-conditioned top-k over the knowledge base).

## The state machine

```
DISCOVERED → EMBEDDED → PARSED → CLASSIFIED ─┬→ READY_FOR_RESUME → RESUME_GENERATED
                 │                           │        → COVER_LETTER_GENERATED
                 └→ DEPRIORITIZED → PARSED   │        → READY_FOR_REVIEW
                                             └→ REJECTED
READY_FOR_REVIEW → APPROVED → SUBMITTED ─┬→ INTERVIEW → OFFER
                                         ├→ REJECTED_BY_COMPANY
                                         └→ (any) → ARCHIVED
```

Jobs are **embedded and ranked cheaply first**; only the top-N per company advance
to the expensive `PARSED`/`CLASSIFIED` LLM stages, and the rest are `DEPRIORITIZED`
(a prestigious company keeps `top_per_company × prestige_cap_multiplier` roles — see
below). The orchestrator drives the automated portion (`DISCOVERED …
COVER_LETTER_GENERATED` → `READY_FOR_REVIEW`). The **tracker** owns the
human-in-the-loop transitions (`APPROVED`, `SUBMITTED`, outcomes). `ARCHIVED` is
reachable from any state (used by `scripts/rescore.py` to drop roles that fall below
threshold after re-tuning). Allowed transitions live in
`job_agent/orchestrator/states.py`.

## The scoring pipeline

`classifier/classifier.py` first obtains five **dimension ratings on a 1-100 scale**
— technical, experience, education, research, interest — from the LLM (via the
`classify_job` prompt) or the deterministic heuristic fallback. Crucially the model
returns *only* those ratings; `_coerce` normalizes them to [0, 1] and `_weighted_overall`
applies `_WEIGHTS` to compute the base `overall_score`. This is the single place the
overall is computed, so the weighting is identical for every provider and a user's
preference weights always apply (the mock/heuristic path emits the same 1-100 wire
shape, so both paths flow through one weighting funnel). `_finalize` then runs the
base score through a chain of deterministic, configurable adjustments — each in its
own module under `classifier/` and each built `from_pipeline(settings.pipeline)` so
it is off unless configured:

```
base_score
  × LevelTargeting.factor   (targeting.py — penalize off-target level/keywords)
  × DomainFilter.factor     (domain.py    — penalize roles with no domain keywords)
  + CompanyPrestige.boost   (prestige.py  — FAANG+/high-growth tier bonus)
  + ScoreBoost.apply        (boost.py     — capped location/title-keyword bonuses)
  = overall_score  (clamped to [0,1]; drives recommendation + interview_probability)
```

Multipliers come first so an off-target/off-domain role cannot be lifted over the
threshold by an additive boost. The pre-adjustment value is stored as
`ClassifierScore.base_score` (and mirrored into `jobs.raw["base_score"]`) so the
whole chain can be **recomputed from a stable base** — that is exactly what
`scripts/rescore.py` does, re-ranking an already-classified database with no LLM
calls after you change the settings. A `CompanyBlocklist` (`scrapers/blocklist.py`)
short-circuits this entirely by dropping blocked employers at scrape time.

## The LLM abstraction and deterministic fallbacks

Every AI component calls `llm.complete_json(...)` / `complete_text(...)` with a
`fallback` callable that computes the same result deterministically from the same
inputs. Consequences:

* **Mock provider** returns the fallback directly → the whole pipeline runs with
  no API keys, and tests are reproducible.
* **Real providers** use the fallback only when the model returns unparseable
  output → graceful degradation.
* The component's heuristic *is* both the mock behavior and the safety net, so
  there's exactly one deterministic implementation to reason about.

## Data model (tables)

`companies`, `job_sources`, `jobs`, `parsed_jobs`, `classifier_scores`,
`resume_versions`, `cover_letter_versions`, `applications`, `documents`,
`embeddings`, `logs`. All use UUID string primary keys and carry
`created_at`/`updated_at`.

## Why not LangGraph?

The pipeline is a small, explicit state machine with per-job commits for
resumability — a hand-written orchestrator keeps it dependency-light and easy to
reason about. LangGraph is available as an optional `orchestration` extra if you
want to swap it in; the stage functions are already pure `(ctx, job) -> None`
steps that map cleanly onto graph nodes.
