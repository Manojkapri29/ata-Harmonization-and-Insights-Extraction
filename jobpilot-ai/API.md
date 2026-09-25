# API

Base URL `http://localhost:8000`. Interactive docs with request/response schemas: **`/docs`** (Swagger) and
`/redoc`. All bodies are JSON unless noted. Long-running work returns a **task** (`202`); poll
`GET /api/tasks/{id}` until `status` is `completed` or `failed` (`queued → running → completed | failed`).

## Jobs

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/jobs` | List with filters: `q, role, location, source, status, min_score, max_experience, min_salary_monthly, posted_within_days, remote`, sorting `sort=match_score\|posted_date\|created_at\|salary_max\|company`, `order`, `page`, `page_size` |
| POST | `/api/jobs` | Manual job / pasted JD `{title, company, location, description, job_url, salary_text, experience_text, …}` |
| POST | `/api/jobs/search` | **Task.** Search sources. Body: `{search_profile_id}` or inline `{keywords, locations, experience_min/max, include_remote, min_salary_monthly, posted_within_days, sources}`. Result: per-source counts, new job ids, high matches, assisted search links |
| POST | `/api/jobs/import/url` | `{url}`: import a public job page (schema.org JobPosting; robots.txt respected) |
| POST | `/api/jobs/import/page` | `{url, title, text, jsonld[]}`: bookmarklet import from a page the user is viewing |
| POST | `/api/jobs/rescore` | Re-score every job against the current profile/resume |
| GET / PATCH / DELETE | `/api/jobs/{id}` | Detail (description + `match_details`) / edit status, notes, HR fields / delete (cascades) |
| POST | `/api/jobs/{id}/analyze` | JD analysis: required skills, keywords, requirements, responsibilities, red flags (e.g. fee requests) |
| POST | `/api/jobs/{id}/match` | Recompute the explainable match |
| POST | `/api/jobs/{id}/ats` | ATS estimate of the master resume against this job |
| POST / GET | `/api/jobs/{id}/resume` | Create a job-specific resume version (`?use_ai=true\|false`) / list versions for the job |
| POST / GET | `/api/jobs/{id}/communications` | Generate drafts `{channels: ["email","whatsapp","linkedin_note","linkedin_dm","cover_letter"], contact_id?}` / list |
| POST | `/api/jobs/{id}/kit` | **Task.** One-click Application Kit (JD → match → resume ATS → tailored resume → 5 messages → saved) |
| GET | `/api/jobs/{id}/kit` | Latest kit (communications, resume version, analyses) or `null` |
| POST | `/api/jobs/{id}/apply` | Record that you applied `{resume_version_id?, applied_on?}`; schedules follow-ups |

### Match object (excerpt)
```json
{
  "overall": 87,
  "components": {"role": {"score": 100, "weight": 25}, "skills": {"score": 80, "weight": 25}, "...": {}},
  "role_match": 100, "skill_match": 80, "experience_match": 100, "location_match": 100,
  "matching_skills": ["Advanced Excel", "Power BI", "SQL", "MIS Reporting"],
  "missing_skills": ["VBA/Macros", "Retail Analytics"],
  "concerns": ["Not in your profile/resume: VBA/Macros, Retail Analytics."],
  "why": ["'MIS Executive' is a MIS Executive role, one of your target roles."],
  "recommendation": "Good fit. Tailor your resume to the JD before applying.",
  "disclaimer": "Match score is an estimate to help you prioritise. It does not predict interview selection."
}
```

## Resumes

| Method | Path | Purpose |
|---|---|---|
| GET / POST | `/api/resumes` | List / upload (multipart `file`: PDF, DOCX, TXT ≤ 5 MB; `?make_master=true`) |
| GET / DELETE | `/api/resumes/{id}` | Parsed resume + format info / delete |
| POST | `/api/resumes/{id}/master` | Make master (re-scores jobs) |
| POST | `/api/resumes/analyze` | ATS estimate `{resume_id?, job_id? \| jd_text + job_title?}`; omit both for a general check |
| POST | `/api/resumes/tailor` | `{resume_id?, job_id?, use_ai}`: job-specific version, or ATS-optimised general version without `job_id` |
| GET | `/api/resumes/versions` | All versions (`?job_id=`) |
| GET / DELETE | `/api/resumes/versions/{id}` | Version content, change log, keywords surfaced, ATS estimate |
| GET | `/api/resumes/versions/{id}/download?format=docx\|pdf` | File, e.g. `Manoj_Kapri_Data_Analyst_ABC_v1.docx` |

## Applications, contacts, messages, follow-ups

| Method | Path | Purpose |
|---|---|---|
| GET / POST | `/api/applications` | List (`?status=Applied,Interview&q=`) / create `{job_id, status}` |
| GET / PATCH / DELETE | `/api/applications/{id}` | Detail with follow-ups and messages / update `{status, applied_date, notes, response_received, resume_version_id}` |
| GET / POST | `/api/contacts` | List (`?job_id=&company=`) / add a publicly listed HR contact |
| PATCH / DELETE | `/api/contacts/{id}` | Edit / delete |
| GET | `/api/communications` | List (`?channel=&status=draft\|sent`) |
| PATCH | `/api/communications/{id}` | Edit `{subject, body}`; record as sent with `{mark_sent: true, confirm: true}` (409 without `confirm`). LinkedIn notes are limited to 300 chars |
| GET | `/api/communications/{id}/links` | `mailto:` / `wa.me` / LinkedIn links pre-filled with the draft |
| DELETE | `/api/communications/{id}` | Delete draft |
| GET | `/api/followups` | `?status=pending\|done,skipped&due_only=true` |
| PATCH | `/api/followups/{id}` | `{status: done\|skipped\|pending, due_date, note}` |
| POST | `/api/followups/{id}/draft` | Draft the follow-up message (Day 3 nudge, Day 7 email, Day 14 final) |

Statuses: `Saved, Shortlisted, Resume Tailored, Applied, HR Contacted, Interview, Assessment, Rejected, Offer, Closed`.
Moving to Interview/Assessment/Offer/Rejected/Closed cancels pending follow-ups.

## Search profiles, sources, settings

| Method | Path | Purpose |
|---|---|---|
| GET / POST | `/api/search-profiles` | List / create `{name, keywords[], locations[], experience_min, experience_max, include_remote, min_salary_monthly, posted_within_days, sources[], auto_run, interval_hours}` |
| PUT / DELETE | `/api/search-profiles/{id}` | Update / delete |
| POST | `/api/search-profiles/{id}/run` | **Task.** Run now |
| GET | `/api/sources` | All adapters with kind, credentials needed/missing, config fields, last run |
| PATCH | `/api/sources/{key}` | `{enabled, config}` (e.g. `{"companies": "razorpay, groww"}`) |
| GET | `/api/sources/links` | Browser-assisted search links for a search profile |
| GET / PUT | `/api/profile` | Your profile (PUT re-scores all jobs) |
| GET / PUT | `/api/settings` | Thresholds, follow-up schedule, AI provider/model override (keys only from `.env`), source options |
| POST | `/api/settings/ai/test` | Test the configured AI provider |

## Tasks, alerts, analytics, import/export

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/tasks`, `/api/tasks/{id}` | Background task status, progress %, message, result, error |
| GET | `/api/notifications` | High-match alerts `{title: "🔥 NEW HIGH MATCH JOB", body: {company, role, location, match, salary, posted, application_url}}` |
| POST | `/api/notifications/{id}/read`, `/api/notifications/read-all` | Mark read |
| GET | `/api/dashboard` | Cards: jobs found today, relevant, high match, applications, HR contacts, interviews, offers, response rate |
| GET | `/api/analytics` | Totals, rates (application, HR response, interview conversion), weekly series, by source/role, match distribution, funnel, source- and role-wise response rates |
| GET | `/api/export/{jobs\|applications\|contacts\|communications\|analytics}?format=csv\|xlsx\|json` | Download |
| POST | `/api/import/jobs` | Multipart CSV / XLSX / JSON with a `title` column |
| GET | `/api/health` | Liveness |
