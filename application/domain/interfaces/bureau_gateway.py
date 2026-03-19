from abc import ABC, abstractmethod
from typing import Dict, Any

class BureauGateway(ABC):
    @abstractmethod
    async def get_bureau_data(self, sk_id_curr: str) -> Dict[str, Any]:
        """Fetch credit bureau data for the applicant."""
        pass
