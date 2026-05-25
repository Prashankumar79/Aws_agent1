"""End-to-end smoke tests against the real FastAPI app (Bedrock stubbed)."""

# 🟢 BEGINNER: Boots the whole app via the `client` fixture (see conftest.py)
# which patches BedrockService so no network calls fire.
import pytest


def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "version" in r.json()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


def test_health_agents_returns_pipeline_info(client):
    r = client.get("/health/agents")
    assert r.status_code == 200
    body = r.json()
    assert "pipeline" in body
    assert body["pipeline"]["compiled"] is True


def test_docs_disabled_in_non_debug(client):
    # 🟢 BEGINNER: /docs is gated by settings.DEBUG. Default is False → 404.
    r = client.get("/docs")
    assert r.status_code == 404


def test_create_company_flow(client):
    # 🟢 BEGINNER: Exercises the multi-tenant auth path end-to-end (auth disabled in dev).
    r = client.post("/api/v1/companies/", json={"name": "TestCo"})
    assert r.status_code == 201, r.text
    company_id = r.json()["id"]

    r = client.get(f"/api/v1/companies/{company_id}")
    assert r.status_code == 200
    assert r.json()["name"] == "TestCo"

    r = client.delete(f"/api/v1/companies/{company_id}")
    assert r.status_code == 200


def test_create_company_rejects_blank_name(client):
    # 🟢 BEGINNER: Pydantic min_length validation must kick in before our service.
    r = client.post("/api/v1/companies/", json={"name": ""})
    assert r.status_code == 422


def test_template_endpoints_require_company_header(client):
    r = client.get("/api/v1/templates/")
    assert r.status_code == 400
    assert "X-Company-Id" in r.json()["detail"]


def test_list_templates_includes_default_when_company_header_present(client):
    r = client.get("/api/v1/templates/", headers={"X-Company-Id": "test-co"})
    assert r.status_code == 200
    names = [t["name"] for t in r.json()]
    assert any("Enterprise" in n for n in names)


def test_unknown_route_returns_404(client):
    r = client.get("/api/v1/this-does-not-exist")
    assert r.status_code == 404


def test_analyse_endpoint_rejects_paths_outside_upload_dir(client):
    # 🟢 BEGINNER: Critical security regression test for the SSRF/file-read fix.
    r = client.post("/api/v1/jobs/analyse", json={
        "file_path": "/etc/passwd",
        "target_clouds": ["aws"],
    })
    assert r.status_code == 400


def test_analyse_endpoint_rejects_traversal(client):
    r = client.post("/api/v1/jobs/analyse", json={
        "file_path": "../../etc/passwd",
        "target_clouds": ["aws"],
    })
    # Either 400 (rejected as out-of-bounds) or 404 (file does not exist) — never 200.
    assert r.status_code in (400, 404)


def test_rag_chat_rejects_empty_query(client):
    r = client.post("/api/v1/rag/chat", json={"query": ""})
    assert r.status_code == 400


def test_rag_index_rejects_unsupported_extension(client, tmp_path):
    bad = tmp_path / "exploit.exe"
    bad.write_bytes(b"MZ\x00\x00")
    with bad.open("rb") as fp:
        r = client.post(
            "/api/v1/rag/index",
            files={"file": ("exploit.exe", fp, "application/octet-stream")},
        )
    assert r.status_code == 400
    assert "not allowed" in r.json()["detail"].lower()


def test_suggest_prompt_validates_cloud_provider(client):
    r = client.post(
        "/api/v1/jobs/suggest-prompt",
        json={"rough_prompt": "make a vpc", "cloud_provider": "ibm-cloud", "detected_resources": []},
    )
    assert r.status_code == 400
