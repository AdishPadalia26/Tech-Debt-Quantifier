"""Integration tests for FastAPI endpoints."""
import pytest
from fastapi.testclient import TestClient
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from main import app

client = TestClient(app)


def test_health_check():
    """Test health endpoint."""
    response = client.get("/")
    assert response.status_code == 200


def test_health_endpoint():
    """Test /health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200


def test_analyze_missing_url():
    """Test analyze with missing URL."""
    response = client.post("/analyze", json={})
    assert response.status_code in (400, 422)


def test_analyze_invalid_url():
    """Test analyze with invalid URL."""
    response = client.post("/analyze", json={"github_url": "not-a-url"})
    assert response.status_code in (400, 422, 503)


def test_status_unknown_job():
    """Test status for unknown job."""
    response = client.get("/status/nonexistent-job-id")
    assert response.status_code in (404, 200)
    if response.status_code == 200:
        assert response.json().get("status") in ("not_found", "unknown", None)


def test_status_in_memory_job():
    """Test status for in-memory job."""
    from main import jobs
    test_job_id = "test-job-12345"
    jobs[test_job_id] = {
        "status": "queued",
        "progress": 0,
        "phase": "Queued",
        "result": None,
        "error": None,
    }
    response = client.get(f"/status/{test_job_id}")
    assert response.status_code == 200
    assert response.json().get("status") == "queued"