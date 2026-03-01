"""Shared fixtures for unit tests."""

import pytest
from unittest.mock import AsyncMock

from domain.entities.loan_application import LoanApplication, ApplicationStatus
from domain.interfaces.loan_repository import LoanRepository
from domain.interfaces.scoring_gateway import ScoringGateway


@pytest.fixture
def sample_loan_application():
    """Valid LoanApplication domain entity."""
    return LoanApplication(
        sk_id_curr="100001",
        amt_credit=500_000.0,
        amt_income_total=200_000.0,
        amt_goods_price=450_000.0,
        details={"code_gender": "M", "cnt_children": 1},
    )


@pytest.fixture
def valid_create_payload():
    """Minimal valid dict for LoanApplicationCreate schema."""
    return {
        "sk_id_curr": "100001",
        "code_gender": "M",
        "birth_date": "1990-01-15",
        "cnt_children": 0,
        "amt_income_total": 180_000.0,
        "amt_credit": 406_597.5,
        "name_income_type": "Working",
        "name_education_type": "Higher education",
        "name_family_status": "Married",
        "name_housing_type": "House / apartment",
    }


@pytest.fixture
def mock_loan_repo():
    """AsyncMock repository implementing LoanRepository."""
    repo = AsyncMock(spec=LoanRepository)
    repo.save.return_value = None
    repo.get_by_id.return_value = None
    return repo


@pytest.fixture
def mock_scoring_gateway():
    """AsyncMock gateway implementing ScoringGateway."""
    gw = AsyncMock(spec=ScoringGateway)
    gw.publish_for_scoring.return_value = None
    return gw
