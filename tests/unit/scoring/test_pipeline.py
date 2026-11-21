"""Tests for scoring pipeline helpers (pure functions)."""


from scoring.pipeline import postprocess


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
