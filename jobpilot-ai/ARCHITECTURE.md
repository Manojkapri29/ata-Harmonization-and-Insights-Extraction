# Architecture

```
frontend/  React + Vite + TS + Tailwind + Recharts  ──/api──▶  backend/  FastAPI
                                                                  │
          ┌───────────────────────────────────────────────────────┼───────────────────────────┐
          │ app/api/        routers (jobs, resumes, tracking, system) + Pydantic schemas      │
          │ app/services/   pipeline.py  – workflows (search, kit, tailor, apply)              │
          │                 sources/     – pluggable job-source adapters                      │
          │                 normalize.py – RawJob → normalised record, dedupe hash            │
          │                 matching.py  – weighted, explainable match score                  │
          │                 resume_parser.py, ats.py, tailor.py, export.py                    │
          │                 communications.py, followups.py, analytics.py                     │
          │                 tasks.py     – background task runner + scheduler                 │
          │ app/ai/         providers.py (none/openai/anthropic/ollama) + guard.py            │
          │ app/models.py   SQLAlchemy tables  →  SQLite (or PostgreSQL via DATABASE_URL)     │
          └────────────────────────────────────────────────────────────────────────────────────┘
```

## Data flow: "Find Jobs"

1. UI → `POST /api/jobs/search` (or `/api/search-profiles/{id}/run`) → a `background_tasks` row, status `queued`.
2. `TaskRunner` (thread pool) runs `pipeline.search_task`:
   - for each selected source: `adapter.search(query, PoliteClient)` → `list[RawJob]`
     (assisted sources return browser links instead)
   - `normalize()` → salary (annualised, currency), experience range, location, remote, skills, education,
     notice period, role category, `dedupe_hash`
   - `upsert_job()` → de-duplicates by `(source, source_job_id)` then by `dedupe_hash`
     (same title + company + city across boards); fills gaps in the existing record, keeps your edits
   - local filters for sources that can't filter server-side (keywords, location incl. NCR, date, exp, salary)
   - `match_job()` → score + explanation stored on the job
   - new jobs ≥ high-match threshold → `notifications` row (🔥 alert)
3. UI polls `GET /api/tasks/{id}` (queued → running → completed/failed) and shows progress; nothing blocks.

`Scheduler` (a daemon thread) queues the same task for search profiles with `auto_run`, every `interval_hours`.

## Adding a new job source

Create a class in `app/services/sources/` (or a new module imported from `sources/__init__.py`):

```python
from .base import PoliteClient, SearchQuery, SourceAdapter, register
from ..normalize import RawJob

@register
class MyBoardSource(SourceAdapter):
    key, name, kind = "myboard", "My Board", "api"     # api | feed | company | assisted | demo
    description = "Official API of My Board."
    requires_credentials = ["MYBOARD_API_KEY"]          # add the field to config.Settings too
    server_side_filtering = True                         # API already filters by keyword/location

    def search(self, q: SearchQuery, http: PoliteClient) -> list[RawJob]:
        data = http.json("https://api.myboard.example/jobs", params={"q": q.text})
        return [RawJob(source=self.key, source_job_id=str(j["id"]), title=j["title"], company=j["company"],
                       location=j["city"], job_url=j["url"], description=j["html"], posted=j["date"],
                       salary_text=j.get("salary", "")) for j in data["jobs"]]
```

Restart: it appears in Settings, search profiles and the API automatically (a `job_sources` row is seeded).
Keep parsing in a pure `parse_*` function and add an offline test with a sample payload.

For sites that forbid automation, subclass `AssistedSource` and implement `build(keyword, location, days, exp)`
to return a search URL. Users import from there via bookmarklet/URL/paste.

**Rules for any adapter:** use `PoliteClient` (identifies itself, per-domain delay, robots.txt for pages),
never send user credentials, never bypass CAPTCHA/login/anti-bot measures, respect the site's terms.

## Matching (explainable)

| Component | Weight | How |
|---|---|---|
| Role | 25 | job title's role category vs your target roles; token overlap with targets/past titles |
| Skills | 25 | job skills found ∩ your skills (profile + resume), with implications (Power Query ⇒ Excel) |
| Experience | 15 | your years vs required range; under-qualified penalised more than over-qualified |
| Location | 10 | remote / preferred city / NCR expansion / relocation preference |
| Salary | 10 | job max vs your expected (or current × 1.15); unknown salary = neutral 50 |
| Education | 5 | MBA/PG/graduate vs requirement (e.g. B.Tech-only flagged) |
| JD keywords | 10 | top JD keywords present in your resume |

Unknown information is scored neutrally and listed as "unclear" rather than guessed. The output also carries
matching/missing skills, concerns, reasons and a recommended action.

## Resume pipeline

`resume_parser.extract_text` (pypdf / python-docx / txt) → `parse_resume` (sections by heading, roles by
date ranges, bullets, achievements = bullets with metrics, skills canonicalised, total experience with overlap
merging) → `ats.analyze` (formatting facts from the file: tables, text boxes, columns, images, header contact;
section completeness; readability; keyword/skill coverage vs a JD) → `tailor.optimize` (JD-relevant skills first,
bullets ranked and weak phrasing fixed, projects ranked, summary composed from facts) → `export.to_docx/to_pdf`
(single column, standard headings, no tables/images/header content) → `resume_versions` row with version number,
ATS estimate, keywords surfaced, change log and file paths.

## AI layer

`get_provider()` returns `NoAI`, `OpenAICompatible` (httpx), `AnthropicProvider` (official SDK; server-side
fallback on refusals) or `OllamaProvider`. AI is only asked to rephrase. `guard.check(source, output)` rejects
output containing numbers, known skills or proper names that don't appear in the source; rejected pieces fall back
to the rule-based text and the reason is recorded in the change log.

## Database

`users, profiles, resumes, resume_versions, jobs, job_skills, job_sources, applications, contacts,
communications, followups, search_profiles, ai_analysis, settings`, plus `background_tasks` and `notifications`.
Indexes on job source/status/score/posted date/dedupe hash, application status/dates, follow-up due date.
Deleting a job cascades to its application, follow-ups, skills, messages and analyses.

Portable column types only (JSON, Date, Float…), so PostgreSQL is a `DATABASE_URL` change. Tables are created at
startup; add Alembic when the schema starts evolving.

## Background work

`TaskRunner` wraps a `ThreadPoolExecutor`; status, progress and results live in `background_tasks` so any client
can poll. Each task opens its own DB session and commits between steps (SQLite single-writer). To scale out,
replace `TaskRunner.submit` with a Celery/RQ enqueue; task functions already have the signature
`fn(task_id, params, progress)`.

## Security & compliance

- Secrets only from environment (`.env`, git-ignored); the settings API strips any key-like fields.
- No stored passwords for any job site; assisted boards are opened by the user in their own browser.
- Human confirmation required to mark messages as sent or an application as applied; nothing is sent automatically.
- Contacts are entered manually from public sources; no personal-data scraping.
- CORS limited to the frontend origin(s). The bookmarklet opens the JobPilot UI in a new tab with the page data,
  so job sites never talk to the local API directly.
