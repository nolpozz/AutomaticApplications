# job-agent

An AI-powered pipeline that **discovers** ML / AI research / AI engineering / NLP /
data-science jobs, **decides** whether they fit your background, **generates**
tailored resumes and cover letters, and **tracks** every application — architected
like a product, not a pile of scripts.

* **SQLite is the single source of truth.** Excel is a generated projection, never read back.
* **Every stage is resumable**, every artifact is stored, every LLM prompt is versioned.
* **Runs with zero API keys** out of the box (deterministic mock LLM + mock embeddings).
  Add an API key to switch on real generation — nothing else changes.
* **Your personal data never leaves your machine** (`user_data/`, `data/`, `.env` are gitignored).

---

## What's implemented

**Job discovery (live scrapers).** A common abstract scraper interface with many
concrete adapters, all emitting normalized `Job` objects and recording the real
per-posting URL:

| Source | Status | How it works |
|---|---|---|
| **GitHub aggregator repos** | ✅ live | Parses the big community internship lists (SimplifyJobs, speedyapply, vanshb03…) in both Markdown- and HTML-table formats; extracts the direct posting URL from each "Apply" badge, handles `↳` company continuation, skips closed roles |
| **Amazon** | ✅ live | `amazon.jobs` search JSON API |
| **Netflix** | ✅ live | Eightfold public API (`canonicalPositionUrl`) |
| **Google** | ✅ live | Careers results page → per-job `og:title` |
| **Spotify** | ✅ live | Scrapes `engineering.atspotify.com/jobs` posting links |
| **Greenhouse / Lever / Ashby** | ✅ live | Public board APIs (e.g. Anthropic, OpenAI) |
| **Workday** | ✅ live | CxS JSON API (e.g. NVIDIA) |
| **YC / Wellfound / LinkedIn** | ⚠️ sample | No free public API / ToS-restricted; sample data by default |
| **Company career pages** | ⚠️ partial | Auto-delegates to Greenhouse/Lever/Ashby when detected |

**Centralized ML/AI search.** One `search_queries` list (covering ML engineer, AI
research, research scientist, applied scientist, NLP, LLMs, computer vision, deep
learning, MLOps, internships, …) drives every search-based board, so the full
ML/AI research + engineering role space is searched from one place.

**LLM layer.** Provider abstraction over **OpenAI (default)**, Anthropic, Gemini,
Ollama/vLLM, and a deterministic **mock**. Every AI component supplies a
deterministic fallback, so the pipeline runs and tests reproducibly with no keys,
and real-provider parse failures degrade gracefully. Prompts are versioned files.

**LLM-based parsing & reproducible classifier.** Extracts structured requirements
from each posting; scores fit across technical / experience / education / research /
interest with an overall score, recommendation, and reasons. Supports **role
targeting** (e.g. prioritize Master's-level internships, down-weight senior
full-time roles).

**Retrieval + tailored documents.** Embeddings (mock hashed or
sentence-transformers) over your knowledge base with SQLite/FAISS vector search;
job-conditioned retrieval passes only relevant, real material to the generators.
Resumes and cover letters are produced in Markdown (+ DOCX/PDF with the extra),
never inventing experience.

**Narrative-block cover letters.** Assembles cover letters from your own tagged,
pre-written paragraphs — picking one opening, the best-matching body blocks, and a
closing for each job — with the single company-specific hook sentence written fresh
by the LLM every time.

**Orchestration & tracking.** A resumable state-machine pipeline (per-job commits);
an application tracker for the human-in-the-loop review → approve → submit → outcome
flow with a daily-submission cap; deduplication across URL, company/title, and
semantics.

**Surfaces.** A typer CLI, a local FastAPI dashboard (search / filter / charts), an
auto-synced Excel workbook (colored by stage, frozen headers, autofilter), analytics,
and rotating structured logs. Full test suite (**68 tests**), `ruff` / `black` /
`mypy` clean, GitHub Actions CI on Python 3.10–3.12.

