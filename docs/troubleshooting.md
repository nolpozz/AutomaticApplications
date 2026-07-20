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

### Live scraping returns nothing / falls back to sample data

A board only fetches live when it has `slugs`/`urls`/`extra` configured in
`config/sources.yaml` **and** you didn't pass `--offline`. On any HTTP error the
scraper logs a warning and uses sample data so one bad board never breaks a run.
Check the board token in the company's careers URL.

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
