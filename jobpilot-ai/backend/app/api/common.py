from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from ..models import Application, Communication, Followup, Job, ResumeVersion
from ..schemas import ApplicationOut, CommunicationOut, FollowupOut, JobDetail, JobOut


def job_out(job: Job, detail: bool = False) -> JobOut | JobDetail:
    model = JobDetail if detail else JobOut
    out = model.model_validate(job)
    if job.application is not None:
        out.application_status = job.application.status
        out.application_id = job.application.id
    return out


def app_out(app: Application, db: Session) -> ApplicationOut:
    out = ApplicationOut.model_validate(app)
    job = app.job
    out.job_title, out.company, out.location, out.source = job.title, job.company, job.location, job.source
    out.match_score = job.match_score
    if app.resume_version_id:
        rv = db.get(ResumeVersion, app.resume_version_id)
        out.resume_version_name = rv.filename_base if rv else ""
    return out


def comm_out(c: Communication, db: Session) -> CommunicationOut:
    out = CommunicationOut.model_validate(c)
    if c.job_id:
        job = db.get(Job, c.job_id)
        if job:
            out.job_title, out.company = job.title, job.company
    return out


def followup_out(f: Followup, db: Session) -> FollowupOut:
    out = FollowupOut.model_validate(f)
    job = db.get(Job, f.job_id) if f.job_id else None
    if job:
        out.job_title, out.company = job.title, job.company
    out.overdue = f.status == "pending" and f.due_date < date.today()
    return out
