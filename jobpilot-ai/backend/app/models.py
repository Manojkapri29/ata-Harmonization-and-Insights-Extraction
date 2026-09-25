"""Database tables. Portable SQLAlchemy types only, so SQLite -> PostgreSQL is a DATABASE_URL change."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(200))
    profile: Mapped[Profile | None] = relationship(back_populates="user", uselist=False)


class Profile(TimestampMixin, Base):
    __tablename__ = "profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    headline: Mapped[str] = mapped_column(String(300), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    location: Mapped[str] = mapped_column(String(200), default="")
    linkedin_url: Mapped[str] = mapped_column(String(300), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    total_experience_years: Mapped[float | None] = mapped_column(Float)
    current_salary_monthly: Mapped[int | None] = mapped_column(Integer)
    expected_salary_monthly: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str] = mapped_column(String(10), default="INR")
    notice_period: Mapped[str] = mapped_column(String(100), default="")
    education: Mapped[list] = mapped_column(JSON, default=list)        # ["MBA in Data Science & Analysis"]
    target_roles: Mapped[list] = mapped_column(JSON, default=list)
    skills: Mapped[list] = mapped_column(JSON, default=list)
    preferred_locations: Mapped[list] = mapped_column(JSON, default=list)
    open_to_remote: Mapped[bool] = mapped_column(Boolean, default=True)
    open_to_relocation_if_relevant: Mapped[bool] = mapped_column(Boolean, default=True)
    user: Mapped[User] = relationship(back_populates="profile")


class Resume(TimestampMixin, Base):
    __tablename__ = "resumes"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(300))
    file_type: Mapped[str] = mapped_column(String(10))
    file_path: Mapped[str] = mapped_column(String(500), default="")
    raw_text: Mapped[str] = mapped_column(Text, default="")
    parsed: Mapped[dict] = mapped_column(JSON, default=dict)
    format_info: Mapped[dict] = mapped_column(JSON, default=dict)
    ats_score: Mapped[int | None] = mapped_column(Integer)
    is_master: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    versions: Mapped[list[ResumeVersion]] = relationship(back_populates="resume", cascade="all, delete-orphan")


class ResumeVersion(Base):
    __tablename__ = "resume_versions"
    __table_args__ = (UniqueConstraint("resume_id", "job_id", "version", name="uq_resume_job_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="job")  # ats_general | job
    version: Mapped[int] = mapped_column(Integer, default=1)
    company: Mapped[str] = mapped_column(String(200), default="")
    role: Mapped[str] = mapped_column(String(200), default="")
    filename_base: Mapped[str] = mapped_column(String(300))
    ats_score: Mapped[int | None] = mapped_column(Integer)
    keywords_added: Mapped[list] = mapped_column(JSON, default=list)
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    changes: Mapped[list] = mapped_column(JSON, default=list)
    docx_path: Mapped[str] = mapped_column(String(500), default="")
    pdf_path: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    resume: Mapped[Resume] = relationship(back_populates="versions")


class JobSource(TimestampMixin, Base):
    __tablename__ = "job_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(20))        # api | feed | company | assisted | demo
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_status: Mapped[str] = mapped_column(String(500), default="")
    last_count: Mapped[int] = mapped_column(Integer, default=0)


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("source", "source_job_id", name="uq_job_source_id"),
        Index("ix_jobs_match_posted", "match_score", "posted_date"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(50), index=True)
    source_job_id: Mapped[str] = mapped_column(String(300))
    job_url: Mapped[str] = mapped_column(String(1000), default="")
    company: Mapped[str] = mapped_column(String(300), default="", index=True)
    title: Mapped[str] = mapped_column(String(300), index=True)
    location: Mapped[str] = mapped_column(String(300), default="")
    remote: Mapped[bool | None] = mapped_column(Boolean)
    salary_min: Mapped[float | None] = mapped_column(Float)     # annual
    salary_max: Mapped[float | None] = mapped_column(Float)     # annual
    salary_currency: Mapped[str] = mapped_column(String(10), default="")
    salary_text: Mapped[str] = mapped_column(String(200), default="")
    experience_min: Mapped[float | None] = mapped_column(Float)
    experience_max: Mapped[float | None] = mapped_column(Float)
    employment_type: Mapped[str] = mapped_column(String(50), default="")
    posted_date: Mapped[date | None] = mapped_column(Date, index=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    description: Mapped[str] = mapped_column(Text, default="")
    skills: Mapped[list] = mapped_column(JSON, default=list)
    education: Mapped[str] = mapped_column(String(300), default="")
    notice_period: Mapped[str] = mapped_column(String(100), default="")
    application_url: Mapped[str] = mapped_column(String(1000), default="")
    hr_name: Mapped[str] = mapped_column(String(200), default="")
    hr_email: Mapped[str] = mapped_column(String(200), default="")
    company_website: Mapped[str] = mapped_column(String(500), default="")
    role_category: Mapped[str] = mapped_column(String(50), default="Other", index=True)
    match_score: Mapped[int | None] = mapped_column(Integer, index=True)
    match_details: Mapped[dict] = mapped_column(JSON, default=dict)
    ats_score: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="New", index=True)  # New | Saved | Shortlisted | Ignored
    notes: Mapped[str] = mapped_column(Text, default="")
    dedupe_hash: Mapped[str] = mapped_column(String(64), index=True)
    job_skills: Mapped[list[JobSkill]] = relationship(back_populates="job", cascade="all, delete-orphan",
                                                       passive_deletes=True)
    application: Mapped[Application | None] = relationship(back_populates="job", uselist=False,
                                                           cascade="all, delete-orphan", passive_deletes=True)


class JobSkill(Base):
    __tablename__ = "job_skills"
    __table_args__ = (UniqueConstraint("job_id", "skill", name="uq_job_skill"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    skill: Mapped[str] = mapped_column(String(100), index=True)
    job: Mapped[Job] = relationship(back_populates="job_skills")


class Application(TimestampMixin, Base):
    __tablename__ = "applications"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(30), default="Saved", index=True)
    applied_date: Mapped[date | None] = mapped_column(Date, index=True)
    last_followup_date: Mapped[date | None] = mapped_column(Date)
    next_followup_date: Mapped[date | None] = mapped_column(Date, index=True)
    resume_version_id: Mapped[int | None] = mapped_column(ForeignKey("resume_versions.id", ondelete="SET NULL"))
    response_received: Mapped[bool] = mapped_column(Boolean, default=False)
    communication_sent: Mapped[list] = mapped_column(JSON, default=list)   # channels actually sent
    notes: Mapped[str] = mapped_column(Text, default="")
    job: Mapped[Job] = relationship(back_populates="application")
    followups: Mapped[list[Followup]] = relationship(back_populates="application", cascade="all, delete-orphan",
                                                     passive_deletes=True)


class Contact(TimestampMixin, Base):
    __tablename__ = "contacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"), index=True)
    company: Mapped[str] = mapped_column(String(300), default="", index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    role_title: Mapped[str] = mapped_column(String(200), default="HR")   # HR | Recruiter | Hiring Manager
    email: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    linkedin_url: Mapped[str] = mapped_column(String(300), default="")
    career_page: Mapped[str] = mapped_column(String(500), default="")
    source_note: Mapped[str] = mapped_column(String(300), default="")    # where this public info came from
    notes: Mapped[str] = mapped_column(Text, default="")


class Communication(TimestampMixin, Base):
    __tablename__ = "communications"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    application_id: Mapped[int | None] = mapped_column(ForeignKey("applications.id", ondelete="SET NULL"))
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"))
    channel: Mapped[str] = mapped_column(String(30), index=True)  # email|whatsapp|linkedin_note|linkedin_dm|cover_letter|followup_*
    subject: Mapped[str] = mapped_column(String(300), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")   # draft | sent
    generated_by: Mapped[str] = mapped_column(String(30), default="template")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)


class Followup(TimestampMixin, Base):
    __tablename__ = "followups"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    day_offset: Mapped[int] = mapped_column(Integer)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    channel: Mapped[str] = mapped_column(String(50))
    label: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending|done|skipped
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    note: Mapped[str] = mapped_column(Text, default="")
    application: Mapped[Application] = relationship(back_populates="followups")


class SearchProfile(TimestampMixin, Base):
    __tablename__ = "search_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    locations: Mapped[list] = mapped_column(JSON, default=list)
    experience_min: Mapped[float | None] = mapped_column(Float)
    experience_max: Mapped[float | None] = mapped_column(Float)
    include_remote: Mapped[bool] = mapped_column(Boolean, default=True)
    min_salary_monthly: Mapped[int | None] = mapped_column(Integer)
    posted_within_days: Mapped[int] = mapped_column(Integer, default=7)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_run: Mapped[bool] = mapped_column(Boolean, default=False)
    interval_hours: Mapped[int] = mapped_column(Integer, default=12)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime)


class AIAnalysis(Base):
    __tablename__ = "ai_analysis"
    __table_args__ = (Index("ix_ai_analysis_job_kind", "job_id", "kind"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    resume_id: Mapped[int | None] = mapped_column(ForeignKey("resumes.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(30))     # jd | match | ats | kit
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    provider: Mapped[str] = mapped_column(String(50), default="rules")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON)


class BackgroundTask(Base):
    __tablename__ = "background_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)  # queued|running|completed|failed
    progress: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(String(500), default="")
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30), default="high_match")
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[dict] = mapped_column(JSON, default=dict)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
