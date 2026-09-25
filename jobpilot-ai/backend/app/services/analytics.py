"""Dashboard numbers and application metrics. Descriptive only - no predictions about hiring outcomes."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Application, Communication, Contact, Followup, Job, Setting

APPLIED_STATES = {"Applied", "HR Contacted", "Interview", "Assessment", "Rejected", "Offer", "Closed"}
RESPONSE_STATES = {"Interview", "Assessment", "Offer"}
INTERVIEW_STATES = {"Interview", "Assessment", "Offer"}
FUNNEL = ["Discovered", "Shortlisted", "Resume Tailored", "Applied", "HR Contacted", "Interview", "Offer"]


def _threshold(db: Session, key: str, default: int) -> int:
    row = db.get(Setting, key)
    return int(row.value) if row and row.value is not None else default


def responded(app: Application) -> bool:
    return app.response_received or app.status in RESPONSE_STATES


def _rate(n: int, d: int) -> float:
    return round(100 * n / d, 1) if d else 0.0


def dashboard(db: Session) -> dict:
    today = date.today()
    start_today = datetime.combine(today, datetime.min.time())
    high = _threshold(db, "high_match_threshold", 75)
    relevant = _threshold(db, "relevant_threshold", 60)
    apps = list(db.scalars(select(Application)))
    applied = [a for a in apps if a.status in APPLIED_STATES]
    return {
        "jobs_found_today": db.scalar(select(func.count(Job.id)).where(Job.created_at >= start_today)) or 0,
        "jobs_total": db.scalar(select(func.count(Job.id))) or 0,
        "relevant_jobs": db.scalar(select(func.count(Job.id)).where(Job.match_score >= relevant)) or 0,
        "high_match_jobs": db.scalar(select(func.count(Job.id)).where(Job.match_score >= high)) or 0,
        "applications": len(applied),
        "hr_contacts": db.scalar(select(func.count(Contact.id))) or 0,
        "interviews": sum(1 for a in apps if a.status in INTERVIEW_STATES),
        "offers": sum(1 for a in apps if a.status == "Offer"),
        "response_rate": _rate(sum(1 for a in applied if responded(a)), len(applied)),
        "followups_due": db.scalar(select(func.count(Followup.id)).where(Followup.status == "pending",
                                                                          Followup.due_date <= today)) or 0,
        "thresholds": {"high": high, "relevant": relevant},
    }


def analytics(db: Session, weeks: int = 12) -> dict:
    jobs = list(db.scalars(select(Job)))
    apps = list(db.scalars(select(Application)))
    applied = [a for a in apps if a.status in APPLIED_STATES]
    comms_sent = db.scalar(select(func.count(Communication.id)).where(Communication.status == "sent")) or 0
    contacted = [a for a in apps if a.status == "HR Contacted" or a.communication_sent]
    interviews = [a for a in apps if a.status in INTERVIEW_STATES]
    job_by_id = {j.id: j for j in jobs}

    # weekly applications
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    weekly = []
    for i in range(weeks - 1, -1, -1):
        wk = monday - timedelta(weeks=i)
        weekly.append({"week": wk.isoformat(),
                       "applications": sum(1 for a in applied if a.applied_date and wk <= a.applied_date < wk + timedelta(days=7)),
                       "jobs_found": sum(1 for j in jobs if j.created_at and wk <= j.created_at.date() < wk + timedelta(days=7))})

    bins = [(0, 40), (40, 50), (50, 60), (60, 70), (70, 80), (80, 90), (90, 101)]
    dist = [{"range": f"{lo}-{min(hi, 100)}", "count": sum(1 for j in jobs if j.match_score is not None and lo <= j.match_score < hi)}
            for lo, hi in bins]

    shortlisted = {j.id for j in jobs if j.status in ("Shortlisted", "Saved")} | {a.job_id for a in apps}
    tailored = {a.job_id for a in apps if a.resume_version_id} | {a.job_id for a in apps if a.status == "Resume Tailored"}
    funnel_counts = {
        "Discovered": len(jobs), "Shortlisted": len(shortlisted), "Resume Tailored": len(tailored),
        "Applied": len(applied), "HR Contacted": len(contacted), "Interview": len(interviews),
        "Offer": sum(1 for a in apps if a.status == "Offer"),
    }

    def rate_by(key_fn):
        groups: dict[str, list[Application]] = defaultdict(list)
        for a in applied:
            j = job_by_id.get(a.job_id)
            if j:
                groups[key_fn(j)].append(a)
        return [{"name": k, "applications": len(v), "responses": sum(1 for a in v if responded(a)),
                 "response_rate": _rate(sum(1 for a in v if responded(a)), len(v))}
                for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1]))]

    status_counts = Counter(a.status for a in apps)
    return {
        "totals": {"jobs_discovered": len(jobs), "jobs_shortlisted": len(shortlisted), "applications": len(applied),
                   "hr_contacts": len(contacted), "messages_sent": comms_sent,
                   "responses": sum(1 for a in applied if responded(a)), "interviews": len(interviews),
                   "offers": funnel_counts["Offer"]},
        "rates": {
            "application_rate": _rate(len(applied), len(shortlisted)),
            "hr_response_rate": _rate(sum(1 for a in applied if responded(a)), len(applied)),
            "interview_conversion_rate": _rate(len(interviews), len(applied)),
        },
        "weekly": weekly,
        "jobs_by_source": [{"name": k, "count": v} for k, v in Counter(j.source for j in jobs).most_common()],
        "jobs_by_role": [{"name": k, "count": v} for k, v in Counter(j.role_category for j in jobs).most_common()],
        "match_distribution": dist,
        "funnel": [{"stage": s, "count": funnel_counts[s]} for s in FUNNEL],
        "status_counts": dict(status_counts),
        "source_response": rate_by(lambda j: j.source),
        "role_response": rate_by(lambda j: j.role_category),
        "note": "Rates describe your own history so far. They are not predictions.",
    }
