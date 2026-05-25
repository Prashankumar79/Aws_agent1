"""Tests for CompanyService SQLite CRUD."""

# 🟢 BEGINNER: These run against a temp SQLite file (see conftest.py).
import pytest

from app.services.company_service import CompanyService


def test_create_get_list_update_delete():
    svc = CompanyService()

    # Create
    c = svc.create_company("Acme Corp")
    assert c["id"] and c["name"] == "Acme Corp"
    assert c["created_at"] == c["updated_at"]

    # Get
    fetched = svc.get_company(c["id"])
    assert fetched is not None
    assert fetched["name"] == "Acme Corp"

    # List
    rows = svc.list_companies()
    assert any(r["id"] == c["id"] for r in rows)

    # Update
    updated = svc.update_company(c["id"], "Acme Inc.")
    assert updated and updated["name"] == "Acme Inc."
    assert updated["updated_at"] >= updated["created_at"]

    # Delete
    assert svc.delete_company(c["id"]) is True
    assert svc.get_company(c["id"]) is None
    # Second delete is a no-op, not an error.
    assert svc.delete_company(c["id"]) is False


def test_create_rejects_blank_name():
    # 🟢 BEGINNER: Defence against accidental empty-name rows in the DB.
    svc = CompanyService()
    with pytest.raises(ValueError):
        svc.create_company("")
    with pytest.raises(ValueError):
        svc.create_company("   ")


def test_update_unknown_company_returns_none():
    svc = CompanyService()
    assert svc.update_company("does-not-exist", "New") is None


def test_create_strips_whitespace():
    svc = CompanyService()
    c = svc.create_company("   Beta   ")
    assert c["name"] == "Beta"
