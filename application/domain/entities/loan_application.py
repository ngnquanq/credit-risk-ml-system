from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

class ApplicationStatus(str, Enum):
    SUBMITTED = "submitted"
    EVALUATING = "evaluating"
    APPROVED = "approved"
    REJECTED = "rejected"

@dataclass
class LoanApplication:
    """
    Domain Entity for Loan Application.
    This is the core business object. It is stable and independent of API or DB schemas.
    """
    sk_id_curr: str
    amt_credit: float
    amt_income_total: float
    amt_goods_price: Optional[float] = None
    
    # Store other details that are not evaluating factors but needed for persistence
    # This keeps the entity clean while preserving data.
    details: Optional[dict] = field(default_factory=dict)
    
    # Metadata
    status: ApplicationStatus = ApplicationStatus.SUBMITTED
    request_date: datetime = field(default_factory=datetime.utcnow)

    def evaluate_worthiness(self, risk_score: float, threshold: float = 0.5) -> bool:
        """
        Core Business Logic: Determine if the application is approved based on risk score.
        """
        # Business Rule 1: High risk score means rejection
        # (Assuming risk_score is probability of default. If it's probability of approval, flip logic)
        # Let's assume risk_score = Probability of Default (0 = Good, 1 = Bad)
        if risk_score > threshold:
            self.status = ApplicationStatus.REJECTED
            return False
            
        # Business Rule 2: Debt-to-Income check (Example)
        # if self.debt_to_income_ratio > 0.6: ...

        self.status = ApplicationStatus.APPROVED
        return True

    @property
    def debt_to_income_ratio(self) -> float:
        """Calculates DTI ratio."""
        if self.amt_income_total == 0:
            return float('inf')
        return self.amt_credit / self.amt_income_total
