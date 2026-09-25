"""Business workflows that tie the services together (used by the API and background tasks)."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..ai.providers import get_provider
from ..config import get_settings
from ..db import session_scope
from ..models import (AIAnalysis, Application, Communication, Contact, Job, JobSkill, JobSource, Notification,
                      Profile, Resume, ResumeVersion, SearchProfile, Setting)
from . import ats, communications, export, followups, tailor
from .matching import Candidate, build_candidate, match_job
from .normalize import NCR, REMOTE_RE, RawJob, cities_in, format_salary, normalize
from .skills import find_skills, jd_keywords, role_category, title_tokens
from .sources import REGISTRY, PoliteClient, SearchQuery, SourceError

APP_STATUSES = ["Saved", "Shortlisted", "Resume Tailored", "Applied", "HR Contacted", "Interview", "Assessment",
                "Rejected", "Offer", "Closed"]
STOP_FOLLOWUPS = {"Interview", "Assessment", "Rejected", "Offer", "Closed"}


# ---------------------------------------------------------------- settings / profile

def get_setting(db: Session, key: str, default=None):
    row = db.get(Setting, key)
    return row.value if row is not None and row.value is not None else default


def set_setting(db: Session, key: str, value) -> None:
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value


def get_profile(db: Session) -> Profile:
    p = db.scalar(select(Profile).order_by(Profile.id))
    if p is None:
        from ..seed import seed
        seed(db)
        p = db.scalar(select(Profile).order_by(Profile.id))
    return p


def master_resume(db: Session) -> Resume | None:
    return db.scalar(select(Resume).where(Resume.is_master).order_by(Resume.id.desc())) or \
        db.scalar(select(Resume).order_by(Resume.id.desc()))


def candidate(db: Session) -> tuple[Candidate, Resume | None]:
    resume = master_resume(db)
    return build_candidate(get_profile(db), resume.parsed if resume else None, resume.raw_text if resume else ""), resume


def ai_provider(db: Session):
    return get_provider(get_setting(db, "ai", {}) or {})


# ---------------------------------------------------------------- jobs: save / dedupe / score

def upsert_job(db: Session, raw: RawJob) -> tuple[Job, bool]:
    data = normalize(raw)
    if not data["title"]:
        raise ValueError("Job has no title")
    existing = db.scalar(select(Job).where(Job.source == data["source"], Job.source_job_id == data["source_job_id"]))
    if existing is None:
        existing = db.scalar(select(Job).where(Job.dedupe_hash == data["dedupe_hash"]))
    if existing is not None:
        # fill gaps from the new copy, keep the user's edits (status/notes/hr fields)
        for k, v in data.items():
            if k in ("source", "source_job_id", "dedupe_hash"):
                continue
            if v not in (None, "", []) and getattr(existing, k) in (None, "", []):
                setattr(existing, k, v)
        if len(data["description"]) > len(existing.description or ""):
            existing.description = data["description"]
        existing.scraped_at = datetime.utcnow()
        _sync_skills(existing)
        return existing, False
    job = Job(**data)
    db.add(job)
    db.flush()
    _sync_skills(job)
    return job, True


def _sync_skills(job: Job) -> None:
    have = {s.skill for s in job.job_skills}
    for s in job.skills or []:
        if s not in have:
            job.job_skills.append(JobSkill(skill=s[:100]))


def score_job(job: Job, cand: Candidate) -> dict:
    m = match_job(job, cand)
    job.match_score, job.match_details = m["overall"], m
    return m


def rescore_all(db: Session) -> int:
    cand, _ = candidate(db)
    jobs = list(db.scalars(select(Job)))
    for j in jobs:
        score_job(j, cand)
    return len(jobs)


# ---------------------------------------------------------------- search

def _keyword_hit(job: Job, keywords: list[str]) -> bool:
    if not keywords:
        return True
    title = job.title.lower()
    cats = {role_category(k) for k in keywords} - {"Other"}
    if job.role_category in cats:
        return True
    for kw in keywords:
        k = kw.lower().strip()
        if k and (k in title or (title_tokens(k) and title_tokens(k) <= title_tokens(job.title))):
            return True
    return False


def _location_hit(job: Job, locations: list[str], include_remote: bool) -> bool:
    if not locations:
        return True
    if include_remote and (job.remote or REMOTE_RE.search(job.location or "")):
        return True
    wanted = set()
    for l in locations:
        wanted |= cities_in(l)
    if "Delhi NCR" in wanted:
        wanted |= NCR
    have = cities_in(job.location or "")
    if "Delhi NCR" in have:
        have |= NCR
    return bool(wanted & have) or any(l.lower() in (job.location or "").lower() for l in locations if l.lower() != "remote")


def passes_filters(job: Job, q: SearchQuery) -> bool:
    if not _keyword_hit(job, q.keywords):
        return False
    if not _location_hit(job, [l for l in q.locations if l.lower() != "remote"], q.include_remote or
                         any(l.lower() == "remote" for l in q.locations)):
        return False
    if job.posted_date and q.posted_within_days and job.posted_date < date.today() - timedelta(days=q.posted_within_days):
        return False
    if q.experience_max is not None and job.experience_min is not None and job.experience_min > q.experience_max + 1:
        return False
    if q.min_salary_monthly and job.salary_max and job.salary_currency in ("INR", "") \
            and job.salary_max < q.min_salary_monthly * 12:
        return False
    return True


def query_from(db: Session, params: dict) -> tuple[SearchQuery, list[str], SearchProfile | None]:
    sp = db.get(SearchProfile, params["search_profile_id"]) if params.get("search_profile_id") else None
    get = (lambda k, d=None: params.get(k, getattr(sp, k, d) if sp else d))
    enabled = {s.key for s in db.scalars(select(JobSource).where(JobSource.enabled))}
    sources = [s for s in (get("sources") or sorted(enabled)) if s in REGISTRY]
    options = get_setting(db, "source_options", {}) or {}
    for key, src in db.execute(select(JobSource.key, JobSource.config)).all():
        if src:
            options.setdefault(key, {}).update(src)
    q = SearchQuery(keywords=list(get("keywords") or []), locations=list(get("locations") or []),
                    include_remote=bool(get("include_remote", True)), posted_within_days=int(get("posted_within_days", 7) or 7),
                    experience_min=get("experience_min"), experience_max=get("experience_max"),
                    min_salary_monthly=get("min_salary_monthly"), options=options)
    return q, sources, sp


def search_task(task_id: int, params: dict, progress) -> dict:
    with session_scope() as db:
        q, sources, sp = query_from(db, params)
        if sp:
            sp.last_run_at = datetime.utcnow()
        high = int(get_setting(db, "high_match_threshold", 75))
    http = PoliteClient()
    summary, links, new_ids, high_ids = {}, [], [], []
    try:
        for i, key in enumerate(sources):
            adapter = REGISTRY[key]
            progress(int(90 * i / max(1, len(sources))), f"Searching {adapter.name}")
            if not adapter.supports_search:
                links += adapter.search_links(q)
                summary[key] = {"status": "assisted", "found": 0, "new": 0, "kept": 0,
                                "message": "Open the search links in your browser, then import jobs you like."}
                continue
            try:
                raws = adapter.search(q, http)
                status, message = "ok", ""
            except SourceError as e:
                raws, status, message = [], "error", str(e)
            except Exception as e:  # network errors, API changes
                raws, status, message = [], "error", f"{type(e).__name__}: {e}"
            kept = new = 0
            with session_scope() as db:
                cand, _ = candidate(db)
                for raw in raws[: q.max_results * 3]:
                    try:
                        job, is_new = upsert_job(db, raw)
                    except ValueError:
                        continue
                    if not adapter.server_side_filtering and is_new and not passes_filters(job, q):
                        db.delete(job)          # outside the search - don't keep it
                        db.flush()
                        continue
                    kept += 1
                    score_job(job, cand)
                    if is_new:
                        new += 1
                        new_ids.append(job.id)
                        if job.match_score is not None and job.match_score >= high:
                            high_ids.append(job.id)
                            notify_high_match(db, job)
                src = db.scalar(select(JobSource).where(JobSource.key == key))
                if src:
                    src.last_run_at, src.last_status, src.last_count = datetime.utcnow(), (message or "ok")[:500], kept
            summary[key] = {"status": status, "found": len(raws), "kept": kept, "new": new, "message": message}
    finally:
        http.close()
    return {"sources": summary, "new_jobs": len(new_ids), "high_matches": len(high_ids), "new_job_ids": new_ids[:200],
            "high_match_ids": high_ids, "assisted_links": links}


def notify_high_match(db: Session, job: Job) -> None:
    db.add(Notification(kind="high_match", title="🔥 NEW HIGH MATCH JOB", job_id=job.id, body={
        "company": job.company, "role": job.title, "location": job.location, "match": job.match_score,
        "salary": job.salary_text or format_salary(job.salary_min, job.salary_max, job.salary_currency) or "Not disclosed",
        "posted": job.posted_date.isoformat() if job.posted_date else "", "application_url": job.application_url or job.job_url}))


def import_raw_jobs(db: Session, raws: list[RawJob]) -> list[tuple[Job, bool]]:
    cand, _ = candidate(db)
    high = int(get_setting(db, "high_match_threshold", 75))
    out = []
    for raw in raws:
        job, is_new = upsert_job(db, raw)
        score_job(job, cand)
        if is_new and job.status == "New":
            job.status = "Saved"          # imported by hand = the user is interested
        if is_new and job.match_score >= high:
            notify_high_match(db, job)
        out.append((job, is_new))
    return out


# ---------------------------------------------------------------- JD analysis

SCAM_RE = re.compile(r"registration fee|security deposit|refundable deposit|processing fee|pay (?:for|to) (?:training|"
                     r"registration|joining)|training fee|investment (?:is )?required|whatsapp only|no interview", re.I)


def analyze_jd(job: Job) -> dict:
    text = job.description or ""
    lines = [l.strip(" -•*\t") for l in text.splitlines() if l.strip()]
    resp = [l for l in lines if re.match(r"(prepare|build|develop|create|manage|maintain|analy|track|work|design|own|"
                                         r"automate|ensure|coordinate|support|monitor|generate|present)", l, re.I)][:12]
    flags = []
    if SCAM_RE.search(text):
        flags.append("Mentions paying a fee/deposit or similar. Genuine employers don't charge candidates. Verify first.")
    if len(text) < 300:
        flags.append("Very short description; details may be missing.")
    if not job.company:
        flags.append("Company name is missing.")
    seniority = ("Senior" if re.search(r"\b(senior|sr\.?|lead|manager)\b", job.title, re.I) else
                 "Junior/Entry" if re.search(r"\b(junior|jr\.?|trainee|intern|fresher)\b", job.title, re.I) else "Mid")
    return {
        "role_category": role_category(job.title), "seniority": seniority,
        "required_skills": sorted(find_skills(f"{job.title}\n{text}")),
        "keywords": jd_keywords(text, 30),
        "requirements": ats._requirements(text),
        "responsibilities": resp,
        "experience": {"min": job.experience_min, "max": job.experience_max},
        "education": job.education, "salary": job.salary_text or format_salary(job.salary_min, job.salary_max, job.salary_currency),
        "employment_type": job.employment_type, "notice_period": job.notice_period,
        "remote": job.remote, "red_flags": flags,
    }


# ---------------------------------------------------------------- resume analysis / tailoring

def ats_for(resume: Resume, job: Job | None = None, text: str | None = None, parsed: dict | None = None) -> dict:
    return ats.analyze(parsed or resume.parsed, text if text is not None else resume.raw_text, resume.format_info,
                       f"{job.title}\n{job.description}" if job else "", job.title if job else "")


def create_resume_version(db: Session, resume: Resume, job: Job | None, use_ai: bool = True) -> ResumeVersion:
    profile = get_profile(db)
    ai = ai_provider(db) if use_ai else None
    result = tailor.optimize(resume.parsed, profile, job, ai=ai, source_text=resume.raw_text + "\n" +
                             " ".join(profile.skills or []) + "\n" + (profile.summary or ""))
    content = result["resume"]
    text = export.to_text(content)
    # formatting of the generated file is ATS-clean by construction
    analysis = ats.analyze({**resume.parsed, "skills": content["skills_core"] + content["skills"],
                            "summary": content["summary"],
                            "experience": [{**e, "responsibilities": e["bullets"]} for e in content["experience"]],
                            "sections_found": sorted(set(resume.parsed.get("sections_found", [])) | {"summary", "skills"})},
                           text, {"file_type": "docx"}, f"{job.title}\n{job.description}" if job else "",
                           job.title if job else "")
    kind = "job" if job else "ats_general"
    version = (db.scalar(select(func.max(ResumeVersion.version)).where(
        ResumeVersion.resume_id == resume.id,
        ResumeVersion.job_id == job.id if job else ResumeVersion.job_id.is_(None))) or 0) + 1
    base = export.file_base(profile.full_name, job.title if job else "ATS_Optimized", job.company if job else "", version)
    folder = get_settings().storage_dir / "resumes"
    folder.mkdir(parents=True, exist_ok=True)
    docx_path, pdf_path = folder / f"{base}.docx", folder / f"{base}.pdf"
    docx_path.write_bytes(export.to_docx(content))
    pdf_path.write_bytes(export.to_pdf(content))
    rv = ResumeVersion(resume_id=resume.id, job_id=job.id if job else None, kind=kind, version=version,
                       company=job.company if job else "", role=job.title if job else "ATS optimized",
                       filename_base=base, ats_score=analysis["ats_score"], keywords_added=result["keywords_added"],
                       content={**content, "ai_used": result["ai_used"], "ats": analysis},
                       changes=result["changes"], docx_path=str(docx_path), pdf_path=str(pdf_path))
    db.add(rv)
    db.flush()
    if job is not None:
        job.ats_score = analysis["ats_score"]
        app = job.application
        if app is not None:
            app.resume_version_id = rv.id
            if app.status in ("Saved", "Shortlisted"):
                app.status = "Resume Tailored"
    return rv


# ---------------------------------------------------------------- communications

def generate_communications(db: Session, job: Job, channels: list[str], contact_id: int | None = None,
                            use_ai: bool = True) -> list[Communication]:
    cand, resume = candidate(db)
    contact = db.get(Contact, contact_id) if contact_id else db.scalar(
        select(Contact).where(or_(Contact.job_id == job.id, (Contact.company == job.company) & (Contact.company != "")))
        .order_by(Contact.id.desc()))
    if contact is None and job.hr_name:
        contact = Contact(name=job.hr_name, email=job.hr_email, company=job.company)  # transient, not saved
    match = job.match_details or score_job(job, cand)
    ai = ai_provider(db) if use_ai else None
    out = []
    for ch in channels:
        d = communications.generate(ch, cand, job, match, resume.parsed if resume else None, contact, ai,
                                    resume.raw_text if resume else "")
        c = Communication(job_id=job.id, application_id=job.application.id if job.application else None,
                          contact_id=contact.id if contact is not None and contact.id else None, channel=ch,
                          subject=d.get("subject", ""), body=d["body"], generated_by=d["generated_by"])
        db.add(c)
        out.append(c)
    db.flush()
    return out


# ---------------------------------------------------------------- applications

def ensure_application(db: Session, job: Job, status: str = "Saved") -> Application:
    if job.application is None:
        app = Application(job_id=job.id, status=status)
        db.add(app)
        job.application = app
        db.flush()
    return job.application


def set_status(db: Session, app: Application, status: str) -> Application:
    if status not in APP_STATUSES:
        raise ValueError(f"Unknown status {status}")
    app.status = status
    if status == "Applied" and not app.applied_date:
        app.applied_date = date.today()
        followups.schedule_followups(db, app)
    if status == "HR Contacted" and not app.applied_date:
        app.applied_date = date.today()
        followups.schedule_followups(db, app)
    if status in STOP_FOLLOWUPS:
        followups.cancel_pending(app, f"Status changed to {status}")
    if status in ("Interview", "Assessment", "Offer"):
        app.response_received = True
    return app


def mark_applied(db: Session, job: Job, resume_version_id: int | None = None, applied_on: date | None = None) -> Application:
    app = ensure_application(db, job)
    if resume_version_id:
        app.resume_version_id = resume_version_id
    elif app.resume_version_id is None:
        latest = db.scalar(select(ResumeVersion).where(ResumeVersion.job_id == job.id).order_by(ResumeVersion.id.desc()))
        app.resume_version_id = latest.id if latest else None
    if applied_on:
        app.applied_date = applied_on
    set_status(db, app, "Applied")
    job.status = "Applied"
    return app


# ---------------------------------------------------------------- one-click application kit

KIT_STEPS = ["Analyze JD", "Calculate match", "Analyze current resume", "Generate tailored resume",
             "Generate cover letter", "Generate HR email", "Generate WhatsApp message",
             "Generate LinkedIn connection note", "Generate LinkedIn DM", "Save to application record"]


def kit_task(task_id: int, params: dict, progress) -> dict:
    job_id, use_ai = params["job_id"], params.get("use_ai", True)
    out: dict = {"job_id": job_id, "steps": []}
    with session_scope() as db:
        job = db.get(Job, job_id)
        if job is None:
            raise ValueError(f"Job {job_id} not found")
        resume = master_resume(db)

        def step(i: int):
            db.commit()   # release SQLite's write lock so the progress update can be written
            progress(int(100 * i / len(KIT_STEPS)), KIT_STEPS[i])
            out["steps"].append(KIT_STEPS[i])

        step(0)
        jd = analyze_jd(job)
        db.add(AIAnalysis(job_id=job.id, kind="jd", result=jd))
        step(1)
        cand, _ = candidate(db)
        match = score_job(job, cand)
        step(2)
        if resume is None:
            raise ValueError("Upload your master resume first (Resume page).")
        resume_ats = ats_for(resume, job)
        db.add(AIAnalysis(job_id=job.id, resume_id=resume.id, kind="ats", result=resume_ats))
        app = ensure_application(db, job)
        step(3)
        rv = create_resume_version(db, resume, job, use_ai=use_ai)
        comm_ids = {}
        for i, ch in enumerate(["cover_letter", "email", "whatsapp", "linkedin_note", "linkedin_dm"], start=4):
            step(i)
            comm_ids[ch] = generate_communications(db, job, [ch], use_ai=use_ai)[0].id
        step(9)
        app.resume_version_id = rv.id
        if app.status in ("Saved", "Shortlisted"):
            app.status = "Resume Tailored"
        if job.status == "New":
            job.status = "Shortlisted"
        kit = {"jd": jd, "match": match, "resume_ats": resume_ats, "resume_version_id": rv.id,
               "tailored_ats": rv.ats_score, "communication_ids": comm_ids, "application_id": app.id}
        db.add(AIAnalysis(job_id=job.id, resume_id=resume.id, kind="kit", result=kit,
                          provider=ai_provider(db).name if use_ai else "rules"))
        out.update(kit)
    return out


def latest_kit(db: Session, job_id: int) -> dict | None:
    row = db.scalar(select(AIAnalysis).where(AIAnalysis.job_id == job_id, AIAnalysis.kind == "kit")
                    .order_by(AIAnalysis.id.desc()))
    return row.result if row else None


def storage_path(p: str) -> Path:
    path = Path(p).resolve()
    root = get_settings().storage_dir.resolve()
    if root not in path.parents:
        raise ValueError("File outside storage")
    return path
