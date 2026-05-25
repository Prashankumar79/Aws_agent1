"""Tests for app.core.auth — the optional X-API-Key dependency."""

# 🟢 BEGINNER: Two flavours: API_KEY empty (no-op) and API_KEY set (must enforce).
import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from app.core import auth as auth_mod

# 🟢 BEGINNER: All tests in this file restore the original API_KEY value at teardown
# so the in-memory mutation never leaks into other tests.
pytestmark = pytest.mark.usefixtures("restore_api_key")


def _build_app(api_key: str) -> FastAPI:
    """🟢 BEGINNER: Tiny isolated app that tests only the dependency."""
    auth_mod.settings.API_KEY = api_key  # in-memory override (settings is a singleton)

    app = FastAPI()

    @app.get("/protected", dependencies=[Depends(auth_mod.require_api_key)])
    def protected():
        return {"ok": True}

    return app


def test_no_api_key_set_means_auth_is_disabled():
    client = TestClient(_build_app(""))
    r = client.get("/protected")
    assert r.status_code == 200


def test_missing_header_returns_401_when_required():
    client = TestClient(_build_app("super-secret"))
    r = client.get("/protected")
    assert r.status_code == 401
    assert r.headers.get("www-authenticate", "").lower() == "apikey"


def test_wrong_header_returns_401():
    client = TestClient(_build_app("super-secret"))
    r = client.get("/protected", headers={"X-API-Key": "guess"})
    assert r.status_code == 401


def test_correct_header_passes():
    client = TestClient(_build_app("super-secret"))
    r = client.get("/protected", headers={"X-API-Key": "super-secret"})
    assert r.status_code == 200


def test_compare_digest_used_for_constant_time_comparison():
    # 🟢 BEGINNER: hmac.compare_digest avoids leaking the key byte-by-byte via timing.
    # We can't measure timing here, but at least confirm the function is referenced.
    import inspect
    src = inspect.getsource(auth_mod.require_api_key)
    assert "compare_digest" in src
