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
            band="REJECT",
            status="rejected",
            reasons=["score_band"],
            reason_codes=["EXT_SCORE_LOW"],
            bands={"approve_below": 0.25, "reject_above": 0.35},
            model_name="credit_risk",
            model_version="3",
        )
        assert resp.probability == 0.75
        assert resp.status == "rejected"

    def test_unavailable_has_no_probability(self):
        resp = ScoreResponse(
            band="UNDER_REVIEW",
            status="manual_review",
            reasons=["feature_data_unavailable"],
            bands={"approve_below": 0.25, "reject_above": 0.35},
            model_name="m",
        )
        assert resp.probability is None
        assert resp.reason_codes == []
