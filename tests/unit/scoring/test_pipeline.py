"""Tests for scoring pipeline helpers (pure functions)."""

import pytest
import numpy as np

from scoring.pipeline import as_vector, postprocess


class TestAsVector:
    def test_ordered_features(self):
        features = {"a": 1.0, "b": 2.0, "c": 3.0}
        order = ["c", "a", "b"]
        result = as_vector(features, order)
        np.testing.assert_array_equal(result, [[3.0, 1.0, 2.0]])

    def test_missing_key_fills_zero(self):
        features = {"a": 1.0}
        order = ["a", "b", "c"]
        result = as_vector(features, order)
        np.testing.assert_array_equal(result, [[1.0, 0.0, 0.0]])

    def test_no_order_sorts_by_key(self):
        features = {"c": 3.0, "a": 1.0, "b": 2.0}
        result = as_vector(features, feature_order=None)
        np.testing.assert_array_equal(result, [[1.0, 2.0, 3.0]])

    def test_returns_2d_float_array(self):
        features = {"x": 42}
        result = as_vector(features, ["x"])
        assert result.ndim == 2
        assert result.shape == (1, 1)
        assert result.dtype == float

    def test_empty_input(self):
        result = as_vector({}, feature_order=[])
        assert result.shape == (1, 0)


class TestPostprocess:
    def test_below_threshold_approve(self):
        prob, decision = postprocess(0.3, threshold=0.5)
        assert decision == "approve"
        assert prob == 0.3

    def test_at_threshold_reject(self):
        """Pipeline uses `>=` — at threshold means reject."""
        prob, decision = postprocess(0.5, threshold=0.5)
        assert decision == "reject"

    def test_above_threshold_reject(self):
        prob, decision = postprocess(0.7, threshold=0.5)
        assert decision == "reject"

    def test_returns_float(self):
        prob, _ = postprocess(0.123456789, threshold=0.5)
        assert isinstance(prob, float)

    def test_threshold_edge_zero(self):
        _, decision = postprocess(0.0, threshold=0.0)
        assert decision == "reject"  # 0.0 >= 0.0

    def test_threshold_edge_one(self):
        _, decision = postprocess(0.99, threshold=1.0)
        assert decision == "approve"  # 0.99 < 1.0
