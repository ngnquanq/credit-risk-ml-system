"""Tests for domain entity LoanApplication (pure logic, no I/O)."""

from domain.entities.loan_application import LoanApplication, ApplicationStatus


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
