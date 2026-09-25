# JobPilot AI

A personal job-search agent. It finds relevant jobs, scores each one against your profile and resume with
an explainable match score, estimates ATS compatibility, builds a truthful job-specific resume (DOCX + PDF),
drafts HR outreach (email, WhatsApp, LinkedIn note/DM, cover letter), and tracks applications and follow-ups.

**Stack:** React + Vite + TypeScript + Tailwind + Recharts · FastAPI + SQLAlchemy + SQLite (PostgreSQL-ready) ·
optional AI via OpenAI-compatible APIs, Anthropic or local Ollama.

## Quick start

```bash
# Terminal 1: backend  (Python 3.10+)
cd jobpilot-ai/backend
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env                                   # Windows: copy ..\.env.example .env
uvicorn app.main:app --reload --port 8000

# Terminal 2: frontend  (Node 20+)
cd jobpilot-ai/frontend
npm install
npm run dev
```

Open **http://localhost:5173**. API docs: **http://localhost:8000/docs**.

First steps in the app:
1. **Settings → Profile**: add your email, phone and city (left blank on purpose so they aren't in code).
2. **Resume**: upload your master resume (DOCX parses best).
3. **Find Jobs** (top right). Open a job → **Generate Application Kit** → review → apply yourself → **Mark Applied**.

Full instructions: [SETUP.md](SETUP.md) · Design: [ARCHITECTURE.md](ARCHITECTURE.md) · Endpoints: [API.md](API.md)

## What works now

| Module | Status |
|---|---|
| Job discovery (background tasks, scheduler, search profiles) | ✅ |
| Normalisation (salary in LPA/lakh/monthly, experience, NCR locations, skills) + cross-board de-duplication | ✅ |
| Explainable matching: role 25, skills 25, experience 15, location 10, salary 10, education 5, JD keywords 10 | ✅ |
| Resume parsing (PDF / DOCX / TXT) into summary, roles, bullets, achievements, skills, education, certifications, projects | ✅ |
| ATS compatibility estimate: keywords, sections, formatting (tables, text boxes, columns, header contact), readability | ✅ |
| ATS-optimised and job-specific resumes, versioned (`Manoj_Kapri_Data_Analyst_ABC_v1.docx`) | ✅ |
| Cover letter, HR email, WhatsApp, LinkedIn note (≤300 chars), LinkedIn DM | ✅ |
| One-click **Application Kit** (10 steps, progress shown live) | ✅ |
| Tracker (10 statuses), follow-ups (Day 3/7/14, configurable), reminders on dashboard | ✅ |
| Dashboard, analytics (application/response/interview rates by source and role) | ✅ |
| High-match alerts (bell + toast) with Analyze / Tailor / Email / LinkedIn / Track actions | ✅ |
| Import/export CSV, Excel, JSON; job import by URL, pasted JD, or browser bookmarklet | ✅ |
| Dark/light mode, responsive layout, loading/empty/error states, toasts | ✅ |

## Job sources: what needs what

| Source | How it works | Needs |
|---|---|---|
| Remotive, RemoteOK, Arbeitnow, The Muse | Public JSON APIs | Nothing (mostly remote / international jobs) |
| Greenhouse, Lever, Ashby | Official public career-page APIs | Company board names (Settings → Job sources) |
| **Adzuna** | Official job-search API with **India** coverage | Free `ADZUNA_APP_ID` + `ADZUNA_APP_KEY` in `backend/.env` |
| RSS / Atom | Any public job feed | Feed URLs in Settings |
| **LinkedIn, Naukri, Indeed, Glassdoor, Foundit, Internshala** | **Browser-assisted / manual import.** Their terms forbid scraping or they need login, so JobPilot builds the search links, you open them, and import jobs with the bookmarklet, by URL, or by pasting the JD. | Nothing. No passwords are ever stored. |
| Any public job page URL | Reads schema.org `JobPosting` data; robots.txt respected | Nothing |
| Demo | 5 clearly-labelled **fake** jobs to try the app offline | Off by default |

## Guarantees built into the code

- **No fabrication.** Tailoring only selects, reorders and rephrases what's in your resume/profile. Any AI rewrite
  is rejected if it introduces a new number, skill, employer or credential (`app/ai/guard.py`, covered by tests).
- **Nothing is sent or submitted automatically.** Messages are drafts; "Mark as sent" and "Mark applied" require
  your explicit confirmation.
- **No CAPTCHA/login bypass, no scraping of sites that forbid it**, robots.txt checks and per-domain rate limits
  for page fetching.
- Scores are labelled as estimates: the match score does not predict selection, and the ATS score is an
  "ATS compatibility estimate", never a guarantee.

## Tests

```bash
cd backend && pip install -r requirements-dev.txt && python -m pytest      # 61 tests
cd frontend && npm run build                                                # type-check + production build
```
