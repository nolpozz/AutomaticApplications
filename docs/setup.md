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

### Ranking & targeting controls

These shape *which* roles reach the expensive stages and how they rank in the
review queue. **All default off** (empty list / `0` / `1.0`), so the pipeline
behaves exactly as before until you set them. Every one is deterministic and is
also honored by `scripts/rescore.py`, so you can tune them and re-rank an existing
database without any LLM calls. List values are comma-separated as env vars.

| Variable (`JOB_AGENT_PIPELINE__…`) | Default | Meaning |
|---|---|---|
| `TARGET_EXPERIENCE_LEVELS` | `[]` | Levels you want (e.g. `internship,entry`). Off-target roles get a multiplier < 1. |
| `TARGET_KEYWORDS` | `[]` | Title terms marking an on-target role (e.g. `intern,co-op`). |
| `TARGET_DESCRIPTION` | `""` | Human phrase shown to the LLM (e.g. `Master's-level internships`). |
| `DOMAIN_KEYWORDS` | `[]` | If set, a role with *none* of these in its title/description/skills is multiplied by `DOMAIN_PENALTY`. |
| `DOMAIN_PENALTY` | `1.0` | Multiplier for off-domain roles (e.g. `0.5`). `>= 1.0` disables the gate. |
| `PRESTIGE_BOOST` | `0.0` | Score bonus added to FAANG+/top-AI-lab employers; high-growth startups get `0.6×` this. |
| `PRESTIGE_CAP_MULTIPLIER` | `1` | Prestigious companies keep `TOP_PER_COMPANY × this` roles through the per-company cap. |
| `PRESTIGE_EXTRA_FAANG` / `PRESTIGE_EXTRA_GROWTH` | `[]` | Extend the built-in tier lists (`classifier/prestige.py`). |
| `TARGET_LOCATIONS` | `[]` | Locations to boost (e.g. `new york,nyc`); a matching role gets `+LOCATION_BOOST`. |
| `LOCATION_BOOST` | `0.0` | Additive bonus for a location match. |
| `BOOST_KEYWORDS` | `[]` | Title terms to boost (e.g. `research,nlp`); `+KEYWORD_BOOST` per hit. |
| `KEYWORD_BOOST` | `0.0` | Additive bonus per title-keyword hit. |
| `BOOST_CAP` | `0.1` | Ceiling on the total additive boost per job, so a boost nudges but never dominates. |
| `BLOCKED_COMPANIES` | `[]` | Employers to drop at scrape time (word-boundary match), before any embedding/LLM spend. |

Order of application on the base fit score: **level targeting → domain gate →
prestige bonus → location/keyword boosts** (targeting and domain are multipliers,
applied before the additive boosts, so an off-target/off-domain role can't be
lifted over the threshold by a boost). See the README's *reproducible classifier*
section and `job_agent/classifier/` for the implementations.

After tuning these, re-rank an existing database offline:

```bash
python3 scripts/rescore.py    # no LLM calls; archives newly off-domain roles,
                              # surfaces newly-qualifying ones, re-ranks Excel
```

### How much each factor weighs

The **base fit score** (before the adjustments above) is a weighted sum of five
sub-scores, defined by `_WEIGHTS` in `job_agent/classifier/classifier.py`:

| Sub-score | Weight |
|---|---|
| technical (skills/langs/frameworks overlap) | **0.35** |
| interest (alignment with your stated interests) | **0.25** |
| experience (years vs. required) | **0.20** |
| education | **0.10** |
| research | **0.10** |

The classifier (LLM or the deterministic heuristic) rates each of the five
dimensions on a **1-100 scale** and returns *only* those ratings — never an overall
score. The pipeline normalizes each rating to [0, 1] and applies `_WEIGHTS` itself
(`_weighted_overall` in `classifier.py`) to compute `overall_score`. So the same
weights govern for **every** provider — the model supplies dimension ratings, your
weights decide how they combine, and swapping LLMs does not change the weighting.
`recommendation` and `interview_probability` (= `overall_score × 0.6`) are derived
from that overall, not returned by the model.

The **adjustments** then have these magnitudes:

* **Level targeting** is the only place role *type* is enforced, and it is a
  *soft* down-weight, never a hard filter: an off-target role keeps `×0.6` of its
  score, or `×0.5` if it is senior/staff/principal. With the default 0.65 threshold
  a role scoring 0.9 survives a `×0.6` (→0.54 fails) or not depending on its base —
  so targeting reshapes the queue rather than deleting roles.
* **Geography** is purely additive and opt-in: a location match adds
  `location_boost`, bounded by `boost_cap` (default 0.1). It cannot exclude a job
  and cannot move a role more than the cap. If you never set `target_locations`,
  location is ignored entirely.
* **Prestige** adds `prestige_boost` for FAANG+/top-AI-labs and `0.6 ×` that for
  high-growth startups, and multiplies a prestigious company's per-company cap by
  `prestige_cap_multiplier`. Both default to no-ops.
* **Domain gate** multiplies by `domain_penalty` (only when configured `< 1.0`).

### Which companies are blocked, and changing them

**None by default** — `blocked_companies` ships empty, so no employer is excluded.
Blocking is entirely opt-in: add company names (word-boundary matched against the
posting's company, so `meta` blocks "Meta" but not "Metabolic"), and those jobs are
dropped at scrape time before any embedding or LLM spend. To stop blocking a
company, remove it from the list. Example:

```bash
# .env  — blocks two companies for *your* runs only
JOB_AGENT_PIPELINE__BLOCKED_COMPANIES=acme corp,globex
```

The **prestige** tier lists (`FAANG_PLUS` / `HIGH_GROWTH` in
`classifier/prestige.py`) are the opposite of a blocklist — they *favor* employers —
and are separate from `blocked_companies`.

### Per-user vs. shared configuration

The tool is single-user per checkout; isolation between users comes from *where* a
setting lives:

* **Per-user (gitignored, never affects anyone else):** `.env`, `config/config.yaml`,
  and `user_data/`. Put *all* personal tailoring here — targeting, locations,
  blocklist, prestige boost, thresholds, even your own `search_queries`. Any
  `PipelineSettings` field is settable as `JOB_AGENT_PIPELINE__<FIELD>` in `.env`
  or under `pipeline:` in `config/config.yaml`.
* **Shared (committed — edits change the default for everyone, land via PR):**
  `config/sources.yaml` (board tokens), `DEFAULT_SEARCH_QUERIES` and `_WEIGHTS` in
  `job_agent/config/settings.py` / `classifier/classifier.py`, and the prestige tier
  lists in `classifier/prestige.py`.

Rule of thumb: **retune your own runs through `.env` / `config/config.yaml` /
`user_data/`; only touch committed files to move the project default.** Adding a new
board, provider, prompt, or ranking module is additive and off-by-default (see
[`extending.md`](extending.md)), so new features ship dormant and reach a user only
when they enable them.

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
