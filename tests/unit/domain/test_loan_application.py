"""Tests for domain entity LoanApplication (pure logic, no I/O)."""

import pytest
from domain.entities.loan_application import LoanApplication, ApplicationStatus


class TestEvaluateWorthiness:
    def test_approve_below_threshold(self):
        app = LoanApplication(sk_id_curr="1", amt_credit=100, amt_income_total=100)
        result = app.evaluate_worthiness(risk_score=0.3, threshold=0.5)
        assert result is True
        assert app.status == ApplicationStatus.APPROVED

    def test_reject_above_threshold(self):
        app = LoanApplication(sk_id_curr="1", amt_credit=100, amt_income_total=100)
        result = app.evaluate_worthiness(risk_score=0.6, threshold=0.5)
        assert result is False
        assert app.status == ApplicationStatus.REJECTED

    def test_at_threshold_approves(self):
        """Domain uses `>` (not `>=`), so score == threshold => APPROVED."""
        app = LoanApplication(sk_id_curr="1", amt_credit=100, amt_income_total=100)
        result = app.evaluate_worthiness(risk_score=0.5, threshold=0.5)
        assert result is True
        assert app.status == ApplicationStatus.APPROVED

    def test_custom_threshold(self):
        app = LoanApplication(sk_id_curr="1", amt_credit=100, amt_income_total=100)
        assert app.evaluate_worthiness(risk_score=0.75, threshold=0.8) is True
        assert app.evaluate_worthiness(risk_score=0.85, threshold=0.8) is False

    def test_evaluate_mutates_status(self):
        app = LoanApplication(sk_id_curr="1", amt_credit=100, amt_income_total=100)
        assert app.status == ApplicationStatus.SUBMITTED
        app.evaluate_worthiness(risk_score=0.1)
        assert app.status == ApplicationStatus.APPROVED


class TestDebtToIncome:
    def test_dti_normal(self):
        app = LoanApplication(sk_id_curr="1", amt_credit=500_000, amt_income_total=200_000)
        assert app.debt_to_income_ratio == 2.5

    def test_dti_zero_income(self):
        app = LoanApplication(sk_id_curr="1", amt_credit=100, amt_income_total=0)
        assert app.debt_to_income_ratio == float("inf")

    def test_dti_negative_income(self):
        """No guard on negative income — ratio is negative."""
        app = LoanApplication(sk_id_curr="1", amt_credit=100, amt_income_total=-100)
        assert app.debt_to_income_ratio == -1.0


class TestDefaults:
    def test_default_status_submitted(self):
        app = LoanApplication(sk_id_curr="1", amt_credit=100, amt_income_total=100)
        assert app.status == ApplicationStatus.SUBMITTED

    def test_default_details_empty_dict(self):
        app = LoanApplication(sk_id_curr="1", amt_credit=100, amt_income_total=100)
        assert app.details == {}
        assert app.details is not None

    def test_none_goods_price(self):
        app = LoanApplication(sk_id_curr="1", amt_credit=100, amt_income_total=100, amt_goods_price=None)
        assert app.amt_goods_price is None


class TestThresholdInconsistency:
    def test_domain_vs_pipeline_boundary(self):
        """
        BUG DOC: domain uses `>` (boundary=approve), pipeline uses `>=` (boundary=reject).
        At exactly the threshold, domain approves but pipeline rejects.
        """
        from scoring.pipeline import postprocess

        threshold = 0.5
        app = LoanApplication(sk_id_curr="1", amt_credit=100, amt_income_total=100)
        domain_result = app.evaluate_worthiness(risk_score=threshold, threshold=threshold)
        _, pipeline_decision = postprocess(prob=threshold, threshold=threshold)

        # Domain says APPROVE, pipeline says REJECT — inconsistency
        assert domain_result is True  # domain: > threshold
        assert pipeline_decision == "reject"  # pipeline: >= threshold
