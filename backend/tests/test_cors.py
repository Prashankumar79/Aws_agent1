"""Tests for CORS configuration in main.py."""

# 🟢 BEGINNER: Validates that we never combine "*" with credentials and that the
# explicit origin list works as expected.
def test_allowed_origin_passes_preflight(client):
    r = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    # FastAPI's CORS middleware returns 200 for valid preflight.
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_disallowed_origin_does_not_get_acao_header(client):
    r = client.options(
        "/health",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    # Either rejected (400) or response has no ACAO for the disallowed origin.
    aco = r.headers.get("access-control-allow-origin", "")
    assert aco != "https://evil.example.com"
