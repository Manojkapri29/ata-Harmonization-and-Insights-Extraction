from __future__ import annotations

from datetime import date, datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Application, Communication, Contact, Followup, Job
from ..schemas import (ApplicationCreate, ApplicationOut, ApplicationUpdate, CommunicationOut, CommunicationUpdate,
                       ContactIn, ContactOut, FollowupOut, FollowupUpdate)
from ..services import communications as comms
from ..services import followups as fu_service
from ..services import pipeline
from .common import app_out, comm_out, followup_out

router = APIRouter(prefix="/api", tags=["tracking"])


# ---------------------------------------------------------------- applications

@router.get("/applications", response_model=list[ApplicationOut])
def list_applications(status: str = "", q: str = "", db: Session = Depends(get_db)):
    stmt = select(Application).join(Job).order_by(Application.updated_at.desc())
    if status:
        stmt = stmt.where(Application.status.in_(status.split(",")))
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Job.title).like(like), func.lower(Job.company).like(like)))
    return [app_out(a, db) for a in db.scalars(stmt)]


@router.post("/applications", response_model=ApplicationOut, status_code=201)
def create_application(body: ApplicationCreate, db: Session = Depends(get_db)):
    job = db.get(Job, body.job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    app = pipeline.ensure_application(db, job)
    try:
        pipeline.set_status(db, app, body.status)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    app.notes = body.notes or app.notes
    db.commit()
    return app_out(app, db)


def _app(db: Session, app_id: int) -> Application:
    app = db.get(Application, app_id)
    if app is None:
        raise HTTPException(404, "Application not found")
    return app


@router.get("/applications/{app_id}")
def get_application(app_id: int, db: Session = Depends(get_db)):
    app = _app(db, app_id)
    return {"application": app_out(app, db),
            "followups": [followup_out(f, db) for f in sorted(app.followups, key=lambda f: f.due_date)],
            "communications": [comm_out(c, db) for c in db.scalars(
                select(Communication).where(Communication.job_id == app.job_id).order_by(Communication.id.desc()))]}


@router.patch("/applications/{app_id}", response_model=ApplicationOut)
def update_application(app_id: int, body: ApplicationUpdate, db: Session = Depends(get_db)):
    app = _app(db, app_id)
    data = body.model_dump(exclude_unset=True)
    if "applied_date" in data:
        app.applied_date = data.pop("applied_date")
    if "status" in data:
        try:
            pipeline.set_status(db, app, data.pop("status"))
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        if app.status == "Applied":
            app.job.status = "Applied"
    for k, v in data.items():
        setattr(app, k, v)
    db.commit()
    return app_out(app, db)


@router.delete("/applications/{app_id}", status_code=204)
def delete_application(app_id: int, db: Session = Depends(get_db)):
    db.delete(_app(db, app_id))
    db.commit()


# ---------------------------------------------------------------- contacts (manually entered, public info only)

@router.get("/contacts", response_model=list[ContactOut])
def list_contacts(job_id: int | None = None, company: str = "", db: Session = Depends(get_db)):
    stmt = select(Contact).order_by(Contact.id.desc())
    if job_id:
        stmt = stmt.where(Contact.job_id == job_id)
    if company:
        stmt = stmt.where(func.lower(Contact.company) == company.lower())
    return list(db.scalars(stmt))


@router.post("/contacts", response_model=ContactOut, status_code=201)
def create_contact(body: ContactIn, db: Session = Depends(get_db)):
    c = Contact(**body.model_dump())
    if c.job_id and not c.company:
        job = db.get(Job, c.job_id)
        c.company = job.company if job else ""
    db.add(c)
    db.commit()
    return c


@router.patch("/contacts/{contact_id}", response_model=ContactOut)
def update_contact(contact_id: int, body: ContactIn, db: Session = Depends(get_db)):
    c = db.get(Contact, contact_id)
    if c is None:
        raise HTTPException(404, "Contact not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    db.commit()
    return c


@router.delete("/contacts/{contact_id}", status_code=204)
def delete_contact(contact_id: int, db: Session = Depends(get_db)):
    c = db.get(Contact, contact_id)
    if c is None:
        raise HTTPException(404, "Contact not found")
    db.delete(c)
    db.commit()


# ---------------------------------------------------------------- communications

@router.get("/communications", response_model=list[CommunicationOut])
def list_communications(channel: str = "", status: str = "", db: Session = Depends(get_db)):
    stmt = select(Communication).order_by(Communication.id.desc()).limit(500)
    if channel:
        stmt = stmt.where(Communication.channel.in_(channel.split(",")))
    if status:
        stmt = stmt.where(Communication.status == status)
    return [comm_out(c, db) for c in db.scalars(stmt)]


@router.patch("/communications/{comm_id}", response_model=CommunicationOut)
def update_communication(comm_id: int, body: CommunicationUpdate, db: Session = Depends(get_db)):
    """Edit a draft, or record that the user sent it. Marking as sent needs confirm=true (human confirmation)."""
    c = db.get(Communication, comm_id)
    if c is None:
        raise HTTPException(404, "Message not found")
    if body.subject is not None:
        c.subject = body.subject
    if body.body is not None:
        if c.channel == "linkedin_note" and len(body.body) > comms.LINKEDIN_NOTE_LIMIT:
            raise HTTPException(422, f"LinkedIn connection notes are limited to {comms.LINKEDIN_NOTE_LIMIT} characters.")
        c.body = body.body
    if body.mark_sent:
        if not body.confirm:
            raise HTTPException(409, "Confirm that you sent this message yourself (confirm=true).")
        c.status, c.sent_at = "sent", datetime.utcnow()
        job = db.get(Job, c.job_id) if c.job_id else None
        if job is not None and c.channel != "cover_letter":
            app = pipeline.ensure_application(db, job)
            if c.channel not in app.communication_sent:
                app.communication_sent = [*app.communication_sent, c.channel]
            if app.status in ("Saved", "Shortlisted", "Resume Tailored", "Applied"):
                pipeline.set_status(db, app, "HR Contacted")
    db.commit()
    return comm_out(c, db)


@router.get("/communications/{comm_id}/links")
def send_links(comm_id: int, db: Session = Depends(get_db)):
    """Links that open the user's own email/WhatsApp/LinkedIn with the draft filled in. Nothing is auto-sent."""
    c = db.get(Communication, comm_id)
    if c is None:
        raise HTTPException(404, "Message not found")
    contact = db.get(Contact, c.contact_id) if c.contact_id else None
    job = db.get(Job, c.job_id) if c.job_id else None
    email = (contact.email if contact else "") or (job.hr_email if job else "")
    phone = "".join(ch for ch in (contact.phone if contact else "") if ch.isdigit())
    if phone and len(phone) == 10:
        phone = "91" + phone
    links = {"mailto": f"mailto:{email}?subject={quote(c.subject)}&body={quote(c.body)}",
             "whatsapp": f"https://wa.me/{phone}?text={quote(c.body)}" if phone else f"https://wa.me/?text={quote(c.body)}",
             "linkedin": contact.linkedin_url if contact and contact.linkedin_url else ""}
    return links


@router.delete("/communications/{comm_id}", status_code=204)
def delete_communication(comm_id: int, db: Session = Depends(get_db)):
    c = db.get(Communication, comm_id)
    if c is None:
        raise HTTPException(404, "Message not found")
    db.delete(c)
    db.commit()


# ---------------------------------------------------------------- follow-ups

@router.get("/followups", response_model=list[FollowupOut])
def list_followups(status: str = "pending", due_only: bool = False, db: Session = Depends(get_db)):
    stmt = select(Followup).order_by(Followup.due_date)
    if status:
        stmt = stmt.where(Followup.status.in_(status.split(",")))
    if due_only:
        stmt = stmt.where(Followup.due_date <= date.today())
    return [followup_out(f, db) for f in db.scalars(stmt)]


@router.patch("/followups/{fu_id}", response_model=FollowupOut)
def update_followup(fu_id: int, body: FollowupUpdate, db: Session = Depends(get_db)):
    f = db.get(Followup, fu_id)
    if f is None:
        raise HTTPException(404, "Follow-up not found")
    if body.due_date:
        f.due_date = body.due_date
    if body.note is not None:
        f.note = body.note
    if body.status and body.status != "pending":
        fu_service.complete(db, f, body.status, body.note or "")
    elif body.status == "pending":
        f.status = "pending"
    fu_service.refresh_next(f.application)
    db.commit()
    return followup_out(f, db)


@router.post("/followups/{fu_id}/draft", response_model=CommunicationOut, status_code=201)
def followup_draft(fu_id: int, db: Session = Depends(get_db)):
    """Draft the follow-up message for this reminder."""
    f = db.get(Followup, fu_id)
    if f is None:
        raise HTTPException(404, "Follow-up not found")
    job = db.get(Job, f.job_id)
    cand, _ = pipeline.candidate(db)
    contact = db.scalar(select(Contact).where(or_(Contact.job_id == job.id, Contact.company == job.company))
                        .order_by(Contact.id.desc()))
    d = comms.followup(cand, job, f.day_offset, f.channel, contact)
    c = Communication(job_id=job.id, application_id=f.application_id, contact_id=contact.id if contact else None,
                      channel=d["channel"], subject=d.get("subject", ""), body=d["body"])
    db.add(c)
    db.commit()
    return comm_out(c, db)
