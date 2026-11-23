from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

class ApplicationStatus(str, Enum):
    SUBMITTED = "submitted"

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
