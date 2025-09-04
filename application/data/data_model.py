from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime 

class LoanApplication(BaseModel):
    eir: float                                # Interest rate
    isbidproduct: bool                        # Is cross-sell product
    currdebt: float                           # Current debt
    price: float                              # Credit price
    requesttype: str                          # Tax authority request type
    responsedate: Optional[datetime] = None   # Tax authority response date
    mobilephncnt: float                       # Shared mobile phone count
