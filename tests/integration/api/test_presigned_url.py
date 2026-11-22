"""POST /api/v1/presigned-url: one-object upload policies (ADR-0014)."""

import pytest


async def test_policy_pins_key_type_and_size(api_client, test_app):
    resp = await api_client.post("/api/v1/presigned-url", json={"document_type": 2, "content_type": "image/jpeg"})
    assert resp.status_code == 200
    body = resp.json()
    owner = test_app.state.cipher.owner_tag("off-1")
    assert body["document_id"].startswith(f"{owner}/identity/doc_") and body["document_id"].endswith(".jpg")
    assert body["fields"]["key"] == body["document_id"]
    assert body["fields"]["Content-Type"] == "image/jpeg"
    assert body["upload_url"] == "http://storage.test/loan-documents"
    assert body["max_bytes"] == 10 * 1024 * 1024
    assert "off-1" not in body["document_id"]  # keys never name the uploader


@pytest.mark.parametrize("content_type, ext", [("application/pdf", "pdf"), ("image/png", "png")])
async def test_extension_follows_the_content_type(api_client, content_type, ext):
    resp = await api_client.post("/api/v1/presigned-url", json={"document_type": 3, "content_type": content_type})
    assert resp.json()["document_id"].endswith(f".{ext}")


async def test_unknown_slot_is_400(api_client):
    resp = await api_client.post("/api/v1/presigned-url", json={"document_type": 1, "content_type": "image/png"})
    assert resp.status_code == 400


async def test_other_content_types_are_422(api_client):
    resp = await api_client.post("/api/v1/presigned-url",
                                 json={"document_type": 2, "content_type": "application/x-msdownload"})
    assert resp.status_code == 422


async def test_storage_failure_is_503_without_details(api_client, test_app):
    test_app.state.document_store.fail = RuntimeError("secret endpoint minio-internal:9000 refused")
    resp = await api_client.post("/api/v1/presigned-url", json={"document_type": 2, "content_type": "image/png"})
    assert resp.status_code == 503 and "minio-internal" not in resp.text


async def test_only_submitters_may_upload(api_client, act_as, audit):
    act_as("uw-1", "staff", {"underwriter"})
    resp = await api_client.post("/api/v1/presigned-url", json={"document_type": 2, "content_type": "image/png"})
    assert resp.status_code == 403
    assert audit.events[-1]["action"] == "submit_application" and audit.events[-1]["outcome"] == "denied"
