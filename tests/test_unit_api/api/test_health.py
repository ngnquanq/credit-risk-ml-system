"""
Unit tests for health check endpoint.

Tests the /health endpoint which verifies:
- API service is running
- Database connectivity
- Returns proper status codes and response format
"""

import pytest
from httpx import AsyncClient
from fastapi import status


@pytest.mark.unit
@pytest.mark.asyncio
async def test_health_check_returns_healthy_status(api_client: AsyncClient):
    """
    Test that health check endpoint returns 200 OK with healthy status.

    This test verifies:
    - Endpoint is accessible
    - Returns 200 status code
    - Response contains 'status' field set to 'healthy'
    - Response contains 'timestamp' field
    """
    response = await api_client.get("/health")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data


@pytest.mark.unit
@pytest.mark.asyncio
async def test_health_check_returns_unhealthy_when_database_fails():
    """
    Test that health check returns 'unhealthy' when database connection fails.

    This test:
    - Mocks the database dependency to raise an exception
    - Verifies the endpoint still returns 200 OK (not 500 error)
    - Confirms status field is set to 'unhealthy'

    Following best practice: health checks should not fail with 5xx errors.
    """
    from api.main import app
    from core.database import get_db

    # Create a mock database function that raises an exception
    async def mock_failing_database():
        raise Exception("Database connection failed")

    # Override the database dependency
    app.dependency_overrides[get_db] = mock_failing_database

    # Create a new client with the overridden dependency
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")

    # Clean up: remove the override
    app.dependency_overrides.clear()

    # Verify response
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "unhealthy"
