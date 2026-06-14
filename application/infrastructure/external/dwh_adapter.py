from typing import Dict, Any
from domain.interfaces.dwh_gateway import DwhGateway
from .dwh_client_ch import fetch_all_by_sk_id_curr

class DwhAdapter(DwhGateway):
    """
    Infrastructure adapter for the ClickHouse DWH.
    Wraps the existing dwh_client_ch module.
    """
    async def get_historical_features(self, sk_id_curr: str) -> Dict[str, Any]:
        # The legacy service returns Dict[str, List[Dict]], which is complex.
        # This adapter serves as a translation layer.
        try:
            sk_id_int = int(sk_id_curr)
            raw_data = await fetch_all_by_sk_id_curr(sk_id_int)
            # Potentially flatten or simplify here if Domain needs a cleaner structure
            return raw_data 
        except ValueError:
            return {}
