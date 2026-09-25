from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..ai.providers import AIError
from ..config import get_settings
from ..db import get_db
from ..models import (Application, BackgroundTask, Communication, Contact, Job, JobSource, Notification, SearchProfile)
from ..schemas import (NotificationOut, ProfileIn, ProfileOut, SearchProfileIn, SearchProfileOut, SettingsIn,
                       SourceUpdate, TaskOut)
from ..services import analytics as analytics_service
from ..services import pipeline
from ..services.normalize import RawJob
from ..services.sources import REGISTRY, SearchQuery
from ..services.tasks import runner
from .common import app_out

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health():
    return {"status": "ok", "app": get_settings().app_name}


# ---------------------------------------------------------------- profile & settings

@router.get("/profile", response_model=ProfileOut)
def get_profile(db: Session = Depends(get_db)):
    return pipeline.get_profile(db)


@router.put("/profile", response_model=ProfileOut)
def put_profile(body: ProfileIn, db: Session = Depends(get_db)):
    p = pipeline.get_profile(db)
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    p.user.name = body.full_name
    pipeline.rescore_all(db)
    db.commit()
    return p


@router.get("/settings")
def get_settings_api(db: Session = Depends(get_db)):
    s = get_settings()
    ai = pipeline.ai_provider(db)
    return {
        "high_match_threshold": pipeline.get_setting(db, "high_match_threshold", 75),
        "relevant_threshold": pipeline.get_setting(db, "relevant_threshold", 60),
        "followup_schedule": pipeline.followups.get_schedule(db),
        "ai": pipeline.get_setting(db, "ai", {}),
        "ai_status": ai.describe(),
        "ai_env": {"provider": s.ai_provider, "openai_key_set": bool(s.openai_api_key),
                   "anthropic_key_set": bool(s.anthropic_api_key), "ollama_base_url": s.ollama_base_url,
                   "anthropic_model": s.anthropic_model, "openai_model": s.openai_model, "ollama_model": s.ollama_model},
        "source_options": pipeline.get_setting(db, "source_options", {}),
        "credentials": {"adzuna": bool(s.adzuna_app_id and s.adzuna_app_key)},
        "scheduler_enabled": s.scheduler_enabled,
    }


