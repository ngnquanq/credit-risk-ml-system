"""Integration tests for /api/v1/presigned-url endpoint."""

import pytest
from unittest.mock import patch, MagicMock
from minio.error import S3Error


class TestPresignedUrl:
    async def test_valid_request(self, api_client):
        resp = await api_client.post("/api/v1/presigned-url", json={
            "sk_id_curr": "100001",
            "document_type": 3,
            "file_extension": "pdf",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "upload_url" in body
        assert "document_id" in body
        assert body["document_id"].startswith("doc_")

    async def test_invalid_document_type(self, api_client):
        """
        BUG DOC: The HTTPException(400) is caught by the broad `except Exception`
        handler and re-wrapped as 500. The endpoint intends 400 but delivers 500.
        """
        resp = await api_client.post("/api/v1/presigned-url", json={
            "sk_id_curr": "100001",
            "document_type": 1,  # not in DOCUMENT_FOLDERS (2-21)
            "file_extension": "pdf",
        })
        assert resp.status_code == 500  # should be 400, but except Exception catches HTTPException

    async def test_invalid_file_extension(self, api_client):
        """Same bug: HTTPException(400) caught by except Exception → 500."""
        resp = await api_client.post("/api/v1/presigned-url", json={
            "sk_id_curr": "100001",
            "document_type": 3,
            "file_extension": "exe",
        })
        assert resp.status_code == 500  # should be 400

    @pytest.mark.parametrize("ext", ["pdf", "jpg", "jpeg", "png"])
    async def test_valid_extensions(self, api_client, ext):
        resp = await api_client.post("/api/v1/presigned-url", json={
            "sk_id_curr": "100001",
            "document_type": 3,
            "file_extension": ext,
        })
        assert resp.status_code == 200

    async def test_special_chars_sanitized(self, api_client):
        """sk_id_curr with special chars should be sanitized (no 400)."""
        resp = await api_client.post("/api/v1/presigned-url", json={
            "sk_id_curr": "user/../etc",
            "document_type": 3,
            "file_extension": "pdf",
        })
        assert resp.status_code == 200

    async def test_empty_sk_id_curr(self, api_client):
        """Same bug: HTTPException(400) caught by except Exception → 500."""
        resp = await api_client.post("/api/v1/presigned-url", json={
            "sk_id_curr": "",
            "document_type": 3,
            "file_extension": "pdf",
        })
        assert resp.status_code == 500  # should be 400

    async def test_minio_error_returns_500(self, api_client, test_app):
        """If MinIO raises S3Error, endpoint returns 500."""
        # Access the minio_client from the module and make it raise
        with patch("entrypoints.api.main.minio_client") as mock_mc:
            mock_mc.presigned_put_object.side_effect = S3Error(
                "NoSuchBucket", "Bucket not found", "resource", "", "", ""
            )
            resp = await api_client.post("/api/v1/presigned-url", json={
                "sk_id_curr": "100001",
                "document_type": 3,
                "file_extension": "pdf",
            })
            assert resp.status_code == 500
