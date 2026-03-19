from abc import ABC, abstractmethod
from typing import Dict, Any, List

class DwhGateway(ABC):
    @abstractmethod
    async def get_historical_features(self, sk_id_curr: str) -> Dict[str, Any]:
        """Fetch historical features from Data Warehouse."""
        pass
