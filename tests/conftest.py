"""Shared test fixtures."""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.tools.mail_api import reset_inbox


@pytest.fixture(autouse=True)
def reset_state():
    """Reset inbox before each test."""
    reset_inbox()
    yield


@pytest_asyncio.fixture
async def client():
    """Async HTTP test client for the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