@router.put("/settings")
def put_settings(body: SettingsIn, db: Session = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    if "followup_schedule" in data:
        for step in data["followup_schedule"]:
            if "day" not in step or "channel" not in step:
                raise HTTPException(422, "Each follow-up step needs 'day' and 'channel'.")
            step["day"] = int(step["day"])
    if "ai" in data:
        # keys are never accepted here - they belong in backend/.env
        data["ai"] = {k: v for k, v in (data["ai"] or {}).items() if k in ("provider", "model", "base_url")}
    for k, v in data.items():
        pipeline.set_setting(db, k, v)
    db.commit()
    return get_settings_api(db)


@router.post("/settings/ai/test")
def test_ai(db: Session = Depends(get_db)):
    ai = pipeline.ai_provider(db)
    if not ai.available:
        return {"ok": False, "provider": ai.name, "message": "Not configured. Set AI_PROVIDER and its key in backend/.env."}
    try:
        text = ai.generate("Reply with exactly: OK", "Say OK", max_tokens=20)
        return {"ok": True, "provider": ai.name, "message": text.strip()[:100]}
    except AIError as e:
        return {"ok": False, "provider": ai.name, "message": str(e)}


# ---------------------------------------------------------------- sources

@router.get("/sources")
def list_sources(db: Session = Depends(get_db)):
    rows = {s.key: s for s in db.scalars(select(JobSource))}
    out = []
    for key, adapter in REGISTRY.items():
        row = rows.get(key)
        out.append({**adapter.meta(), "enabled": row.enabled if row else adapter.default_enabled,
                    "config": row.config if row else {}, "last_run_at": row.last_run_at if row else None,
                    "last_status": row.last_status if row else "", "last_count": row.last_count if row else 0})
    return out


@router.patch("/sources/{key}")
def update_source(key: str, body: SourceUpdate, db: Session = Depends(get_db)):
    row = db.scalar(select(JobSource).where(JobSource.key == key))
    if row is None:
        raise HTTPException(404, "Unknown source")
    if body.enabled is not None:
        row.enabled = body.enabled
    if body.config is not None:
        row.config = body.config
    db.commit()
    return {"key": key, "enabled": row.enabled, "config": row.config}


@router.get("/sources/links")
def assisted_links(search_profile_id: int | None = None, db: Session = Depends(get_db)):
    """Search links for browser-assisted boards (LinkedIn, Naukri, Indeed, ...)."""
    sp = db.get(SearchProfile, search_profile_id) if search_profile_id else \
        db.scalar(select(SearchProfile).order_by(SearchProfile.id))
    if sp is None:
        return []
    q = SearchQuery(keywords=sp.keywords, locations=sp.locations + (["Remote"] if sp.include_remote else []),
                    posted_within_days=sp.posted_within_days, experience_min=sp.experience_min)
    enabled = {s.key for s in db.scalars(select(JobSource).where(JobSource.enabled))}
    return [l for key, a in REGISTRY.items() if not a.supports_search and key in enabled for l in a.search_links(q)]


# ---------------------------------------------------------------- search profiles

@router.get("/search-profiles", response_model=list[SearchProfileOut])
def list_search_profiles(db: Session = Depends(get_db)):
    return list(db.scalars(select(SearchProfile).order_by(SearchProfile.id)))


@router.post("/search-profiles", response_model=SearchProfileOut, status_code=201)
def create_search_profile(body: SearchProfileIn, db: Session = Depends(get_db)):
    sp = SearchProfile(**body.model_dump())
    db.add(sp)
    db.commit()
    return sp


@router.put("/search-profiles/{sp_id}", response_model=SearchProfileOut)
def update_search_profile(sp_id: int, body: SearchProfileIn, db: Session = Depends(get_db)):
    sp = db.get(SearchProfile, sp_id)
    if sp is None:
        raise HTTPException(404, "Search profile not found")
    for k, v in body.model_dump().items():
        setattr(sp, k, v)
    db.commit()
    return sp


@router.delete("/search-profiles/{sp_id}", status_code=204)
def delete_search_profile(sp_id: int, db: Session = Depends(get_db)):
    sp = db.get(SearchProfile, sp_id)
    if sp is None:
        raise HTTPException(404, "Search profile not found")
    db.delete(sp)
    db.commit()


@router.post("/search-profiles/{sp_id}/run", response_model=TaskOut, status_code=202)
def run_search_profile(sp_id: int, db: Session = Depends(get_db)):
    if db.get(SearchProfile, sp_id) is None:
        raise HTTPException(404, "Search profile not found")
    task_id = runner.submit("search", {"search_profile_id": sp_id}, pipeline.search_task)
    db.expire_all()
    return db.get(BackgroundTask, task_id)


# ---------------------------------------------------------------- tasks & notifications

@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(limit: int = 20, db: Session = Depends(get_db)):
    return list(db.scalars(select(BackgroundTask).order_by(BackgroundTask.id.desc()).limit(limit)))


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: int, db: Session = Depends(get_db)):
    t = db.get(BackgroundTask, task_id)
    if t is None:
        raise HTTPException(404, "Task not found")
    return t


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(unread_only: bool = False, limit: int = 30, db: Session = Depends(get_db)):
    stmt = select(Notification).order_by(Notification.id.desc()).limit(limit)
    if unread_only:
        stmt = stmt.where(Notification.read.is_(False))
    return list(db.scalars(stmt))


@router.post("/notifications/{nid}/read", status_code=204)
def read_notification(nid: int, db: Session = Depends(get_db)):
    n = db.get(Notification, nid)
    if n:
        n.read = True
        db.commit()


@router.post("/notifications/read-all", status_code=204)
def read_all(db: Session = Depends(get_db)):
    db.execute(update(Notification).values(read=True))
    db.commit()


# ---------------------------------------------------------------- analytics

@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    return analytics_service.dashboard(db)


@router.get("/analytics")
def analytics(weeks: int = 12, db: Session = Depends(get_db)):
    return analytics_service.analytics(db, weeks)


# ---------------------------------------------------------------- import / export

