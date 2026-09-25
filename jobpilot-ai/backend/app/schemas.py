"""Pydantic request/response models."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- jobs

class JobOut(ORM):
    id: int
    source: str
    source_job_id: str
    job_url: str
    company: str
    title: str
    location: str
    remote: bool | None
    salary_min: float | None
    salary_max: float | None
    salary_currency: str
    salary_text: str
    experience_min: float | None
    experience_max: float | None
    employment_type: str
    posted_date: date | None
    scraped_at: datetime
    created_at: datetime
    skills: list[str]
    education: str
    notice_period: str
    application_url: str
    hr_name: str
    hr_email: str
    company_website: str
    role_category: str
    match_score: int | None
    ats_score: int | None
    status: str
    notes: str
    application_status: str | None = None
    application_id: int | None = None


class JobDetail(JobOut):
    description: str
    match_details: dict


class JobList(BaseModel):
    items: list[JobOut]
    total: int
    page: int
    page_size: int


class JobCreate(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    company: str = ""
    location: str = ""
    description: str = ""
    job_url: str = ""
    salary_text: str = ""
    experience_text: str = ""
    employment_type: str = ""
    remote: bool | None = None
    hr_name: str = ""
    hr_email: str = ""


class JobUpdate(BaseModel):
    status: str | None = None
    notes: str | None = None
    hr_name: str | None = None
    hr_email: str | None = None
    company_website: str | None = None
    application_url: str | None = None
    title: str | None = None
    company: str | None = None
    location: str | None = None
    description: str | None = None


class ImportUrl(BaseModel):
    url: str


class ImportPage(BaseModel):
    """Sent by the browser bookmarklet from a page the user is viewing."""
    url: str = ""
    title: str = ""
    text: str = ""
    jsonld: list[Any] = []
    company: str = ""
    location: str = ""


class SearchRequest(BaseModel):
    search_profile_id: int | None = None
    keywords: list[str] | None = None
    locations: list[str] | None = None
    experience_min: float | None = None
    experience_max: float | None = None
    include_remote: bool | None = None
    min_salary_monthly: int | None = None
    posted_within_days: int | None = None
    sources: list[str] | None = None


class ApplyRequest(BaseModel):
    resume_version_id: int | None = None
    applied_on: date | None = None


class GenerateComms(BaseModel):
    channels: list[Literal["email", "whatsapp", "linkedin_note", "linkedin_dm", "cover_letter"]] = \
        ["email", "whatsapp", "linkedin_note", "linkedin_dm", "cover_letter"]
    contact_id: int | None = None
    use_ai: bool = True


# ---------------------------------------------------------------- resumes

class ResumeOut(ORM):
    id: int
    filename: str
    file_type: str
    is_master: bool
    ats_score: int | None
    created_at: datetime
    parsed: dict
    format_info: dict


class ResumeVersionOut(ORM):
    id: int
    resume_id: int
    job_id: int | None
    kind: str
    version: int
    company: str
    role: str
    filename_base: str
    ats_score: int | None
    keywords_added: list[str]
    changes: list[str]
    content: dict
    created_at: datetime


class AnalyzeRequest(BaseModel):
    resume_id: int | None = None
    job_id: int | None = None
    jd_text: str = ""
    job_title: str = ""


class TailorRequest(BaseModel):
    resume_id: int | None = None
    job_id: int | None = None      # omit for a general ATS-optimised version
    use_ai: bool = True


# ---------------------------------------------------------------- applications / contacts / comms / follow-ups

class ApplicationOut(ORM):
    id: int
    job_id: int
    status: str
    applied_date: date | None
    last_followup_date: date | None
    next_followup_date: date | None
    resume_version_id: int | None
    response_received: bool
    communication_sent: list[str]
    notes: str
    created_at: datetime
    updated_at: datetime
    job_title: str = ""
    company: str = ""
    location: str = ""
    source: str = ""
    match_score: int | None = None
    resume_version_name: str = ""


class ApplicationCreate(BaseModel):
    job_id: int
    status: str = "Saved"
    notes: str = ""


class ApplicationUpdate(BaseModel):
    status: str | None = None
    applied_date: date | None = None
    notes: str | None = None
    response_received: bool | None = None
    resume_version_id: int | None = None
    next_followup_date: date | None = None


class ContactIn(BaseModel):
    job_id: int | None = None
    company: str = ""
    name: str = ""
    role_title: str = "HR"
    email: str = ""
    phone: str = ""
    linkedin_url: str = ""
    career_page: str = ""
    source_note: str = ""
    notes: str = ""

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip()
        if v and ("@" not in v or " " in v):
            raise ValueError("Invalid email address")
        return v


class ContactOut(ContactIn, ORM):
    id: int
    created_at: datetime


class CommunicationOut(ORM):
    id: int
    job_id: int | None
    application_id: int | None
    contact_id: int | None
    channel: str
    subject: str
    body: str
    status: str
    generated_by: str
    sent_at: datetime | None
    created_at: datetime
    job_title: str = ""
    company: str = ""


class CommunicationUpdate(BaseModel):
    subject: str | None = None
    body: str | None = None
    # marking as sent requires explicit confirmation from the user
    mark_sent: bool = False
    confirm: bool = False


class FollowupOut(ORM):
    id: int
    application_id: int
    job_id: int | None
    day_offset: int
    due_date: date
    channel: str
    label: str
    status: str
    completed_at: datetime | None
    note: str
    job_title: str = ""
    company: str = ""
    overdue: bool = False


class FollowupUpdate(BaseModel):
    status: Literal["pending", "done", "skipped"] | None = None
    due_date: date | None = None
    note: str | None = None


# ---------------------------------------------------------------- search profiles / profile / settings

class SearchProfileIn(BaseModel):
    name: str
    keywords: list[str] = []
    locations: list[str] = []
    experience_min: float | None = None
    experience_max: float | None = None
    include_remote: bool = True
    min_salary_monthly: int | None = None
    posted_within_days: int = 7
    sources: list[str] = []
    enabled: bool = True
    auto_run: bool = False
    interval_hours: int = Field(12, ge=1, le=168)


class SearchProfileOut(SearchProfileIn, ORM):
    id: int
    last_run_at: datetime | None


class ProfileIn(BaseModel):
    full_name: str
    headline: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin_url: str = ""
    summary: str = ""
    total_experience_years: float | None = None
    current_salary_monthly: int | None = None
    expected_salary_monthly: int | None = None
    notice_period: str = ""
    education: list[str] = []
    target_roles: list[str] = []
    skills: list[str] = []
    preferred_locations: list[str] = []
    open_to_remote: bool = True
    open_to_relocation_if_relevant: bool = True


class ProfileOut(ProfileIn, ORM):
    id: int


class SettingsIn(BaseModel):
    high_match_threshold: int | None = Field(None, ge=0, le=100)
    relevant_threshold: int | None = Field(None, ge=0, le=100)
    followup_schedule: list[dict] | None = None
    ai: dict | None = None
    source_options: dict | None = None


class SourceUpdate(BaseModel):
    enabled: bool | None = None
    config: dict | None = None


class TaskOut(ORM):
    id: int
    kind: str
    status: str
    progress: int
    message: str
    params: dict
    result: dict | None
    error: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class NotificationOut(ORM):
    id: int
    kind: str
    title: str
    body: dict
    job_id: int | None
    read: bool
    created_at: datetime
