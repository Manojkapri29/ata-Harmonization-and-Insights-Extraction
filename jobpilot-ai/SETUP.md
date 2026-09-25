# Setup

## Requirements
- Python 3.10 or newer
- Node.js 20 or newer (includes npm)

## 1. Backend

```bash
cd jobpilot-ai/backend
python -m venv .venv
# macOS / Linux:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
cp ../.env.example .env            # Windows: copy ..\.env.example .env
uvicorn app.main:app --reload --port 8000
```

- API: http://localhost:8000, interactive docs at http://localhost:8000/docs
- Data is stored in `backend/data/` (SQLite database + generated resumes). Back this folder up; it's git-ignored.
- First start creates your profile (from the project brief), the job sources, a default search profile
  ("Data / BI / MIS roles - Delhi NCR") and default settings.

## 2. Frontend

```bash
cd jobpilot-ai/frontend
npm install
npm run dev
```

Open http://localhost:5173. Vite forwards `/api/*` to the backend on port 8000
(set `JOBPILOT_API=http://host:port` to point elsewhere).

Production build: `npm run build`, then `npm run preview` (http://localhost:4173).

## 3. Configure AI (optional)

Everything works without AI. With AI, summaries, bullets and messages are rephrased more naturally, and each
output is checked by the truthfulness guard before it's used.

Edit `backend/.env`, then restart the backend:

| Provider | `.env` |
|---|---|
| None (default) | `AI_PROVIDER=none` |
| **Ollama** (free, local) | Install from https://ollama.com, run `ollama pull llama3.1`, then `AI_PROVIDER=ollama`, `OLLAMA_MODEL=llama3.1` |
| OpenAI / any OpenAI-compatible API (Groq, OpenRouter, Together, LM Studio, vLLM) | `AI_PROVIDER=openai`, `OPENAI_API_KEY=...`, `OPENAI_MODEL=...`, `OPENAI_BASE_URL=...` |
| Anthropic (Claude) | `AI_PROVIDER=anthropic`, `ANTHROPIC_API_KEY=...` (model defaults to `claude-opus-5`) |

**Settings → AI provider → Test connection** confirms it works. The page can switch provider/model, but keys
are only ever read from `.env`.

## 4. Upload your resume

**Resume** page → drop your PDF/DOCX/TXT. Check the "Parsed master resume" panel:
- Every role should show a title, company and dates. If not, use a clear `Experience` heading and dates like
  `Jan 2022 – Present` in the original file, and re-upload.
- DOCX parses most reliably; scanned (image) PDFs can't be read.

Uploading re-scores every job against the new resume.

## 5. Create a search profile

**Job Search → Search profiles**:
- Keywords: one role per chip (`Data Analyst`, `MIS Executive`, …)
- Locations: `Delhi NCR` also covers Noida, Greater Noida, Gurugram, Ghaziabad and Faridabad
- Experience range, minimum monthly salary, "posted within", remote on/off
- Sources: tick the ones to search
- **Run automatically every N hours** keeps searching in the background while the backend runs. New jobs
  above your high-match threshold (Settings → Follow-ups & alerts) raise a 🔥 alert.

Click **Find Jobs**. API sources run in the background; browser-assisted boards (LinkedIn, Naukri, Indeed, …)
come back as search links to open yourself.

## 6. Import jobs from LinkedIn / Naukri / anywhere

**Job Search → Import a job**:
- **Bookmarklet**: drag "+ Save to JobPilot" to your bookmarks bar. On any job page you're viewing, click it.
  JobPilot opens and imports that job (it reads the page's structured JobPosting data, or the text you select).
- **By URL**: public pages / company career pages.
- **Paste**: title + description.
- **File**: CSV / Excel / JSON with a `title` column.

## 7. Add job sources that need keys

- **Adzuna** (recommended for India): register free at https://developer.adzuna.com, put `ADZUNA_APP_ID` and
  `ADZUNA_APP_KEY` in `backend/.env`, restart.
- **Greenhouse / Lever / Ashby**: Settings → Job sources → add company board names from careers URLs
  (`boards.greenhouse.io/<name>`, `jobs.lever.co/<name>`, `jobs.ashbyhq.com/<name>`).
- **RSS**: Settings → Job sources → feed URLs.

## Moving to PostgreSQL

```bash
pip install "psycopg[binary]"
# backend/.env
DATABASE_URL=postgresql+psycopg://jobpilot:password@localhost:5432/jobpilot
```
Tables are created on startup. For schema changes over time, add Alembic migrations.

## Troubleshooting

| Problem | Fix |
|---|---|
| UI says "Cannot reach the JobPilot backend" | Start the backend on port 8000 |
| A source shows `error` after a search | Hover the note in Search results. Usually a missing key or the site being down. Other sources still run. |
| Resume roles missing | Use standard headings (Experience, Skills, Education) and date ranges; prefer DOCX |
| Bookmarklet does nothing | Some browsers block pop-ups from bookmarklets; allow pop-ups for the job site |
