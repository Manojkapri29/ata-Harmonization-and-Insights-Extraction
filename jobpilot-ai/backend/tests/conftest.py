"""Test setup: an isolated temp database and file store, no scheduler, background tasks run inline."""
import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jobpilot-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["STORAGE_DIR"] = str(_TMP / "files")
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["AI_PROVIDER"] = "none"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def client():
    from app.main import app
    from app.services.tasks import runner
    runner.inline = True
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    from app.db import SessionLocal, init_db
    from app.seed import seed
    init_db()
    s = SessionLocal()
    seed(s)
    yield s
    s.rollback()
    s.close()


@pytest.fixture
def resume_text():
    return (FIXTURES / "sample_resume.txt").read_text()
