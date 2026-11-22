"""Integration tests for POST /api/v1/applications validation and failures."""


class TestCreateApplication:
    async def test_post_valid_payload_returns_the_opaque_id(self, api_client, valid_payload):
        resp = await api_client.post("/api/v1/applications", json=valid_payload)
        assert resp.status_code == 201
        body = resp.json()
        assert set(body) == {"id", "status"} and body["status"] == "submitted"
        assert len(body["id"]) == 36

    async def test_post_missing_required_fields_returns_422(self, api_client):
        resp = await api_client.post("/api/v1/applications", json={"amt_credit": 1})
        assert resp.status_code == 422

    async def test_post_without_identity_returns_422(self, api_client, valid_payload):
        valid_payload.pop("applicant")
        assert (await api_client.post("/api/v1/applications", json=valid_payload)).status_code == 422

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

    async def test_get_status_nonexistent_returns_404(self, api_client):
        resp = await api_client.get("/api/v1/applications/NONEXISTENT/status")
        assert resp.status_code == 404
