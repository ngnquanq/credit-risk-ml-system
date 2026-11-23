from infrastructure.persistence.models.pydantic_schemas import LoanApplicationCreate
from dataclasses import dataclass
from typing import Optional

# Reuse the API schema as the Workflow Input DTO (Pragmatic approach)
SubmitLoanInput = LoanApplicationCreate

@dataclass
class SubmitLoanOutput:
    application_id: str
    status: str
    is_approved: bool
    risk_score: Optional[float]
