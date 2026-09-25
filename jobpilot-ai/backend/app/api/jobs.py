from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AIAnalysis, BackgroundTask, Communication, Job, ResumeVersion, SearchProfile
from ..schemas import (ApplyRequest, CommunicationOut, GenerateComms, ImportPage, ImportUrl, JobCreate, JobDetail,
                       JobList, JobOut, JobUpdate, ResumeVersionOut, SearchRequest, TaskOut)
from ..services import pipeline
from ..services.normalize import NCR, RawJob, cities_in
from ..services.sources import PoliteClient, SourceError
from ..services.sources.web_sources import import_from_page, import_from_url
from ..services.tasks import runner
from .common import comm_out, job_out

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

SORTS = {"match_score": Job.match_score, "posted_date": Job.posted_date, "created_at": Job.created_at,
         "salary_max": Job.salary_max, "company": Job.company, "title": Job.title}


def _get_job(db: Session, job_id: int) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job


@router.get("", response_model=JobList)
def list_jobs(db: Session = Depends(get_db), q: str = "", role: str = "", location: str = "", source: str = "",
              status: str = "", min_score: int | None = None, max_experience: float | None = None,
              min_salary_monthly: int | None = None, posted_within_days: int | None = None, remote: bool | None = None,
              sort: str = "match_score", order: str = "desc", page: int = Query(1, ge=1),
              page_size: int = Query(20, ge=1, le=200)):
    stmt = select(Job)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Job.title).like(like), func.lower(Job.company).like(like),
                              func.lower(Job.description).like(like)))
    if role:
        stmt = stmt.where(Job.role_category.in_(role.split(",")))
    if location:
        wanted = set()
        for l in location.split(","):
            wanted |= cities_in(l)
        if "Delhi NCR" in wanted:
            wanted |= NCR
        terms = {l.strip().lower() for l in location.split(",") if l.strip()} | {w.lower() for w in wanted if w != "Delhi NCR"}
        conds = [func.lower(Job.location).like(f"%{t}%") for t in terms if t != "remote"]
        if "remote" in terms:
            conds.append(Job.remote.is_(True))
        stmt = stmt.where(or_(*conds))
    if source:
        stmt = stmt.where(Job.source.in_(source.split(",")))
    if status:
        stmt = stmt.where(Job.status.in_(status.split(",")))
    if min_score is not None:
        stmt = stmt.where(Job.match_score >= min_score)
    if max_experience is not None:
        stmt = stmt.where(or_(Job.experience_min.is_(None), Job.experience_min <= max_experience))
    if min_salary_monthly:
        stmt = stmt.where(or_(Job.salary_max.is_(None), Job.salary_max >= min_salary_monthly * 12))
    if posted_within_days:
        since = date.today() - timedelta(days=posted_within_days)
        stmt = stmt.where(or_(Job.posted_date >= since, Job.posted_date.is_(None) & (Job.created_at >= since)))
    if remote is not None:
        stmt = stmt.where(Job.remote.is_(remote) if remote else or_(Job.remote.is_(False), Job.remote.is_(None)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    col = SORTS.get(sort, Job.match_score)
    direction = desc if order == "desc" else asc
    stmt = stmt.order_by(direction(col).nulls_last(), Job.id.desc()).offset((page - 1) * page_size).limit(page_size)
    return {"items": [job_out(j) for j in db.scalars(stmt)], "total": total, "page": page, "page_size": page_size}


@router.post("", response_model=JobDetail, status_code=201)
def create_job(body: JobCreate, db: Session = Depends(get_db)):
    """Manual job entry / paste a job description."""
    raw = RawJob(source="manual", title=body.title, company=body.company, location=body.location,
                 description=body.description, job_url=body.job_url, salary_text=body.salary_text,
                 experience_text=body.experience_text, employment_type=body.employment_type, remote=body.remote)
    job, _ = pipeline.import_raw_jobs(db, [raw])[0]
    job.hr_name = body.hr_name or job.hr_name
    job.hr_email = body.hr_email or job.hr_email
    db.commit()
    return job_out(job, detail=True)


@router.post("/search", response_model=TaskOut, status_code=202)
def search(body: SearchRequest, db: Session = Depends(get_db)):
    """Queue a background search across the configured sources. Poll /api/tasks/{id}."""
    params = {k: v for k, v in body.model_dump().items() if v is not None}
    if not params.get("search_profile_id") and not params.get("keywords"):
        sp = db.scalar(select(SearchProfile).where(SearchProfile.enabled).order_by(SearchProfile.id))
        if sp is None:
            raise HTTPException(400, "Create a search profile or pass keywords.")
        params["search_profile_id"] = sp.id
    task_id = runner.submit("search", params, pipeline.search_task)
    return _task(db, task_id)


def _task(db: Session, task_id: int):
    db.expire_all()
    return db.get(BackgroundTask, task_id)


@router.post("/import/url", response_model=list[JobDetail])
def import_url(body: ImportUrl, db: Session = Depends(get_db)):
    """Import one public job page by URL. robots.txt is respected; login-only pages must use the bookmarklet."""
    http = PoliteClient()
    try:
        raws = import_from_url(body.url.strip(), http)
    except SourceError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:
        raise HTTPException(422, f"Could not read that page: {type(e).__name__}: {e}") from e
    finally:
        http.close()
    jobs = [j for j, _ in pipeline.import_raw_jobs(db, raws)]
    db.commit()
    return [job_out(j, detail=True) for j in jobs]


@router.post("/import/page", response_model=list[JobDetail])
def import_page(body: ImportPage, db: Session = Depends(get_db)):
    """Browser-assisted import: the bookmarklet sends what's on the page the user is looking at."""
    try:
        raws = import_from_page(body.url, body.title, body.text, body.jsonld, body.company, body.location)
    except SourceError as e:
        raise HTTPException(422, str(e)) from e
    jobs = [j for j, _ in pipeline.import_raw_jobs(db, raws)]
    db.commit()
    return [job_out(j, detail=True) for j in jobs]


@router.post("/rescore")
def rescore(db: Session = Depends(get_db)):
    n = pipeline.rescore_all(db)
    db.commit()
    return {"rescored": n}


@router.get("/{job_id}", response_model=JobDetail)
def get_job(job_id: int, db: Session = Depends(get_db)):
    return job_out(_get_job(db, job_id), detail=True)


@router.patch("/{job_id}", response_model=JobDetail)
def update_job(job_id: int, body: JobUpdate, db: Session = Depends(get_db)):
    job = _get_job(db, job_id)
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(job, k, v)
    if changes.get("status") in ("Saved", "Shortlisted"):
        app = pipeline.ensure_application(db, job, changes["status"])
        if app.status in ("Saved", "Shortlisted"):
            app.status = changes["status"]
    if {"title", "description", "location"} & changes.keys():
        cand, _ = pipeline.candidate(db)
        pipeline.score_job(job, cand)
    db.commit()
    return job_out(job, detail=True)


@router.delete("/{job_id}", status_code=204)
def delete_job(job_id: int, db: Session = Depends(get_db)):
    db.delete(_get_job(db, job_id))
    db.commit()


@router.post("/{job_id}/analyze")
def analyze(job_id: int, db: Session = Depends(get_db)):
    job = _get_job(db, job_id)
    result = pipeline.analyze_jd(job)
    db.add(AIAnalysis(job_id=job.id, kind="jd", result=result))
    db.commit()
    return result


@router.post("/{job_id}/match")
def match(job_id: int, db: Session = Depends(get_db)):
    job = _get_job(db, job_id)
    cand, _ = pipeline.candidate(db)
    m = pipeline.score_job(job, cand)
    db.commit()
    return m


@router.post("/{job_id}/ats")
def ats_for_job(job_id: int, db: Session = Depends(get_db)):
    job = _get_job(db, job_id)
    resume = pipeline.master_resume(db)
    if resume is None:
        raise HTTPException(400, "Upload your master resume first.")
    result = pipeline.ats_for(resume, job)
    db.add(AIAnalysis(job_id=job.id, resume_id=resume.id, kind="ats", result=result))
    db.commit()
    return result


@router.post("/{job_id}/resume", response_model=ResumeVersionOut, status_code=201)
def tailor_resume(job_id: int, use_ai: bool = True, db: Session = Depends(get_db)):
    job = _get_job(db, job_id)
    resume = pipeline.master_resume(db)
    if resume is None:
        raise HTTPException(400, "Upload your master resume first.")
    pipeline.ensure_application(db, job)
    rv = pipeline.create_resume_version(db, resume, job, use_ai=use_ai)
    db.commit()
    return rv


@router.get("/{job_id}/resume", response_model=list[ResumeVersionOut])
def job_resumes(job_id: int, db: Session = Depends(get_db)):
    return list(db.scalars(select(ResumeVersion).where(ResumeVersion.job_id == job_id).order_by(ResumeVersion.id.desc())))


@router.get("/{job_id}/communications", response_model=list[CommunicationOut])
def job_comms(job_id: int, db: Session = Depends(get_db)):
    return [comm_out(c, db) for c in db.scalars(select(Communication).where(Communication.job_id == job_id)
                                                 .order_by(Communication.id.desc()))]


@router.post("/{job_id}/communications", response_model=list[CommunicationOut], status_code=201)
def generate_comms(job_id: int, body: GenerateComms, db: Session = Depends(get_db)):
    job = _get_job(db, job_id)
    comms = pipeline.generate_communications(db, job, list(body.channels), body.contact_id, body.use_ai)
    db.commit()
    return [comm_out(c, db) for c in comms]


@router.post("/{job_id}/kit", response_model=TaskOut, status_code=202)
def application_kit(job_id: int, use_ai: bool = True, db: Session = Depends(get_db)):
    """One-click Application Kit (background task)."""
    _get_job(db, job_id)
    if pipeline.master_resume(db) is None:
        raise HTTPException(400, "Upload your master resume first (Resume page).")
    task_id = runner.submit("kit", {"job_id": job_id, "use_ai": use_ai}, pipeline.kit_task)
    return _task(db, task_id)


@router.get("/{job_id}/kit")
def get_kit(job_id: int, db: Session = Depends(get_db)):
    kit = pipeline.latest_kit(db, job_id)
    if not kit:
        raise HTTPException(404, "No application kit yet")
    comms = {ch: comm_out(db.get(Communication, cid), db).model_dump(mode="json")
             for ch, cid in kit.get("communication_ids", {}).items() if db.get(Communication, cid)}
    rv = db.get(ResumeVersion, kit.get("resume_version_id") or 0)
    return {**kit, "communications": comms,
            "resume_version": ResumeVersionOut.model_validate(rv).model_dump(mode="json") if rv else None}


@router.post("/{job_id}/apply")
def mark_applied(job_id: int, body: ApplyRequest | None = None, db: Session = Depends(get_db)):
    """Record that YOU applied (JobPilot never submits applications). Schedules follow-ups."""
    job = _get_job(db, job_id)
    body = body or ApplyRequest()
    app = pipeline.mark_applied(db, job, body.resume_version_id, body.applied_on)
    db.commit()
    return {"application_id": app.id, "status": app.status, "applied_date": app.applied_date,
            "next_followup_date": app.next_followup_date,
            "followups": [{"day": f.day_offset, "due_date": f.due_date, "channel": f.channel, "label": f.label}
                          for f in app.followups]}
