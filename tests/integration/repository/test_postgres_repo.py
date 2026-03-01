"""Integration tests for PostgresLoanRepository using in-memory SQLite."""

import pytest
from datetime import date

from infrastructure.persistence.postgres_loan_repo import PostgresLoanRepository
from infrastructure.persistence.models.sqlalchemy_models import LoanApplication as DbLoanApplication
from domain.entities.loan_application import LoanApplication, ApplicationStatus


@pytest.fixture
def repo(db_session):
    return PostgresLoanRepository(db_session)


def _make_app(sk_id="T001", **overrides):
    defaults = dict(
        sk_id_curr=sk_id,
        amt_credit=100_000.0,
        amt_income_total=50_000.0,
        details={
            "sk_id_curr": sk_id,
            "code_gender": "M",
            "birth_date": date(1990, 1, 1),  # SQLite requires date objects, not strings
            "cnt_children": 0,
            "amt_income_total": 50_000.0,
            "amt_credit": 100_000.0,
            "name_contract_type": "Cash loans",
            "name_income_type": "Working",
            "name_education_type": "Higher education",
            "name_family_status": "Married",
            "name_housing_type": "House / apartment",
            "flag_mobil": 1,
            "flag_emp_phone": 0,
            "flag_work_phone": 0,
            "flag_phone": 1,
            "flag_email": 1,
            "flag_own_car": 0,
            "flag_own_realty": 1,
        },
    )
    defaults.update(overrides)
    return LoanApplication(**defaults)


class TestSave:
    async def test_inserts_new_record(self, repo, db_session):
        app = _make_app()
        await repo.save(app)

        from sqlalchemy.future import select
        result = await db_session.execute(
            select(DbLoanApplication).where(DbLoanApplication.sk_id_curr == "T001")
        )
        row = result.scalar_one_or_none()
        assert row is not None
        assert float(row.amt_credit) == 100_000.0

    async def test_flattens_document_ids(self, repo, db_session):
        app = _make_app(details={
            **_make_app().details,
            "document_ids": {"document_id_3": "doc_abc"},
        })
        await repo.save(app)

        from sqlalchemy.future import select
        result = await db_session.execute(
            select(DbLoanApplication).where(DbLoanApplication.sk_id_curr == "T001")
        )
        row = result.scalar_one()
        assert row.document_id_3 == "doc_abc"

    async def test_skips_none_values(self, repo, db_session):
        app = _make_app(details={
            "sk_id_curr": "T001",
            "amt_credit": 100_000.0,
            "amt_income_total": 50_000.0,
            "code_gender": "M",
            "birth_date": date(1990, 1, 1),
            "cnt_children": 0,
            "amt_annuity": None,
            "name_contract_type": "Cash loans",
            "name_income_type": "Working",
            "name_education_type": "Higher education",
            "name_family_status": "Married",
            "name_housing_type": "House / apartment",
        })
        await repo.save(app)

        from sqlalchemy.future import select
        result = await db_session.execute(
            select(DbLoanApplication).where(DbLoanApplication.sk_id_curr == "T001")
        )
        row = result.scalar_one()
        assert row.amt_annuity is None

    async def test_upserts_existing_record(self, repo, db_session):
        app1 = _make_app()
        await repo.save(app1)

        app2 = _make_app(details={**_make_app().details, "cnt_children": 3})
        await repo.save(app2)

        from sqlalchemy.future import select
        result = await db_session.execute(
            select(DbLoanApplication).where(DbLoanApplication.sk_id_curr == "T001")
        )
        row = result.scalar_one()
        assert row.cnt_children == 3


class TestGetById:
    async def test_get_by_id_crashes_due_to_missing_status_column(self, repo):
        """
        BUG DOC: get_by_id tries to read db_model.status, but the SQLAlchemy
        LoanApplication model has no `status` column → AttributeError.
        """
        await repo.save(_make_app())
        with pytest.raises(AttributeError, match="status"):
            await repo.get_by_id("T001")

    async def test_nonexistent_returns_none(self, repo):
        result = await repo.get_by_id("NOPE")
        assert result is None

    async def test_get_by_id_returns_empty_details_when_status_bug_fixed(self, repo):
        """
        BUG DOC: Even if the status bug is fixed, get_by_id always returns
        details={} — data loss on round-trip. This test documents the intended
        behavior once the status column issue is resolved.
        """
        # Can't test round-trip until the status bug is fixed
        pytest.skip("Blocked by get_by_id status column bug")
