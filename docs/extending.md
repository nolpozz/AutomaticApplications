# Extending the pipeline

The system is designed so common extensions touch exactly one place.

## Add a job board

1. Create `job_agent/scrapers/<name>.py` with a class inheriting
   `AbstractScraper`. Implement two methods:

   ```python
   from job_agent.scrapers.base import AbstractScraper
   from job_agent.models.domain import Job

   class MyBoardScraper(AbstractScraper):
       source = "myboard"

       def _fetch_live(self) -> list[Job]:
           with self._client() as client:
               ...  # hit the API; build jobs with self._job(...)
           return jobs

       def _sample(self) -> list[Job]:
           return [self._job(title=..., company=..., url=..., description=...)]
   ```

   `self._job(...)` normalizes and fills sensible defaults (remote/level inference,
   dedup key). `fetch()` (in the base) handles live-vs-sample selection, per-run
   dedup, capping, and error isolation for you.

2. Register it in `job_agent/scrapers/registry.py`:

   ```python
   _SCRAPERS["myboard"] = MyBoardScraper
   ```

3. Enable it via `JOB_AGENT_PIPELINE__ENABLED_BOARDS` and configure targets in
   `config/sources.yaml`.

Nothing else in the pipeline changes.

## Add an LLM provider

1. Create `job_agent/llm/providers/<name>.py` implementing `LLMProvider._complete`.
   Import the SDK lazily inside the method so the package imports without it.
2. Wire it in `job_agent/llm/factory.py` (one `if` branch).

The retry loop, JSON extraction, and fallback behavior are inherited from the base.

## Add or revise a prompt

Prompts are versioned files in `job_agent/llm/prompts/` named `name.vN.txt` with
`===SYSTEM===` / `===USER===` sections (Jinja2). To revise a prompt without losing
the old one, add `name.v2.txt`; the registry uses the highest version by default,
and the version string is stored on every artifact it produces. Pin a version with
`registry.render("name", version=1, ...)`.

## Swap the embedding backend

Set `JOB_AGENT_EMBEDDING__PROVIDER=sentence-transformers` for real embeddings, or
`JOB_AGENT_EMBEDDING__BACKEND=faiss` to use a FAISS index instead of the SQLite
vector store. Both implement the same `VectorStore` interface.

## Tune the classifier

The deterministic heuristic lives in `JobClassifier._heuristic`. Adjust `_WEIGHTS`
or the sub-scores. When a real LLM provider is selected the model's JSON is used
and the heuristic becomes the fallback only.

## Future extension points (interfaces are ready)

* **Application automation (Playwright)** — a `submit` step already exists in the
  tracker; add a browser driver that consumes the stored resume/cover paths.
* **Email automation, recruiter tracking, interview scheduling** — hang off the
  `applications` table and tracker transitions.
* **Salary prediction / company scoring** — `companies.score` and job fields are
  in place.
* **Resume A/B testing** — versions are already first-class (`resume_versions`).
* **Learning from outcomes** — `applications` records outcomes and response times;
  feed them back into classifier calibration.
* **Multi-user / cloud** — the repository is the only DB touchpoint; add a tenant
  key and swap SQLite for Postgres.
