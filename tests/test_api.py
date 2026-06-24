"""Tests for the API endpoints."""

import pytest


@pytest.mark.asyncio
async def test_health_check(client):
    """Test the root health check endpoint."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "email-assistant"


@pytest.mark.asyncio
async def test_dedicated_health_check(client):
    """Test the dedicated JSON health endpoint."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "email-assistant"


@pytest.mark.asyncio
async def test_root_redirects_browser_to_ui(client):
    """Browser requests to root should redirect to the UI for Docker Desktop links."""
    response = await client.get("/", headers={"Accept": "text/html"}, follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/ui"


@pytest.mark.asyncio
async def test_list_inbox(client):
    """Test listing inbox emails."""
    response = await client.get("/inbox/")
    assert response.status_code == 200
    data = response.json()
    assert "emails" in data
    assert data["total"] > 0


@pytest.mark.asyncio
async def test_get_email(client):
    """Test getting a specific email."""
    response = await client.get("/inbox/email-001")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "email-001"
    assert "subject" in data


@pytest.mark.asyncio
async def test_get_email_not_found(client):
    """Test getting a non-existent email."""
    response = await client.get("/inbox/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_thread(client):
    """Test getting a thread by ID."""
    response = await client.get("/inbox/thread/thread-002")
    assert response.status_code == 200
    data = response.json()
    assert data["thread_id"] == "thread-002"
    assert data["message_count"] >= 2


@pytest.mark.asyncio
async def test_metrics_endpoint(client):
    """Test the metrics endpoint."""
    response = await client.get("/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "counters" in data
    assert "latencies" in data
    assert "uptime_seconds" in data


@pytest.mark.asyncio
async def test_list_approvals_empty(client):
    """Test listing approvals when none exist."""
    response = await client.get("/approvals/")
    assert response.status_code == 200
    data = response.json()
    assert "approvals" in data

