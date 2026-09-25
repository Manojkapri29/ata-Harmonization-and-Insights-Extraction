"""JobPilot AI - FastAPI application."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import jobs, resumes, system, tracking
from .config import get_settings
from .db import SessionLocal, init_db
from .seed import seed
from .services.tasks import Scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with SessionLocal() as db:
        seed(db)
    scheduler = None
    if get_settings().scheduler_enabled:
        scheduler = Scheduler(get_settings().scheduler_tick_seconds)
        scheduler.start()
    yield
    if scheduler:
        scheduler.stop()


app = FastAPI(title="JobPilot AI", version="1.0.0", lifespan=lifespan,
              description="Personal job-search assistant: discovery, matching, ATS resume tailoring, outreach drafts "
                          "and application tracking. Never auto-applies or auto-sends.")

origins = [o.strip() for o in get_settings().cors_origins.split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=["*"],
                   allow_headers=["*"])


for r in (jobs.router, resumes.router, tracking.router, system.router):
    app.include_router(r)
