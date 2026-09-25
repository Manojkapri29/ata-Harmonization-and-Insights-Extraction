# Free Job Copilot

A free, open-source alternative to paid job copilots. It:

1. **Finds jobs** from free sources (official public APIs, no login).
2. **Scores each job against your profile** (0-100) and shows the skills you match and the ones you're missing.
3. **Builds a tailored, ATS-friendly resume** (DOCX + PDF) and a **cover letter** for any job.
4. **Tracks your applications** in a CSV you can open in Excel.

It does **not** auto-apply. That's on purpose; see [Why no auto-apply](#why-no-auto-apply).

## Quick start

```bash
cd job_copilot_free
pip install -r requirements.txt
cp profile.example.yaml profile.yaml      # then fill in your real details
streamlit run app.py
```

Open http://localhost:8501.

### Free hosting (optional)
Push to GitHub, then on [share.streamlit.io](https://share.streamlit.io) create an app with
main file `job_copilot_free/app.py`. Put Adzuna keys under *App settings > Secrets*.
The disk on free hosting resets on restart, so use the **Download** buttons for your profile and tracker.
A public URL means anyone could open your app, so keep it private (Streamlit Cloud lets you restrict viewers).

## Job sources

| Source | Key needed | Good for |
|---|---|---|
| Remotive, RemoteOK, Arbeitnow | No | Remote / international roles |
| The Muse | No | Data & Analytics roles (mostly US/EU) |
| Greenhouse / Lever / Ashby boards | No | Specific companies' careers pages. Enter the name from the URL, e.g. `boards.greenhouse.io/<name>` |
| **Adzuna** | Free key ([developer.adzuna.com](https://developer.adzuna.com)) | **India** (`country = in`) and 15 other countries |
| JobSpy (optional) | No | LinkedIn, Indeed, Naukri, Glassdoor. `pip install python-jobspy` |

**For jobs in India, use Adzuna + JobSpy.** The no-key sources are mostly remote or foreign roles.

JobSpy scrapes sites that don't offer an official API. It can break when those sites change, and it can get
rate-limited. Use it only for your own searching, keep result counts modest, and never use it with your login.

## How the match score works

```
score = 50 x keyword coverage  (share of the job's recognised skills that you have)
      + 30 x text similarity   (TF-IDF cosine between your profile and the job; 0.30 counts as full)
      + 20 x title fit         (overlap between the job title and your target_roles)
```

It's a ranking aid, not a prediction of whether you'll get shortlisted. The skills vocabulary is `SKILL_VOCAB`
in `jobcopilot/matcher.py`. Add terms for your field.

## How tailoring works (and why it never lies)

Your `profile.yaml` is a **master profile** with everything true about you. For each job the app:
- puts the skill groups and skills the job asks for first,
- orders bullets in each role and project by relevance, and keeps the top N,
- keeps the most relevant projects,
- never adds a skill, number or claim that isn't already in your profile.

The **"Job asks for, not in your profile"** list is a to-do list. If you really have that skill, add it with a
bullet that proves it. If you don't, it's a learning gap, not something to type into your resume.

## Why no auto-apply

- LinkedIn and Naukri ban automated applying in their terms. Accounts get restricted.
- Sending the same application to hundreds of jobs gives low response rates, and recruiters notice.
- Auto-fill bots often submit wrong answers to screening questions under your name.

A dozen well-targeted applications a week, each with a tailored resume, usually beat hundreds of automated ones.

## Project layout

```
app.py                  Streamlit UI (Find jobs / Tailor resume / Tracker / Profile)
jobcopilot/sources.py   job source parsers + fetchers, filtering, de-duplication
jobcopilot/matcher.py   skill vocabulary, match scoring, keyword gap
jobcopilot/resume.py    tailoring, Markdown / DOCX / PDF export, cover letter
jobcopilot/tracker.py   CSV application tracker
jobcopilot/profile.py   load / validate / save profile.yaml
tests/                  offline tests (python -m pytest)
```
