"""Background jobs: searches, application kits, bulk re-scoring. Status lives in the DB
(queued -> running -> completed | failed) so the UI can poll without blocking.

A thread pool is enough for a single-user local app. To scale out, swap TaskRunner.submit for a
Celery/RQ enqueue; the task functions already take (task_id, progress) and open their own DB session.
"""
from __future__ import annotations

import logging
import threading
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from sqlalchemy import select

from ..config import get_settings
from ..db import session_scope
from ..models import BackgroundTask, SearchProfile

log = logging.getLogger(__name__)
Progress = Callable[[int, str], None]


class TaskRunner:
    def __init__(self, workers: int = 2):
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="jobpilot-task")
        self.inline = False    # tests run tasks synchronously

    def submit(self, kind: str, params: dict, fn: Callable[[int, dict, Progress], dict]) -> int:
        with session_scope() as db:
            task = BackgroundTask(kind=kind, params=params, status="queued", message="Queued")
            db.add(task)
            db.flush()
            task_id = task.id
        if self.inline:
            self._run(task_id, params, fn)
        else:
            self.pool.submit(self._run, task_id, params, fn)
        return task_id

    def _run(self, task_id: int, params: dict, fn) -> None:
        def progress(pct: int, msg: str) -> None:
            with session_scope() as db:
                t = db.get(BackgroundTask, task_id)
                t.progress, t.message = max(0, min(100, pct)), msg[:500]

        with session_scope() as db:
            t = db.get(BackgroundTask, task_id)
            t.status, t.started_at, t.message = "running", datetime.utcnow(), "Starting"
        try:
            result = fn(task_id, params, progress)
            with session_scope() as db:
                t = db.get(BackgroundTask, task_id)
                t.status, t.progress, t.result = "completed", 100, result
                t.message, t.finished_at = "Done", datetime.utcnow()
        except Exception as e:  # task failures are reported to the UI, never crash the server
            log.exception("task %s failed", task_id)
            with session_scope() as db:
                t = db.get(BackgroundTask, task_id)
                t.status, t.error = "failed", f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}"
                t.message, t.finished_at = str(e)[:500], datetime.utcnow()


runner = TaskRunner(get_settings().task_workers)


class Scheduler(threading.Thread):
    """Runs search profiles that have auto_run enabled, every `interval_hours`."""

    def __init__(self, tick: int):
        super().__init__(daemon=True, name="jobpilot-scheduler")
        self.tick = tick
        self.stop_event = threading.Event()

    def run(self) -> None:
        from .pipeline import search_task
        while not self.stop_event.wait(self.tick):
            try:
                with session_scope() as db:
                    due = []
                    for sp in db.scalars(select(SearchProfile).where(SearchProfile.enabled, SearchProfile.auto_run)):
                        if not sp.last_run_at or sp.last_run_at + timedelta(hours=sp.interval_hours) <= datetime.utcnow():
                            sp.last_run_at = datetime.utcnow()
                            due.append(sp.id)
                for sp_id in due:
                    runner.submit("search", {"search_profile_id": sp_id, "trigger": "schedule"}, search_task)
            except Exception:  # keep the scheduler alive
                log.exception("scheduler tick failed")

    def stop(self) -> None:
        self.stop_event.set()
