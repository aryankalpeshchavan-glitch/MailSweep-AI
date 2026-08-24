"""System endpoint behavior."""

from __future__ import annotations


def test_health_returns_ok_with_component_statuses(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["environment"] == "test"
    assert body["components"]["database"]["status"] == "ok"
    # No REDIS_URL in test settings => inline mode, reported honestly:
    assert body["components"]["redis"]["status"] == "not_configured"


def test_every_response_carries_request_id(client):
    response = client.get("/api/health")
    assert response.headers.get("x-request-id")


def test_incoming_request_id_is_propagated(client):
    response = client.get("/api/health", headers={"X-Request-ID": "test-rid-123"})
    assert response.headers["x-request-id"] == "test-rid-123"


def test_unknown_route_uses_error_envelope(client):
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "http_404"
    assert body["request_id"]


def test_security_headers_present(client):
    response = client.get("/api/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"
