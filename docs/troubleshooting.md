# Troubleshooting

### The pipeline runs but everything says `[mock:...]` / scores look synthetic

That's expected with the default configuration. Set a real
`JOB_AGENT_LLM__PROVIDER` and the matching API key to use a real model. Mock mode
is deterministic on purpose so the pipeline is runnable and testable with no keys.

### No DOCX or PDF files were produced

Those formats require optional dependencies:

```bash
pip install -e ".[documents]"     # python-docx (DOCX) + weasyprint (PDF)
```

Markdown is always written. If the libraries are missing the renderer logs an
info line and skips that format — it never fails the run. WeasyPrint also needs
system libraries (Pango/cairo); see its docs if PDF import fails.

### `sentence-transformers` / embeddings errors

The default embedding provider is `mock` (a deterministic hashed bag-of-words) and
needs nothing. For real embeddings: `pip install -e ".[embeddings]"` and set
`JOB_AGENT_EMBEDDING__PROVIDER=sentence-transformers`. The first run downloads the
model.

### Live scraping returns nothing

A board fetches live when you pass `--no-offline` **and** either it has
`slugs`/`urls`/`extra` in `config/sources.yaml` (Greenhouse/Lever/Ashby/GitHub) or
it is a search/target board that needs no slugs (Amazon, Google, Netflix, Spotify,
Workday). On any HTTP error a live board logs a warning and returns **zero jobs** —
it does *not* fall back to sample data (fictional rows are never injected into a real
run). So an empty live board means a bad token or a failed request: verify the slug
in the company's careers URL (`boards.greenhouse.io/<slug>`, `jobs.ashbyhq.com/<slug>`,
…). Sample data appears only in explicit offline mode (`job-agent pipeline` without
`--no-offline`).

### I tuned the ranking settings but the review queue looks the same

Changing `target_*`, `domain_*`, `prestige_*`, `*_boost`, or `blocked_companies`
only affects *future* classifications. To apply them to jobs already in the database
without re-scraping or spending on the LLM, run `python3 scripts/rescore.py`. It
re-scores from each job's stored `base_score`, `ARCHIVED`s roles that now fall below
`classifier_threshold` (their documents stay on disk — see them with
`job-agent review --state ARCHIVED`), and reports previously-`REJECTED` roles that
now qualify. It also re-ranks the Excel workbook.

### LinkedIn / Wellfound / YC return only sample data

By design. LinkedIn scraping is disabled (Terms of Service); Wellfound and YC have
no free public jobs API. Provide an authorized integration in the respective
scraper's `_fetch_live` if you have access.

### "Daily cap of N applications reached"

The tracker enforces `JOB_AGENT_PIPELINE__MAX_APPLICATIONS_PER_DAY`. Raise it or
wait until the next day. This guards against accidental mass submission.

### Excel file is locked / won't update

`sync-excel` overwrites `data/job_agent.xlsx`. Close it in your spreadsheet app
first (Excel holds an exclusive lock on Windows). SQLite remains the source of
truth regardless — you can always regenerate.

### Settings changes aren't taking effect

Settings are cached per process. The CLI reloads them each invocation. In a Python
session call `job_agent.config.reload_settings()`. Remember precedence: env vars
override `config/config.yaml` override defaults.

### Resetting state

Delete the `data/` directory (database, documents, workbook, logs) and re-run.
Everything is regenerated from `user_data/` and the boards.

### Where are the logs?

Console plus a rotating file at `data/logs/job_agent.log` (JSON-formatted). Every
database modification is also recorded in the `logs` table. Raise verbosity with
`job-agent --log-level DEBUG <command>`.
