# job-agent

An AI-powered pipeline that **discovers** software / ML / AI / NLP / data-science
jobs, **decides** whether they fit your background, **generates** tailored resumes
and cover letters, and **tracks** every application — architected like a product,
not a pile of scripts.

* **SQLite is the single source of truth.** Excel is a generated projection, never
  read back.
* **Every stage is resumable**, every artifact is stored, every LLM prompt is
  versioned.
* **Runs with zero API keys** out of the box (deterministic mock LLM + mock
  embeddings). Add keys to switch on real providers — nothing else changes.

---

## Quickstart

```bash
# 1. Install (core deps only — the pipeline is fully runnable with just these)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .            # exposes the `job-agent` command

# 2. (optional) configure — defaults work out of the box
cp .env.example .env

# 3. Put your background in user_data/ (sample data ships so you can run now)

# 4. Run the whole pipeline end-to-end (offline sample data, mock LLM)
job-agent pipeline

# 5. See what it produced
job-agent review          # jobs awaiting your review, with fit scores
job-agent stats           # analytics
open data/job_agent.xlsx  # the synced workbook
```

Generated resumes and cover letters land in `data/documents/`. The full run
touches no network and needs no credentials.

### Turn on real models / boards

```bash
# .env
JOB_AGENT_LLM__PROVIDER=anthropic
JOB_AGENT_LLM__MODEL=claude-opus-4-8
ANTHROPIC_API_KEY=sk-ant-...

JOB_AGENT_EMBEDDING__PROVIDER=sentence-transformers   # needs the 'embeddings' extra
```

```bash
pip install -e ".[all]"   # real embeddings, DOCX/PDF, provider SDKs, dashboard
```

Configure real job boards in `config/sources.yaml` (add a Greenhouse/Lever/Ashby
board token), then `job-agent pipeline --no-offline`.

---

## CLI

| Command | What it does |
|---|---|
| `job-agent pipeline` | Run the full automated flow: scrape → parse → embed → classify → resume → cover letter |
| `job-agent scrape` | Discover jobs from enabled boards |
| `job-agent parse` / `embed` / `classify` | Run a single stage over pending jobs |
| `job-agent generate-resume` / `generate-cover-letter` | Generate documents for eligible jobs |
| `job-agent review [--state STATE]` | List jobs at a stage (default: awaiting review) |
| `job-agent approve/submit/outcome <job_id>` | Move an application through review → submitted → outcome |
| `job-agent sync-excel` | Rebuild the Excel workbook from SQLite |
| `job-agent stats` | Print analytics |
| `job-agent dashboard` | Launch the local web dashboard (needs the `dashboard` extra) |
| `job-agent boards` | List available job boards |

Every automated stage is resumable — re-running only processes jobs that still
need that stage, and a job that fails a stage stays put and is retried next run.

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

The **LLM layer** is a provider abstraction (OpenAI / Anthropic / Gemini / Ollama /
mock). Each AI component supplies a *deterministic fallback*, so mock-mode and
tests are reproducible and real-provider parse failures degrade gracefully.

See [`docs/architecture.md`](docs/architecture.md) for the full design,
[`docs/setup.md`](docs/setup.md) to get running, [`docs/extending.md`](docs/extending.md)
to add a board/provider/prompt, and [`docs/troubleshooting.md`](docs/troubleshooting.md).

---

## Your data lives in `user_data/` (private, never pushed)

No resume content is hardcoded anywhere. The agent knows only what you put here:

```
user_data/                # gitignored — your real background, never committed
  profile.yaml            # name, contact, headline, summary, motivation
  experience/  projects/  education/  skills/  awards/
  coursework/  certifications/  publications/
  resume_bullets/  cover_letter_examples/
```

Files are Markdown or YAML. A safe, fictional sample ships as **`user_data.example/`**
(committed). Seed your private copy from it, then edit:

```bash
scripts/seed_user_data.sh      # copies user_data.example/ -> user_data/
```

**Nothing personal is ever pushed to GitHub.** `user_data/` (your background),
`data/` (the generated résumés, cover letters, SQLite DB, and Excel), and `.env`
(API keys) are all gitignored. Only the fictional `user_data.example/` template is
tracked.

---

## Development

```bash
pip install -e ".[dev]"
pytest                 # unit + integration tests
ruff check job_agent tests
black --check job_agent tests
mypy job_agent
pre-commit install     # run the above automatically on commit
```

The project targets Python 3.12 and supports 3.10+.

## License

MIT
