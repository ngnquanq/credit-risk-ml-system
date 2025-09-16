"""
Dynamic DWH schema inference for Feast FeatureView fields.

Reads ClickHouse system.columns for the configured mart tables and
produces a list of Feast Field objects, so we don't have to maintain
large static lists manually.

Env vars used (with sensible defaults for local dev):
- APP_CLICKHOUSE_HOST (default: ch-server)
- APP_CLICKHOUSE_PORT (default: 8123)
- APP_CLICKHOUSE_USER (default: default)
- APP_CLICKHOUSE_PASSWORD (default: empty)
- APP_CLICKHOUSE_DB_DWH (default: application_mart)

Tables considered:
- mart_credit_card_balance
- mart_pos_cash_balance
- mart_previous_application
"""

from __future__ import annotations

import os
from typing import List

import clickhouse_connect
from feast import Field
from feast.types import Float32, Int64, String


MART_TABLES: List[str] = [
    "mart_credit_card_balance",
    "mart_pos_cash_balance",
    "mart_previous_application",
]


def _map_ch_type_to_feast(dtype: str):
    dt = (dtype or "").lower()
    # Normalize ClickHouse type wrappers
    for wrap in ("nullable(", "lowcardinality("):
        if dt.startswith(wrap):
            dt = dt[len(wrap) : -1]
    if any(tok in dt for tok in ["int", "uint"]):
        return Int64
    if any(tok in dt for tok in ["float", "decimal"]):
        return Float32
    return String


def _get_client():  # pragma: no cover - exercised at runtime
    host = os.getenv("APP_CLICKHOUSE_HOST", "ch-server")
    port = int(os.getenv("APP_CLICKHOUSE_PORT", "8123"))
    user = os.getenv("APP_CLICKHOUSE_USER", "default")
    password = os.getenv("APP_CLICKHOUSE_PASSWORD", "")
    return clickhouse_connect.get_client(host=host, port=port, username=user, password=password)


def infer_dwh_fields() -> List[Field]: 
    '''
    This will do infer for all the DWH tables
    '''
    db = os.getenv("APP_CLICKHOUSE_DB_DWH", "application_mart")
    fields: List[Field] = []

    # Always include entity key
    fields.append(Field(name="sk_id_curr", dtype=String))

    # These are the application mart, very similar to the training data features
    try:
        client = _get_client()
        for table in MART_TABLES:
            q = (
                "SELECT name, type FROM system.columns "
                f"WHERE database = %(db)s AND table = %(tbl)s ORDER BY position"
            )
            res = client.query(q, parameters={"db": db, "tbl": table})
            for name, typ in res.result_rows:
                n = str(name).lower()
                if n == "sk_id_curr":
                    continue
                dtype = _map_ch_type_to_feast(str(typ))
                fields.append(Field(name=n, dtype=dtype))
    except Exception:
        # Graceful fallback if CH not reachable
        pass
    
    return fields

