"""Integration tests for the health endpoint."""

import pytest


class TestHealthEndpoint:
    async def test_health_returns_200(self, api_client):
        resp = await api_client.get("/health")
        assert resp.status_code == 200

    async def test_health_body(self, api_client):
        resp = await api_client.get("/health")
        body = resp.json()
        assert body["status"] in ("healthy", "unhealthy")
        assert "timestamp" in body

    async def test_health_includes_timestamp(self, api_client):
        resp = await api_client.get("/health")
        body = resp.json()
        # Timestamp should be ISO format string
        assert isinstance(body["timestamp"], str)
        assert "T" in body["timestamp"]