JOB_COLS = ["id", "title", "company", "location", "remote", "source", "job_url", "application_url", "salary_text",
            "salary_min", "salary_max", "salary_currency", "experience_min", "experience_max", "employment_type",
            "posted_date", "match_score", "ats_score", "status", "role_category", "skills", "hr_name", "hr_email", "notes"]


def _rows(entity: str, db: Session) -> list[dict]:
    if entity == "jobs":
        return [{c: (", ".join(v) if isinstance(v := getattr(j, c), list) else v) for c in JOB_COLS}
                for j in db.scalars(select(Job).order_by(Job.id))]
    if entity == "applications":
        return [app_out(a, db).model_dump(mode="json", exclude={"communication_sent"}) |
                {"communication_sent": ", ".join(a.communication_sent)} for a in db.scalars(select(Application))]
    if entity == "contacts":
        return [{c: getattr(x, c) for c in ("id", "company", "name", "role_title", "email", "phone", "linkedin_url",
                                             "career_page", "source_note", "notes", "job_id")}
                for x in db.scalars(select(Contact))]
    if entity == "communications":
        return [{c: getattr(x, c) for c in ("id", "job_id", "channel", "subject", "body", "status", "generated_by",
                                             "sent_at", "created_at")} for x in db.scalars(select(Communication))]
    if entity == "analytics":
        a = analytics_service.analytics(db)
        rows = [{"metric": k, "value": v} for k, v in {**a["totals"], **a["rates"]}.items()]
        rows += [{"metric": f"source:{r['name']}:response_rate", "value": r["response_rate"]} for r in a["source_response"]]
        rows += [{"metric": f"role:{r['name']}:response_rate", "value": r["response_rate"]} for r in a["role_response"]]
        return rows
    raise HTTPException(404, "Unknown export")


@router.get("/export/{entity}")
def export(entity: str, format: str = "csv", db: Session = Depends(get_db)):
    rows = _rows(entity, db)
    if format == "json":
        return Response(json.dumps(rows, default=str, indent=2), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="jobpilot_{entity}.json"'})
    if format == "xlsx":
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = entity[:30]
        cols = list(rows[0].keys()) if rows else ["empty"]
        ws.append(cols)
        for r in rows:
            ws.append([str(r.get(c)) if isinstance(r.get(c), (dict, list)) else r.get(c) for c in cols])
        buf = io.BytesIO()
        wb.save(buf)
        return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="jobpilot_{entity}.xlsx"'})
    buf = io.StringIO()
    cols = list(rows[0].keys()) if rows else []
    w = csv.DictWriter(buf, fieldnames=cols)
    w.writeheader()
    w.writerows(rows)
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="jobpilot_{entity}.csv"'})


@router.post("/import/jobs")
async def import_jobs(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Import jobs from CSV / XLSX / JSON. Columns: title (required), company, location, description, job_url,
    salary_text, experience_text, employment_type, hr_name, hr_email."""
    name = (file.filename or "").lower()
    data = await file.read()
    try:
        if name.endswith(".json"):
            records = json.loads(data)
            records = records if isinstance(records, list) else records.get("jobs", [])
        elif name.endswith(".xlsx"):
            from openpyxl import load_workbook
            ws = load_workbook(io.BytesIO(data), read_only=True).active
            it = ws.iter_rows(values_only=True)
            header = [str(h or "").strip().lower() for h in next(it)]
            records = [dict(zip(header, row)) for row in it]
        else:
            records = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
    except Exception as e:
        raise HTTPException(422, f"Could not read file: {e}") from e
    raws, skipped = [], 0
    for r in records:
        r = {str(k).strip().lower(): ("" if v is None else str(v)) for k, v in r.items() if k}
        if not r.get("title"):
            skipped += 1
            continue
        raws.append(RawJob(source="import", title=r["title"], company=r.get("company", ""), location=r.get("location", ""),
                           description=r.get("description", ""), job_url=r.get("job_url") or r.get("url", ""),
                           salary_text=r.get("salary_text") or r.get("salary", ""),
                           experience_text=r.get("experience_text") or r.get("experience", ""),
                           employment_type=r.get("employment_type", "")))
    results = pipeline.import_raw_jobs(db, raws)
    db.commit()
    return {"imported": sum(1 for _, new in results if new), "updated": sum(1 for _, new in results if not new),
            "skipped": skipped}