---

## Download & install

```bash
git clone https://github.com/nolpozz/AutomaticApplications.git
cd AutomaticApplications

python -m venv .venv && source .venv/bin/activate      # Python 3.10+ (targets 3.12)

pip install -r requirements.txt   # core deps — pipeline is fully runnable with just these
pip install -e .                  # exposes the `job-agent` command
```

Optional capability bundles:

```bash
pip install -e ".[providers]"     # OpenAI / Anthropic / Gemini SDKs (real generation)
pip install -e ".[documents]"     # DOCX + PDF output
pip install -e ".[embeddings]"    # real semantic embeddings (sentence-transformers, FAISS)
pip install -e ".[dashboard]"     # FastAPI web dashboard
pip install -e ".[dev]"           # pytest, ruff, black, mypy, pre-commit
pip install -e ".[all]"           # everything above
```

---

## Use it

### 1. Add your background (private)

```bash
scripts/seed_user_data.sh          # copies the sample persona into user_data/
$EDITOR user_data/profile.yaml     # then edit the category folders with your own info
```

`user_data/` is gitignored — your real résumé content is never committed. See
`user_data.example/` for the expected shape (Markdown/YAML across `experience/`,
`projects/`, `education/`, `skills/`, `publications/`, `resume_bullets/`,
`cover_letter_examples/`, and an optional `narrative_blocks.md`).

### 2. Try it offline (no keys)

```bash
job-agent pipeline                 # offline by default: mock LLM + sample jobs, no keys/cost
job-agent review                   # ranked queue with fit scores
job-agent stats                    # analytics
open data/job_agent.xlsx           # the synced workbook
```

Generated résumés/cover letters land in `data/documents/`. `job-agent pipeline`
defaults to `--offline` (deterministic sample data); add `--no-offline` to hit
real boards.

### 3. Go live (real models + real jobs)

```bash
cp .env.example .env
```

```ini
# .env
JOB_AGENT_LLM__PROVIDER=openai
JOB_AGENT_LLM__MODEL=gpt-4o
OPENAI_API_KEY=sk-...
```

Review/edit the job sources in **`config/sources.yaml`** (board tokens for
Greenhouse/Lever/Ashby; FAANG search boards work out of the box), then:

```bash
job-agent pipeline --no-offline    # hit real boards and a real model
```

### 4. Apply and track

**What a run produces.** After `job-agent pipeline --no-offline`, every discovered
job is embedded and ranked, then only the **top 5 most-relevant roles per company**
(`PIPELINE__TOP_PER_COMPANY=5`; the rest are marked `DEPRIORITIZED` and skipped)
advance to the expensive stages. Those survivors are parsed and classified, and the
classifier **rejects** anything below `PIPELINE__CLASSIFIER_THRESHOLD` (e.g. a senior
full-time role that slipped through ranking). **Only the roles that pass classification
get a tailored résumé + cover letter** — so you end up with *up to* 5 prepared
applications per company, minus whatever the classifier drops, waiting in
`data/documents/`.

**The apply loop is human-in-the-loop — the tool prepares and tracks; you submit.**
None of the commands below touch an employer's website; they move a job through its
lifecycle in your local database so nothing gets lost and you stay under your daily cap.

```bash
job-agent review                   # your worklist: jobs in READY_FOR_REVIEW with
                                   #   fit score, recommendation, and doc versions.
                                   #   Read-only. Same data as the Excel Jobs sheet
                                   #   (which also has the posting URL + relevance).
                                   #   Try --state DEPRIORITIZED or --state REJECTED
                                   #   to see what got capped or dropped.
```
For each job you want to pursue:
1. Open its tailored `data/documents/<company>-<role>-<id>.{pdf,docx,md}` and **read/edit** them.
2. `job-agent approve <job_id>` — your "yes, applying to this" gate (`READY_FOR_REVIEW → APPROVED`; optional `--note`).
3. Go to the posting **URL**, fill out the application, and upload the generated docs — **the only manual web step.**
4. `job-agent submit <job_id>` — logs the submission (`APPROVED → SUBMITTED`), timestamps it, enforces `MAX_APPLICATIONS_PER_DAY`.
5. `job-agent outcome <job_id> interview` — later, as you hear back, for your analytics.

