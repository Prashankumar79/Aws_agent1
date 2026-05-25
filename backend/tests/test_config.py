"""Tests for app.core.config — the single source of truth for env config."""

# 🟢 BEGINNER: These tests verify env-driven settings load correctly and that
# helper properties work. No network or AWS access required.
from app.core.config import settings, BACKEND_DIR


def test_chroma_persist_dir_is_absolute_and_under_backend():
    # 🟢 BEGINNER: Critical — relative paths break depending on cwd. Must be absolute.
    assert (BACKEND_DIR / "chroma_db").as_posix() == settings.CHROMA_PERSIST_DIR.replace("\\", "/")


def test_allowed_origins_list_strips_whitespace_and_blanks():
    # 🟢 BEGINNER: Verify the helper handles "  http://a , , http://b  " correctly.
    s = settings.__class__(ALLOWED_ORIGINS="  http://a.com , , http://b.com  ")
    assert s.allowed_origins_list == ["http://a.com", "http://b.com"]


def test_settings_ignores_unknown_env_keys():
    # 🟢 BEGINNER: extra="ignore" lets us add new env vars without crashing existing servers.
    s = settings.__class__(SOME_NEW_KEY_NOT_IN_SCHEMA="hello")
    assert s.APP_NAME  # still loads


def test_default_api_key_is_empty():
    # 🟢 BEGINNER: Auth disabled by default in dev — explicit opt-in via .env.
    assert settings.API_KEY == ""


def test_production_validation_rejects_missing_api_key():
    s = settings.__class__(
        ENVIRONMENT="production",
        DEBUG=False,
        API_KEY="",
        GEMINI_API_KEY="test-gemini",
        AWS_ACCESS_KEY_ID="test-access",
        AWS_SECRET_ACCESS_KEY="test-secret",
        ALLOWED_ORIGINS="https://app.example.com",
    )
    try:
        s.validate_production_ready()
    except RuntimeError as exc:
        assert "API_KEY" in str(exc)
    else:
        raise AssertionError("production validation should require API_KEY")


def test_production_validation_accepts_safe_minimums():
    s = settings.__class__(
        ENVIRONMENT="production",
        DEBUG=False,
        API_KEY="x" * 32,
        GEMINI_API_KEY="test-gemini",
        AWS_ACCESS_KEY_ID="test-access",
        AWS_SECRET_ACCESS_KEY="test-secret",
        ALLOWED_ORIGINS="https://app.example.com",
    )
    s.validate_production_ready()
