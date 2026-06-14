from typing import Dict, Any
from domain.interfaces.bureau_gateway import BureauGateway
from .bureau_client import fetch_bureau_by_loan_id

class BureauAdapter(BureauGateway):
    """
    Infrastructure adapter for the Bureau Service.
    Wraps the existing bureau_client function.
    """
    async def get_bureau_data(self, sk_id_curr: str) -> Dict[str, Any]:
        # Convert str to int as required by the legacy service
        try:
            sk_id_int = int(sk_id_curr)
            return await fetch_bureau_by_loan_id(sk_id_int)
        except ValueError:
            # If ID is not an integer, we can't query the bureau service
            # Log this as warning/error in production
            return {}
