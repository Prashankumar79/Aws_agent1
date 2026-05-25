"""
================================================================================
  backend/tests/conftest.py  —  PYTEST SHARED FIXTURES
================================================================================

PURPOSE:
  Shared fixtures for the smoke-test suite. We isolate every test by:
    • Pointing JobStore at a temp directory (no leaking into storage/job_store/)
    • Pointing the SQLite databases at temp files (no touching backend/data/*.db)
    • Stubbing AWS Bedrock so tests never make a real network call.

🟢 BEGINNER: Fixtures defined here are auto-discovered by pytest in any file
under tests/ — you never need to import them.
================================================================================
"""

# 🟢 BEGINNER: Standard library imports.
import importlib
import os
import sys
from pathlib import Path
from typing import Iterator

import pytest

# 🟢 BEGINNER: Make sure the backend/ root is on sys.path so `import app.*` works
# whether you run `pytest` from the project root, from backend/, or from CI.
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# 🟢 BEGINNER: Set dummy credentials BEFORE app.core.config is ever imported.
# These are placeholders — every test that needs the network is marked
# `@pytest.mark.integration` and skipped by default.
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "AKIATESTTESTTESTTEST")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test-secret-key")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("LOG_LEVEL", "WARNING")
# 🟢 BEGINNER: Empty API_KEY = auth disabled. Specific tests can override this
# to verify the auth dependency really blocks unauthenticated requests.
os.environ.setdefault("API_KEY", "")


@pytest.fixture(autouse=True)
def _isolate_persistent_state(tmp_path, monkeypatch) -> Iterator[Path]:
    """🟢 BEGINNER: Run every test inside a private working directory.

    This fixture redirects:
      * JobStore       → tmp_path/storage/job_store/<namespace>.json
      * Companies DB   → tmp_path/companies.db
      * Templates DB   → tmp_path/templates.db
      * Logs           → tmp_path/logs/

    Without this, tests would mutate ``backend/storage/`` and ``backend/data/``.
    The fixture ALSO resets the in-process service singletons so they pick up
    the temp paths instead of using stale connections from a previous test.
    """
    # Move into the tmp dir so any module that does Path("storage/...") works.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "storage" / "job_store").mkdir(parents=True, exist_ok=True)

    # 🟢 BEGINNER: Re-point the SQLite database paths used by the services.
    # The services read DB_PATH at INSTANCE construction time, so we patch it
    # before any new instances are built.
    from app.services import company_service, template_service
    monkeypatch.setattr(company_service, "DB_PATH", tmp_path / "companies.db", raising=True)
    monkeypatch.setattr(template_service, "DB_PATH", tmp_path / "templates.db", raising=True)

    # 🟢 BEGINNER: The api/v1/{companies,templates}.py modules build a global
    # service object at IMPORT time. After patching DB_PATH we need to rebuild
    # those objects so they create their tables at the temp location.
    from app.api.v1 import companies as companies_router, templates as templates_router
    companies_router.company_service = company_service.CompanyService()
    templates_router.template_service = template_service.TemplateService()

    yield tmp_path


@pytest.fixture
def app_with_stubbed_bedrock(monkeypatch):
    """🟢 BEGINNER: Build the FastAPI app with a fake BedrockService.

    Bedrock is the only thing that would attempt a real network call during
    app startup (lifespan ``check_credentials``). We replace it with a no-op
    stub so the smoke tests stay hermetic.
    """
    from app.services import bedrock_service

    class _FakeBedrock:
        def check_credentials(self):
            return {"invoke_test_passed": True, "stub": True}

    monkeypatch.setattr(bedrock_service, "BedrockService", _FakeBedrock)

    # Import lazily so the patch above is in effect.
    from app.main import app
    return app


@pytest.fixture
def client(app_with_stubbed_bedrock):
    """🟢 BEGINNER: Synchronous TestClient — drives the lifespan + every route."""
    from fastapi.testclient import TestClient
    with TestClient(app_with_stubbed_bedrock) as c:
        yield c


@pytest.fixture
def restore_api_key(monkeypatch):
    """🟢 BEGINNER: Tests that mutate settings.API_KEY use this to undo the change.

    Without this, settings.API_KEY would leak across tests because Settings is
    a module-level singleton.
    """
    from app.core.config import settings as live_settings
    original = live_settings.API_KEY
    yield
    live_settings.API_KEY = original
