"""Tests for Pydantic input/output validation schemas."""

import pytest
from pydantic import ValidationError
from datetime import datetime

from infrastructure.persistence.models.pydantic_schemas import (
    LoanApplicationCreate,
    LoanApplicationResponse,
)


class TestLoanApplicationCreateValid:
    def test_valid_minimal_payload(self, valid_create_payload):
        obj = LoanApplicationCreate(**valid_create_payload)
        assert obj.sk_id_curr == "100001"
        assert obj.amt_credit == 406_597.5

    def test_all_optional_fields(self, valid_create_payload):
        payload = {
            **valid_create_payload,
            "amt_annuity": 24_700.5,
            "amt_goods_price": 351_000.0,
            "employment_start_date": "2015-06-01",
            "occupation_type": "Core staff",
            "organization_type": "Business Entity Type 3",
            "own_car_age": 12,
            "document_ids": {"document_id_3": "doc_abc123"},
        }
        obj = LoanApplicationCreate(**payload)
        assert obj.amt_annuity == 24_700.5
        assert obj.own_car_age == 12
        assert obj.document_ids == {"document_id_3": "doc_abc123"}

    def test_each_enum_type(self, valid_create_payload):
        for field, value in [
            ("code_gender", "F"),
            ("name_contract_type", "Revolving loans"),
            ("name_income_type", "Pensioner"),
            ("name_education_type", "Academic degree"),
            ("name_family_status", "Widow"),
            ("name_housing_type", "Renting"),
        ]:
            payload = {**valid_create_payload, field: value}
            LoanApplicationCreate(**payload)  # no error

    def test_cnt_children_zero(self, valid_create_payload):
        payload = {**valid_create_payload, "cnt_children": 0}
        obj = LoanApplicationCreate(**payload)
        assert obj.cnt_children == 0

    def test_amt_annuity_none(self, valid_create_payload):
        payload = {**valid_create_payload, "amt_annuity": None}
        obj = LoanApplicationCreate(**payload)
        assert obj.amt_annuity is None

    def test_amt_goods_price_zero(self, valid_create_payload):
        payload = {**valid_create_payload, "amt_goods_price": 0}
        obj = LoanApplicationCreate(**payload)
        assert obj.amt_goods_price == 0

    def test_document_ids_dict(self, valid_create_payload):
        payload = {**valid_create_payload, "document_ids": {"doc_2": "id1", "doc_3": "id2"}}
        obj = LoanApplicationCreate(**payload)
        assert obj.document_ids == {"doc_2": "id1", "doc_3": "id2"}


class TestLoanApplicationCreateInvalid:
    def test_amt_income_total_zero(self, valid_create_payload):
        payload = {**valid_create_payload, "amt_income_total": 0}
        with pytest.raises(ValidationError, match="amt_income_total"):
            LoanApplicationCreate(**payload)

    def test_amt_credit_zero(self, valid_create_payload):
        payload = {**valid_create_payload, "amt_credit": 0}
        with pytest.raises(ValidationError, match="amt_credit"):
            LoanApplicationCreate(**payload)

    def test_amt_annuity_zero(self, valid_create_payload):
        """amt_annuity has gt=0 when provided (not None)."""
        payload = {**valid_create_payload, "amt_annuity": 0}
        with pytest.raises(ValidationError, match="amt_annuity"):
            LoanApplicationCreate(**payload)

    def test_amt_goods_price_negative(self, valid_create_payload):
        payload = {**valid_create_payload, "amt_goods_price": -1}
        with pytest.raises(ValidationError, match="amt_goods_price"):
            LoanApplicationCreate(**payload)

    def test_flag_mobil_exceeds_max(self, valid_create_payload):
        payload = {**valid_create_payload, "flag_mobil": 2}
        with pytest.raises(ValidationError, match="flag_mobil"):
            LoanApplicationCreate(**payload)

    def test_flag_email_negative(self, valid_create_payload):
        payload = {**valid_create_payload, "flag_email": -1}
        with pytest.raises(ValidationError, match="flag_email"):
            LoanApplicationCreate(**payload)

    def test_cnt_children_negative(self, valid_create_payload):
        payload = {**valid_create_payload, "cnt_children": -1}
        with pytest.raises(ValidationError, match="cnt_children"):
            LoanApplicationCreate(**payload)

    def test_own_car_age_negative(self, valid_create_payload):
        payload = {**valid_create_payload, "own_car_age": -1}
        with pytest.raises(ValidationError, match="own_car_age"):
            LoanApplicationCreate(**payload)

    def test_invalid_enum_gender(self, valid_create_payload):
        payload = {**valid_create_payload, "code_gender": "X"}
        with pytest.raises(ValidationError):
            LoanApplicationCreate(**payload)


class TestLoanApplicationResponseBugs:
    def test_response_silently_ignores_status_kwarg(self):
        """
        BUG DOC: LoanApplicationResponse has no `status` field.
        main.py passes status=output.status via **kwargs, but Pydantic's default
        extra handling silently ignores unknown fields. The real failure is that
        the response object has no `status` attribute despite main.py expecting it.
        """
        resp = LoanApplicationResponse(
            sk_id_curr="1",
            code_gender="M",
            birth_date="1990-01-01",
            cnt_children=0,
            amt_income_total=100_000,
            amt_credit=200_000,
            amt_annuity=None,
            amt_goods_price=None,
            name_contract_type="Cash loans",
            name_income_type="Working",
            name_education_type="Higher education",
            name_family_status="Married",
            name_housing_type="House / apartment",
            employment_start_date=None,
            occupation_type=None,
            organization_type=None,
            flag_mobil=0,
            flag_emp_phone=0,
            flag_work_phone=0,
            flag_phone=0,
            flag_email=0,
            flag_own_car=0,
            flag_own_realty=0,
            own_car_age=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            status="submitted",  # silently ignored — no `status` in schema
        )
        # `status` was silently dropped — attribute doesn't exist on model
        assert not hasattr(resp, "status") or "status" not in resp.model_fields

    def test_max_application_amount_not_enforced(self, valid_create_payload):
        """BUG DOC: settings.max_application_amount=1M is never checked by schema."""
        payload = {**valid_create_payload, "amt_credit": 999_999_999}
        obj = LoanApplicationCreate(**payload)
        assert obj.amt_credit == 999_999_999  # passes despite max_application_amount
