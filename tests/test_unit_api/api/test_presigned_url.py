"""
Unit tests for pre-signed URL generation endpoint.

Tests the /api/v1/presigned-url endpoint which:
- Generates pre-signed URLs for document uploads to MinIO
- Validates document types and file extensions
- Sanitizes customer IDs for security
- Organizes documents by type in folder structure
"""

import pytest
from unittest.mock import patch
from httpx import AsyncClient
from fastapi import status


@pytest.mark.unit
@pytest.mark.asyncio
async def test_presigned_url_generation_success(api_client: AsyncClient):
    """
    Test successful generation of pre-signed URL for valid document upload.

    This test:
    - Mocks the MinIO client
    - Sends valid request with customer ID, document type, and file extension
    - Verifies 200 OK response
    - Checks response contains upload_url and document_id
    - Confirms document_id follows naming convention (starts with 'doc_')
    """
    with patch("api.main.minio_client") as mock_minio:
        # Mock the MinIO presigned_put_object method
        mock_minio.presigned_put_object.return_value = (
            "https://minio.example.com/uploads/100001/identity/doc_abc123.pdf"
        )

        request_data = {
            "sk_id_curr": "100001",
            "document_type": 2,  # Identity document (passport/ID)
            "file_extension": "pdf"
        }

        response = await api_client.post("/api/v1/presigned-url", json=request_data)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "upload_url" in data
        assert "document_id" in data
        assert data["document_id"].startswith("doc_")
        assert len(data["document_id"]) > 4  # Has UUID suffix


@pytest.mark.unit
@pytest.mark.asyncio
async def test_presigned_url_invalid_document_type(api_client: AsyncClient):
    """
    Test that pre-signed URL generation fails for invalid document type.

    Valid document types are 2-21 (defined in DOCUMENT_FOLDERS mapping).
    This test verifies:
    - Sends request with invalid document type (99)
    - Returns 400 Bad Request
    - Error message indicates invalid document type
    """
    request_data = {
        "sk_id_curr": "100001",
        "document_type": 99,  # Invalid - not in allowed range
        "file_extension": "pdf"
    }

    response = await api_client.post("/api/v1/presigned-url", json=request_data)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Invalid document type" in response.json()["detail"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_presigned_url_invalid_file_extension(api_client: AsyncClient):
    """
    Test that pre-signed URL generation rejects unsupported file extensions.

    Allowed extensions: pdf, jpg, jpeg, png
    This test:
    - Sends request with disallowed extension (.exe)
    - Returns 400 Bad Request
    - Error message indicates unsupported extension
    """
    request_data = {
        "sk_id_curr": "100001",
        "document_type": 2,
        "file_extension": "exe"  # Not allowed for security
    }

    response = await api_client.post("/api/v1/presigned-url", json=request_data)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Unsupported file extension" in response.json()["detail"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_presigned_url_missing_customer_id(api_client: AsyncClient):
    """
    Test that pre-signed URL generation requires a customer ID.

    This test:
    - Sends request with empty sk_id_curr
    - Returns 400 Bad Request
    - Error message indicates sk_id_curr is required
    """
    request_data = {
        "sk_id_curr": "",  # Empty customer ID
        "document_type": 2,
        "file_extension": "pdf"
    }

    response = await api_client.post("/api/v1/presigned-url", json=request_data)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "sk_id_curr is required" in response.json()["detail"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_presigned_url_sanitizes_path_traversal_attempt(
    api_client: AsyncClient
):
    """
    Test that customer ID is sanitized to prevent path traversal attacks.

    Security test verifying:
    - Dangerous characters like '../' are removed or replaced
    - MinIO object path does not contain path traversal sequences
    - Request still succeeds with sanitized value
    """
    with patch("api.main.minio_client") as mock_minio:
        mock_minio.presigned_put_object.return_value = "https://test.url"

        request_data = {
            "sk_id_curr": "../../../etc/passwd",  # Path traversal attempt
            "document_type": 2,
            "file_extension": "pdf"
        }

        response = await api_client.post("/api/v1/presigned-url", json=request_data)

        # Should succeed but with sanitized path
        assert response.status_code == status.HTTP_200_OK

        # Verify MinIO was called with sanitized object name
        call_args = mock_minio.presigned_put_object.call_args
        object_name = call_args[0][1]  # Second argument is object_name
        assert "../" not in object_name
        assert "etc" not in object_name or object_name.startswith("_")
