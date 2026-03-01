"""Tests for scoring/schemas.py — request/response validation."""

import pytest
from pydantic import ValidationError

from scoring.schemas import ScoreRequest, ScoreByIdRequest, ScoreResponse


class TestScoreRequest:
    def test_valid(self):
        req = ScoreRequest(features={"a": 1.0, "b": 2.0})
        assert req.features == {"a": 1.0, "b": 2.0}
        assert req.user_id is None

    def test_with_user_id(self):
        req = ScoreRequest(features={"a": 1}, user_id=42)
        assert req.user_id == 42

    def test_missing_features_raises(self):
        with pytest.raises(ValidationError):
            ScoreRequest()

    def test_empty_features_valid(self):
        req = ScoreRequest(features={})
        assert req.features == {}


class TestScoreByIdRequest:
    def test_valid_string(self):
        req = ScoreByIdRequest(sk_id_curr="100001")
        assert req.sk_id_curr == "100001"

    def test_valid_int(self):
        req = ScoreByIdRequest(sk_id_curr=100001)
        assert req.sk_id_curr == 100001

    def test_missing_raises(self):
        with pytest.raises(ValidationError):
            ScoreByIdRequest()


class TestScoreResponse:
    def test_full(self):
        resp = ScoreResponse(
            probability=0.75,
            decision="reject",
            threshold=0.5,
            model_name="credit_risk",
            model_version="3",
        )
        assert resp.probability == 0.75
        assert resp.decision == "reject"

    def test_minimal(self):
        resp = ScoreResponse(
            decision="approve",
            threshold=0.5,
            model_name="m",
        )
        assert resp.probability is None
        assert resp.model_version is None

    def test_with_reason(self):
        resp = ScoreResponse(
            decision="under-review",
            threshold=0.5,
            model_name="m",
            reason="feature_data_unavailable",
        )
        assert resp.reason == "feature_data_unavailable"
