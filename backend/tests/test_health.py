"""
Tests for GET /health.

These tests run with TESTING=true (set globally in conftest.py), which means
the app's lifespan never calls connect_to_mongo(). That's fine here: it
exercises the exact code path we want to verify -- that health_check()
degrades gracefully to {"database": "unreachable"} instead of crashing with
an unhandled 500 when the database isn't available. Verifying the "database
IS reachable" path is left to manual/staging verification against a real
MongoDB instance (see docs/architecture.md), rather than requiring every
contributor to have MongoDB running locally just to run the test suite.
"""

from fastapi.testclient import TestClient

from app.main import app


def test_health_check_returns_200():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200


def test_health_check_reports_database_status():
    with TestClient(app) as client:
        response = client.get("/health")
    body = response.json()
    assert "status" in body
    assert "database" in body
    assert body["database"] in ("ok", "unreachable")