> The tool does **not** auto-fill employer forms (see the roadmap). Always read a
> generated document before sending it.

---

## CLI

| Command | What it does |
|---|---|
| `job-agent pipeline [--no-offline]` | Full flow: scrape → parse → embed → classify → resume → cover letter |
| `job-agent scrape / parse / embed / classify` | Run a single stage over pending jobs |
| `job-agent generate-resume / generate-cover-letter` | Generate documents for eligible jobs |
| `job-agent review [--state STATE]` | List jobs at a stage (default: awaiting review) |
| `job-agent approve / submit / outcome <job_id>` | Move an application through its lifecycle |
| `job-agent sync-excel` | Rebuild the Excel workbook from SQLite |
| `job-agent stats` | Print analytics |
| `job-agent dashboard` | Launch the local web dashboard (needs the `dashboard` extra) |
| `job-agent boards` | List available job boards |

Automated stages are resumable — re-running only processes jobs that still need
that stage; a job that fails a stage stays put and is retried next run.

---

## How it fits together

```
 boards ──> Scrapers ──> [Job] ──> Dedupe ──> SQLite (source of truth)
                                                   │
   ┌───────────────────────────────────────────────┤  Orchestrator (state machine)
   ▼            ▼            ▼             ▼          ▼
 Parser ──> Embeddings ──> Classifier ──> Retrieval ──> Resume + Cover-letter gens
 (LLM)       (vectors)      (LLM, fit)     (top-k)        (LLM, real material only)
                                                   │
                                                   ▼
                              Excel sync · Analytics · Dashboard · Tracker
```

See [`docs/architecture.md`](docs/architecture.md) for the full design,
[`docs/setup.md`](docs/setup.md) for configuration,
[`docs/extending.md`](docs/extending.md) to add a board/provider/prompt, and
[`docs/troubleshooting.md`](docs/troubleshooting.md).

---

## Privacy

Nothing personal is ever pushed to GitHub:

* `user_data/` — your real background — is gitignored (only the fictional
  `user_data.example/` template is tracked).
* `data/` — generated résumés, cover letters, the SQLite DB, and Excel — is gitignored.
* `.env` — API keys — is gitignored.

---

## Roadmap — future features needed

* **Automated submission (Playwright).** Drive employer application forms end-to-end,
  consuming the stored résumé/cover-letter files. The tracker's `submit` step and the
  `Job.url` are already in place as the integration point.
* **More live board adapters.** Meta, Apple, and Microsoft run custom career sites
  with no clean public API and currently need per-site adapters (their roles do show
  up via the GitHub aggregators). Add LinkedIn via an authorized API.
* **Email automation & recruiter tracking.** Detect responses, log recruiter threads,
  and update application state from your inbox.
* **Interview scheduling** hooked to the `applications` table and outcomes.
* **Salary prediction & company scoring** (fields already reserved: `companies.score`).
* **Résumé A/B testing** using the first-class version history (`resume_versions`).
* **Learning from outcomes.** Feed recorded interview/offer results and response times
  back into classifier calibration.
* **Richer dashboard.** Editable notes, one-click approve/submit, and document preview.
* **Multi-user / cloud deployment.** The repository is the only DB touchpoint; add a
  tenant key and swap SQLite for Postgres.
* **Fine-tuned classifier** to replace the heuristic/LLM scorer over time.

---

## Development

```bash
pip install -e ".[dev]"
pytest                       # unit + integration tests
ruff check job_agent tests
black --check job_agent tests
mypy job_agent
pre-commit install           # run the above automatically on commit
```

Targets Python 3.12; supports 3.10+.

## License

MIT
