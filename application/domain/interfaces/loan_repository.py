from abc import ABC, abstractmethod
from typing import Optional
from domain.entities.loan_application import LoanApplication

class LoanRepository(ABC):
    @abstractmethod
    async def save(self, application: LoanApplication) -> None:
        pass

    @abstractmethod
    async def get_by_id(self, application_id: str) -> Optional[LoanApplication]:
        pass
