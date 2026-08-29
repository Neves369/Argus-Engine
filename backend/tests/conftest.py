from __future__ import annotations

import os
import shutil
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./data/test.db"
os.environ["ALLOWED_SCOPES"] = '["example.com"]'
os.environ["EVIDENCE_DIR"] = "./data/test_evidence"
# Mantém os testes de provider no dev-mode determinístico (chaves em claro),
# a despeito do .env do desenvolvedor agora mapear ARGUS_ENCRYPTION_KEY.
os.environ["ARGUS_ENCRYPTION_KEY"] = ""
os.environ["ENCRYPTION_KEY"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.llm.cache import prefix_cache  # noqa: E402
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


@pytest.fixture(autouse=True)
def _clear_llm_prefix_cache():
    """Tests reuse short, generic prompts across files/providers — without this,
    a completion cached by one test could silently serve another."""
    prefix_cache.clear()
    yield
    prefix_cache.clear()


@pytest.fixture(autouse=True)
def _reset_active_runs():
    """Testes que terminam com um run em andamento/aguardando revisão não podem
    travar o lock de run único para os demais testes do mesmo banco."""
    yield
    from sqlite3 import OperationalError, connect

    con = connect("data/test.db")
    try:
        con.execute(
            "UPDATE runs SET status = 'completed' "
            "WHERE status IN ('running', 'pending_review')"
        )
        con.commit()
    except OperationalError:
        pass
    finally:
        con.close()


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c
