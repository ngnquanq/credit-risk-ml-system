from typing import AsyncGenerator
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from infrastructure.persistence.postgres_loan_repo import PostgresLoanRepository
from infrastructure.external.kafka_scoring import KafkaScoringGateway
from workflows.submit_loan import SubmitLoanWorkflow
from domain.interfaces.loan_repository import LoanRepository
from domain.interfaces.scoring_gateway import ScoringGateway

async def get_loan_repository(db: AsyncSession = Depends(get_db)) -> LoanRepository:
    """Dependency for LoanRepository."""
    return PostgresLoanRepository(db)

async def get_scoring_gateway() -> ScoringGateway:
    """Dependency for ScoringGateway."""
    # In production, you might want to reuse a single producer instance
    # or handle configuration here.
    return KafkaScoringGateway()

async def get_submit_loan_workflow(
    repo: LoanRepository = Depends(get_loan_repository),
    gateway: ScoringGateway = Depends(get_scoring_gateway)
) -> SubmitLoanWorkflow:
    """Dependency for SubmitLoanWorkflow."""
    return SubmitLoanWorkflow(repo, gateway)
