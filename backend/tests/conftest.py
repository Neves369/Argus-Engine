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
from app.sources.registry import DataSourceRegistry  # noqa: E402

_SOURCES_MANIFEST = Path(__file__).resolve().parents[1] / "sources.json"


class _DeterministicSourcesService:
    """Test double for `DataSourceService` used by API-driven run tests.

    Real crt.sh/NVD/AbuseIPDB/etc. aren't reachable from the test sandbox, so
    without this every run would legitimately produce zero findings (correct
    behavior — see `app.services.source_findings` — but useless as a fixture
    for tests that need *a* finding to exercise evidence/validation/export).

    Uses the real manifest (`sources.json`) for specs — so `target_kind`/
    `query_param` filtering in `_collect_sources` is exercised exactly like
    production — but returns a fixed, real-shaped "ok" crt.sh result instead
    of making a network call. This guarantees exactly one genuine,
    evidence-grounded finding through the REAL `derive_findings_from_sources`
    pipeline (a "subdomains found" info-level lead), not a fabricated one.
    """

    def __init__(self) -> None:
        self._registry = DataSourceRegistry(_SOURCES_MANIFEST)

    def available_sources(self) -> list[str]:
        return self._registry.available_sources()

    def get_source(self, name: str):
        return self._registry.get_source(name)

    async def query(self, name: str, params: dict | None = None) -> dict:
        params = params or {}
        if name == "crtsh":
            target = params.get("q", "example.com")
            return {
                "status": "ok",
                "source": "crtsh",
                "data": {"response": [{"name_value": f"www.{target}\napi.{target}"}]},
                "fetched_at": "2026-01-01T00:00:00+00:00",
            }
        return {
            "status": "simulated",
            "source": name,
            "data": {},
            "fetched_at": "2026-01-01T00:00:00+00:00",
            "reason": "not-reachable-in-tests",
        }


@pytest.fixture(autouse=True)
def _deterministic_sources(monkeypatch):
    """Every API-driven run gets a fake, real-shaped crt.sh result instead of
    hitting the real internet — see `_DeterministicSourcesService`."""
    fake = _DeterministicSourcesService()
    monkeypatch.setattr("app.api.v1.runs.build_sources_service", lambda: fake)
    monkeypatch.setattr("app.api.v1.compositions.build_sources_service", lambda: fake)


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
