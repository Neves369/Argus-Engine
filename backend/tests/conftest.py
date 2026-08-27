from __future__ import annotations

import os
import shutil
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./data/test.db"
os.environ["ALLOWED_SCOPES"] = '["example.com"]'
os.environ["EVIDENCE_DIR"] = "./data/test_evidence"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _clean_db():
    Path("data").mkdir(parents=True, exist_ok=True)
    db_path = Path("data/test.db")
    evidence_dir = Path("data/test_evidence")
    if db_path.exists():
        db_path.unlink()
    if evidence_dir.exists():
        shutil.rmtree(evidence_dir)
    yield
    if db_path.exists():
        db_path.unlink()
    if evidence_dir.exists():
        shutil.rmtree(evidence_dir)


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c
