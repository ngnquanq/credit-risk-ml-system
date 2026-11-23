from abc import ABC, abstractmethod
from domain.entities.loan_application import LoanApplication

class LoanRepository(ABC):
    @abstractmethod
    async def save(self, application: LoanApplication) -> None:
        pass
