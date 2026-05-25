"""Tests for TemplateService — multi-tenant template CRUD."""

# 🟢 BEGINNER: Validates default-template seeding, scoping by company_id,
# and the SQL-injection-safe whitelist used by update_template.
import pytest

from app.services.template_service import TemplateService


def test_default_enterprise_template_is_seeded():
    # 🟢 BEGINNER: The "enterprise-standard" global template must always exist.
    svc = TemplateService()
    t = svc.get_template("enterprise-standard", None)
    assert t is not None
    assert t["is_default"] is True
    assert "enterprise" in t["name"].lower()


def test_company_scoped_template_invisible_to_other_companies():
    svc = TemplateService()
    t = svc.create_template(company_id="acme", name="Acme Custom",
                             description="d", content="c", is_company_default=True)

    # Acme can see it.
    assert svc.get_template(t["id"], "acme") is not None

    # Different company cannot.
    assert svc.get_template(t["id"], "globex") is None


def test_list_templates_includes_global_and_company_templates():
    svc = TemplateService()
    svc.create_template("acme", "Acme1", "", "c1")
    svc.create_template("acme", "Acme2", "", "c2")

    rows = svc.list_templates("acme")
    names = [r["name"] for r in rows]
    assert "Enterprise Standard" in names  # the global default
    assert "Acme1" in names and "Acme2" in names

    # Globex should still see the global default but neither of Acme's templates.
    rows_globex = svc.list_templates("globex")
    names_globex = [r["name"] for r in rows_globex]
    assert "Enterprise Standard" in names_globex
    assert "Acme1" not in names_globex


def test_update_template_partial_update_works():
    svc = TemplateService()
    t = svc.create_template("acme", "Old", "old desc", "old content")

    # Only update the name. Content and description must be preserved.
    updated = svc.update_template(t["id"], "acme", name="New")
    assert updated["name"] == "New"
    assert updated["description"] == "old desc"
    assert updated["content"] == "old content"


def test_update_template_no_fields_is_safe():
    # 🟢 BEGINNER: Passing zero fields should NOT bork the SQL — must just return the row.
    svc = TemplateService()
    t = svc.create_template("acme", "X", "", "c")
    out = svc.update_template(t["id"], "acme")
    assert out is not None and out["name"] == "X"


def test_create_rejects_empty_content():
    svc = TemplateService()
    with pytest.raises(ValueError):
        svc.create_template("acme", "Bad", "", "")


def test_global_default_cannot_be_deleted():
    # 🟢 BEGINNER: Hard rule — global defaults are protected from deletion.
    svc = TemplateService()
    assert svc.delete_template("enterprise-standard", "acme") is False
    assert svc.get_template("enterprise-standard", None) is not None
