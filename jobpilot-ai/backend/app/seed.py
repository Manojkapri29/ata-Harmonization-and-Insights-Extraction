"""First-run data: the owner's profile (from the project brief), sources, a default search profile, settings.
Contact details are left blank on purpose - fill them in Settings so they never live in the code."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import JobSource, Profile, SearchProfile, Setting, User
from .services.followups import DEFAULT_SCHEDULE
from .services.sources import REGISTRY

DEFAULT_PROFILE = {
    "full_name": "Manoj Kapri",
    "headline": "MIS & Data Analyst | Advanced Excel | Power BI | SQL",
    "summary": "MIS and data analysis professional with 3+ years of experience in MIS reporting, management reporting, "
               "dashboard development and reporting automation using Advanced Excel, Power BI, SQL, Python, "
               "Power Query, Power Pivot and VBA/Macros.",
    "total_experience_years": 3.0,
    "current_salary_monthly": 42000,
    "expected_salary_monthly": None,
    "salary_currency": "INR",
    "notice_period": "Immediate Joiner",
    "education": ["MBA in Data Science & Analysis"],
    "target_roles": ["Data Analyst", "Business Analyst", "BI Analyst", "MIS Executive", "Reporting Analyst"],
    "skills": ["Advanced Excel", "MIS Reporting", "Management Reporting", "Dashboard Development", "Power BI", "SQL",
               "Data Analysis", "Data Validation", "Reporting Automation", "Python", "Power Query", "Power Pivot",
               "VBA/Macros"],
    "preferred_locations": ["Delhi NCR", "Noida", "Greater Noida", "Gurugram", "Remote"],
    "open_to_remote": True,
    "open_to_relocation_if_relevant": True,
}

DEFAULT_SEARCH = {
    "name": "Data / BI / MIS roles - Delhi NCR",
    "keywords": ["Data Analyst", "Business Analyst", "MIS Executive", "BI Analyst", "Reporting Analyst"],
    "locations": ["Delhi NCR", "Noida", "Greater Noida", "Gurugram"],
    "experience_min": 3, "experience_max": 5, "include_remote": True, "min_salary_monthly": None,
    "posted_within_days": 7, "auto_run": False, "interval_hours": 12,
}

DEFAULT_SETTINGS = {
    "high_match_threshold": 75,
    "relevant_threshold": 60,
    "followup_schedule": DEFAULT_SCHEDULE,
    "ai": {},
    "source_options": {},
}


def seed(db: Session) -> None:
    if db.scalar(select(User).limit(1)) is None:
        user = User(name=DEFAULT_PROFILE["full_name"])
        db.add(user)
        db.flush()
        db.add(Profile(user_id=user.id, **DEFAULT_PROFILE))
    existing = {s.key for s in db.scalars(select(JobSource))}
    for key, adapter in REGISTRY.items():
        if key not in existing:
            db.add(JobSource(key=key, name=adapter.name, kind=adapter.kind, enabled=adapter.default_enabled, config={}))
    if db.scalar(select(SearchProfile).limit(1)) is None:
        sources = [k for k, a in REGISTRY.items() if a.default_enabled]
        db.add(SearchProfile(sources=sources, **DEFAULT_SEARCH))
    for k, v in DEFAULT_SETTINGS.items():
        if db.get(Setting, k) is None:
            db.add(Setting(key=k, value=v))
    db.commit()
