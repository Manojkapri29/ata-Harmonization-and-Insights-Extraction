from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import AIAnalysis, Job, Resume, ResumeVersion
from ..schemas import AnalyzeRequest, ResumeOut, ResumeVersionOut, TailorRequest
from ..services import ats, pipeline
from ..services.resume_parser import extract_text, parse_resume

router = APIRouter(prefix="/api/resumes", tags=["resumes"])
MAX_BYTES = 5 * 1024 * 1024


def _resume(db: Session, resume_id: int | None) -> Resume:
    r = db.get(Resume, resume_id) if resume_id else pipeline.master_resume(db)
    if r is None:
        raise HTTPException(404 if resume_id else 400, "Resume not found" if resume_id else "Upload a resume first.")
    return r


@router.get("", response_model=list[ResumeOut])
def list_resumes(db: Session = Depends(get_db)):
    return list(db.scalars(select(Resume).order_by(Resume.id.desc())))


@router.post("", response_model=ResumeOut, status_code=201)
async def upload(file: UploadFile = File(...), make_master: bool = True, db: Session = Depends(get_db)):
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ("pdf", "docx", "txt"):
        raise HTTPException(415, "Upload a PDF, DOCX or TXT resume.")
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Resume must be under 5 MB.")
    try:
        text, info = extract_text(data, ext)
    except Exception as e:
        raise HTTPException(422, f"Could not read the file: {e}") from e
    if len(text.strip()) < 50:
        raise HTTPException(422, "Almost no text could be extracted. If it's a scanned PDF, upload the DOCX instead.")
    parsed = parse_resume(text)
    folder = get_settings().storage_dir / "uploads"
    folder.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", file.filename or f"resume.{ext}")
    path = folder / f"{uuid.uuid4().hex[:8]}_{safe}"
    path.write_bytes(data)
    if make_master:
        db.execute(update(Resume).values(is_master=False))
    profile = pipeline.get_profile(db)
    r = Resume(user_id=profile.user_id, filename=file.filename or safe, file_type=ext, file_path=str(path),
               raw_text=text, parsed=parsed, format_info=info, is_master=make_master)
    r.ats_score = ats.analyze(parsed, text, info)["ats_score"]
    db.add(r)
    db.flush()
    if make_master:
        pipeline.rescore_all(db)  # matches now use the resume too
    db.commit()
    return r


@router.get("/versions", response_model=list[ResumeVersionOut])
def versions(job_id: int | None = None, db: Session = Depends(get_db)):
    stmt = select(ResumeVersion).order_by(ResumeVersion.id.desc())
    if job_id:
        stmt = stmt.where(ResumeVersion.job_id == job_id)
    return list(db.scalars(stmt))


@router.get("/versions/{version_id}", response_model=ResumeVersionOut)
def get_version(version_id: int, db: Session = Depends(get_db)):
    rv = db.get(ResumeVersion, version_id)
    if rv is None:
        raise HTTPException(404, "Version not found")
    return rv


@router.get("/versions/{version_id}/download")
def download_version(version_id: int, format: str = "docx", db: Session = Depends(get_db)):
    rv = db.get(ResumeVersion, version_id)
    if rv is None:
        raise HTTPException(404, "Version not found")
    path = rv.pdf_path if format == "pdf" else rv.docx_path
    try:
        p = pipeline.storage_path(path)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if not p.exists():
        raise HTTPException(404, "File missing; regenerate the resume.")
    media = "application/pdf" if format == "pdf" else \
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return FileResponse(p, media_type=media, filename=f"{rv.filename_base}.{'pdf' if format == 'pdf' else 'docx'}")


@router.delete("/versions/{version_id}", status_code=204)
def delete_version(version_id: int, db: Session = Depends(get_db)):
    rv = db.get(ResumeVersion, version_id)
    if rv is None:
        raise HTTPException(404, "Version not found")
    db.delete(rv)
    db.commit()


@router.post("/analyze")
def analyze(body: AnalyzeRequest, db: Session = Depends(get_db)):
    """ATS analysis of a resume, optionally against a saved job or a pasted JD."""
    r = _resume(db, body.resume_id)
    job = db.get(Job, body.job_id) if body.job_id else None
    if body.job_id and job is None:
        raise HTTPException(404, "Job not found")
    if job is not None:
        result = pipeline.ats_for(r, job)
    else:
        result = ats.analyze(r.parsed, r.raw_text, r.format_info, body.jd_text, body.job_title)
    db.add(AIAnalysis(job_id=job.id if job else None, resume_id=r.id, kind="ats", result=result))
    db.commit()
    return result


@router.post("/tailor", response_model=ResumeVersionOut, status_code=201)
def tailor_resume(body: TailorRequest, db: Session = Depends(get_db)):
    """Create an ATS-optimised (no job) or job-specific resume version."""
    r = _resume(db, body.resume_id)
    job = db.get(Job, body.job_id) if body.job_id else None
    if body.job_id and job is None:
        raise HTTPException(404, "Job not found")
    if job is not None:
        pipeline.ensure_application(db, job)
    rv = pipeline.create_resume_version(db, r, job, use_ai=body.use_ai)
    db.commit()
    return rv


@router.get("/{resume_id}", response_model=ResumeOut)
def get_resume(resume_id: int, db: Session = Depends(get_db)):
    return _resume(db, resume_id)


@router.post("/{resume_id}/master", response_model=ResumeOut)
def set_master(resume_id: int, db: Session = Depends(get_db)):
    r = _resume(db, resume_id)
    db.execute(update(Resume).values(is_master=False))
    r.is_master = True
    pipeline.rescore_all(db)
    db.commit()
    return r


@router.delete("/{resume_id}", status_code=204)
def delete_resume(resume_id: int, db: Session = Depends(get_db)):
    db.delete(_resume(db, resume_id))
    db.commit()
