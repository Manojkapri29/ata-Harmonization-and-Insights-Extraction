"""Follow-up scheduling. Default: Day 0 apply, Day 3 LinkedIn/WhatsApp, Day 7 email, Day 14 final."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Application, Followup, Setting

DEFAULT_SCHEDULE = [
    {"day": 0, "channel": "application", "label": "Apply and send the HR email"},
    {"day": 3, "channel": "linkedin_whatsapp", "label": "LinkedIn / WhatsApp follow-up"},
    {"day": 7, "channel": "email", "label": "Email follow-up"},
    {"day": 14, "channel": "email_final", "label": "Final follow-up"},
]


def get_schedule(db: Session) -> list[dict]:
    row = db.get(Setting, "followup_schedule")
    sched = row.value if row and isinstance(row.value, list) and row.value else DEFAULT_SCHEDULE
    return sorted(sched, key=lambda s: int(s["day"]))


def schedule_followups(db: Session, app: Application, start: date | None = None) -> list[Followup]:
    start = start or app.applied_date or date.today()
    existing = {(f.day_offset, f.channel) for f in app.followups}
    created = []
    for step in get_schedule(db):
        day = int(step["day"])
        if day <= 0 or (day, step["channel"]) in existing:
            continue
        fu = Followup(application_id=app.id, job_id=app.job_id, day_offset=day, due_date=start + timedelta(days=day),
                      channel=step["channel"], label=step.get("label", ""), status="pending")
        db.add(fu)
        app.followups.append(fu)
        created.append(fu)
    refresh_next(app)
    return created


def refresh_next(app: Application) -> None:
    app.next_followup_date = min((f.due_date for f in app.followups if f.status == "pending"), default=None)


def complete(db: Session, fu: Followup, status: str = "done", note: str = "") -> Followup:
    fu.status = status
    fu.note = note or fu.note
    fu.completed_at = datetime.utcnow()
    if status == "done":
        fu.application.last_followup_date = date.today()
    refresh_next(fu.application)
    return fu


def cancel_pending(app: Application, reason: str) -> None:
    """Stop reminders once the process has moved on (interview, offer, rejection, closed)."""
    for f in app.followups:
        if f.status == "pending":
            f.status = "skipped"
            f.note = reason
    refresh_next(app)


def due(db: Session, until: date | None = None) -> list[Followup]:
    until = until or date.today()
    return list(db.scalars(select(Followup).where(Followup.status == "pending", Followup.due_date <= until)
                           .order_by(Followup.due_date)))
