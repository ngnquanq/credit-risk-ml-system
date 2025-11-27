"""
Unit tests for loan application endpoints.

Tests the loan application CRUD endpoints:
- POST /api/v1/applications - Create new application
- GET /api/v1/applications/{customer_id} - Retrieve application
- GET /api/v1/applications/{customer_id}/status - Get application status

Following PEP 8 and writing small, focused test functions.
"""

import pytest
from datetime import date
from httpx import AsyncClient
from fastapi import status
from unittest.mock import AsyncMock


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_loan_application_success(
    api_client: AsyncClient,
    sample_loan_application: dict
):
    """
    Test successful creation of a loan application.

    This test:
    - Sends a POST request with valid loan application data
    - Verifies 201 Created status code
    - Checks response contains all required fields
    - Confirms sk_id_curr matches the request
    - Validates created_at timestamp is present
    """
    # Add required date fields
    application_data = {
        **sample_loan_application,
        "birth_date": "1990-01-15",
        "employment_start_date": "2015-03-20",
    }

    response = await api_client.post("/api/v1/applications", json=application_data)

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["sk_id_curr"] == application_data["sk_id_curr"]
    assert data["code_gender"] == application_data["code_gender"]
    assert data["amt_credit"] == application_data["amt_credit"]
    assert "created_at" in data


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_loan_application_not_found(api_client: AsyncClient):
    """
    Test that retrieving a non-existent application returns 404.

    This test:
    - Attempts to retrieve application with non-existent customer ID
    - Verifies 404 Not Found status
    - Checks error message contains meaningful text
    """
    response = await api_client.get("/api/v1/applications/999999")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    error_data = response.json()
    assert "detail" in error_data
    assert "not found" in error_data["detail"].lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_application_status_success(
    api_client: AsyncClient,
    sample_loan_application: dict
):
    """
    Test successful retrieval of application status.

    This test:
    - Creates a loan application (which creates status log entry)
    - Retrieves the status via /status endpoint
    - Verifies status is "submitted" (initial status)
    - Checks response contains customer_id, status, updated_at, updated_by
    """
    # Create application first
    application_data = {
        **sample_loan_application,
        "birth_date": "1990-01-15",
    }

    create_response = await api_client.post(
        "/api/v1/applications",
        json=application_data
    )
    assert create_response.status_code == status.HTTP_201_CREATED
    customer_id = application_data["sk_id_curr"]

    # Get status
    status_response = await api_client.get(
        f"/api/v1/applications/{customer_id}/status"
    )

    assert status_response.status_code == status.HTTP_200_OK
    status_data = status_response.json()
    assert status_data["customer_id"] == customer_id
    assert status_data["status"] == "submitted"
    assert status_data["updated_by"] == "api-service"
    assert "updated_at" in status_data
    assert "metadata" in status_data


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_application_status_not_found(api_client: AsyncClient):
    """
    Test that status endpoint returns 404 for non-existent application.

    This test:
    - Queries status for non-existent customer ID
    - Verifies 404 Not Found status
    - Checks error message
    """
    response = await api_client.get("/api/v1/applications/888888/status")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    error_data = response.json()
    assert "not found" in error_data["detail"].lower()
