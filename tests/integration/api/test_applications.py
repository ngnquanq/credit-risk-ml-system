"""Integration tests for /api/v1/applications endpoints."""

import pytest
from unittest.mock import AsyncMock
from workflows.dtos import SubmitLoanOutput


@pytest.fixture
def valid_payload():
    return {
        "sk_id_curr": "100001",
        "code_gender": "M",
        "birth_date": "1990-01-15",
        "cnt_children": 0,
        "amt_income_total": 180_000.0,
        "amt_credit": 406_597.5,
        "name_income_type": "Working",
        "name_education_type": "Higher education",
        "name_family_status": "Married",
        "name_housing_type": "House / apartment",
    }


class TestCreateApplication:
    async def test_post_valid_payload_succeeds_despite_status_kwarg(self, api_client, valid_payload):
        """
        BUG DOC: main.py passes `status=output.status` to LoanApplicationResponse.
        That field doesn't exist on the schema, but Pydantic silently ignores unknown
        kwargs (no extra="forbid"). So the request actually returns 201, but the
        `status` field is silently dropped from the response.
        """
        resp = await api_client.post("/api/v1/applications", json=valid_payload)
        assert resp.status_code == 201
        body = resp.json()
        assert "status" not in body  # status kwarg was silently ignored

    async def test_post_missing_required_fields_returns_422(self, api_client):
        resp = await api_client.post("/api/v1/applications", json={"sk_id_curr": "1"})
        assert resp.status_code == 422

    async def test_post_invalid_enum_returns_422(self, api_client, valid_payload):
        valid_payload["code_gender"] = "X"
        resp = await api_client.post("/api/v1/applications", json=valid_payload)
        assert resp.status_code == 422

    async def test_post_invalid_amounts_returns_422(self, api_client, valid_payload):
        valid_payload["amt_income_total"] = 0  # gt=0 violation
        resp = await api_client.post("/api/v1/applications", json=valid_payload)
        assert resp.status_code == 422

    async def test_workflow_exception_returns_500(self, api_client, mock_workflow, valid_payload):
        mock_workflow.execute.side_effect = RuntimeError("boom")
        resp = await api_client.post("/api/v1/applications", json=valid_payload)
        assert resp.status_code == 500


class TestGetApplication:
    async def test_get_nonexistent_returns_404(self, api_client):
        resp = await api_client.get("/api/v1/applications/NONEXISTENT")
        assert resp.status_code == 404


class TestGetApplicationStatus:
    async def test_get_status_nonexistent_returns_404(self, api_client):
        resp = await api_client.get("/api/v1/applications/NONEXISTENT/status")
        assert resp.status_code == 404
