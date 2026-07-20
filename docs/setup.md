# Setup

## Requirements

* Python 3.10+ (project targets 3.12)
* No external services required for the default (mock) configuration

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .              # exposes the `job-agent` console command
```

Optional capability bundles:

```bash
pip install -e ".[embeddings]"   # real semantic embeddings (sentence-transformers, faiss)
pip install -e ".[documents]"    # DOCX + PDF output (python-docx, weasyprint)
pip install -e ".[providers]"    # OpenAI / Anthropic / Gemini SDKs
pip install -e ".[dashboard]"    # FastAPI + uvicorn web dashboard
pip install -e ".[dev]"          # pytest, ruff, black, mypy, pre-commit
pip install -e ".[all]"          # everything above
```

## Configure

Configuration resolves in this precedence order:

1. Environment variables (prefixed `JOB_AGENT_`, nested with `__`)
2. `config/config.yaml` (or the file named by `JOB_AGENT_CONFIG_FILE`)
3. Built-in defaults

Copy the template and edit as needed:

```bash
cp .env.example .env
```

Key settings (all optional — defaults work):

| Variable | Default | Meaning |
|---|---|---|
| `JOB_AGENT_LLM__PROVIDER` | `mock` | `openai`/`anthropic`/`gemini`/`ollama`/`vllm`/`mock` |
| `JOB_AGENT_LLM__MODEL` | `claude-opus-4-8` | Model id for the selected provider |
| `JOB_AGENT_EMBEDDING__PROVIDER` | `mock` | `sentence-transformers` or `mock` |
| `JOB_AGENT_PIPELINE__CLASSIFIER_THRESHOLD` | `0.65` | Min overall score to prepare an application |
| `JOB_AGENT_PIPELINE__MAX_JOBS` | `50` | Cap on jobs ingested per run |
| `JOB_AGENT_PIPELINE__MAX_APPLICATIONS_PER_DAY` | `20` | Daily submission cap enforced by the tracker |
| `JOB_AGENT_PIPELINE__ENABLED_BOARDS` | `greenhouse,lever,ashby,yc` | Comma-separated board list |
| `JOB_AGENT_STORAGE__SQLITE_PATH` | `./data/job_agent.db` | Database location |

Provider API keys use the conventional env vars: `OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`.

## Add your background

Everything the agent knows about you lives in `user_data/` (Markdown/YAML). This
directory is **gitignored** — your real background is never committed or pushed.
A fictional template ships as `user_data.example/`. Seed and edit:

```bash
scripts/seed_user_data.sh        # copies user_data.example/ -> user_data/
$EDITOR user_data/profile.yaml   # then edit the category folders
```

No resume content is stored in code. Personal data stays local: `user_data/`
(background), `data/` (generated documents, database, Excel), and `.env` (keys)
are all gitignored; only `user_data.example/` is tracked.

## Configure real job boards (optional)

Edit `config/sources.yaml` and add board tokens, e.g.:

```yaml
sources:
  greenhouse:
    slugs: ["stripe"]
    extra: {company: "Stripe"}
  lever:
    slugs: ["netflix"]
```

Then run against the network instead of sample data:

```bash
job-agent pipeline --no-offline
```

## First run

```bash
job-agent pipeline          # offline sample data, mock LLM — no keys needed
job-agent review
job-agent stats
```

Artifacts: database at `data/job_agent.db`, documents in `data/documents/`,
workbook at `data/job_agent.xlsx`, rotating logs in `data/logs/`.
