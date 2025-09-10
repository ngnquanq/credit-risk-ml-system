"""
Dynamic DWH schema inference for Feast FeatureView fields.

Reads ClickHouse system.columns for the configured mart tables and
produces a list of Feast Field objects, so we don't have to maintain
large static lists manually.

Env vars used (with sensible defaults for local dev):
- APP_CLICKHOUSE_HOST (default: localhost)
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

try:
    import clickhouse_connect  # type: ignore
except Exception:  # pragma: no cover
    clickhouse_connect = None  # type: ignore

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
    host = os.getenv("APP_CLICKHOUSE_HOST", "localhost")
    port = int(os.getenv("APP_CLICKHOUSE_PORT", "8123"))
    user = os.getenv("APP_CLICKHOUSE_USER", "default")
    password = os.getenv("APP_CLICKHOUSE_PASSWORD", "")
    return clickhouse_connect.get_client(host=host, port=port, username=user, password=password)


def infer_dwh_fields() -> List[Field]:  # pragma: no cover - runs in apply script
    db = os.getenv("APP_CLICKHOUSE_DB_DWH", "application_mart")
    fields: List[Field] = []

    # Always include entity key
    fields.append(Field(name="sk_id_curr", dtype=String))

    if not clickhouse_connect:
        # Fallback minimal set if ClickHouse client not available
        fields.extend([
            Field(name="record_counts_mart_credit_card_balance", dtype=Int64),
            Field(name="record_counts_mart_pos_cash_balance", dtype=Int64),
            Field(name="record_counts_mart_previous_application", dtype=Int64),
            Field(name="agg_prev_loans", dtype=Int64),
            Field(name="delinq_12m", dtype=Int64),
            Field(name="avg_util", dtype=Float32),
        ])
        return fields

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

    # Append extra counters/aggregates produced by the service
    extras = [
        Field(name="record_counts_mart_credit_card_balance", dtype=Int64),
        Field(name="record_counts_mart_pos_cash_balance", dtype=Int64),
        Field(name="record_counts_mart_previous_application", dtype=Int64),
        Field(name="agg_prev_loans", dtype=Int64),
        Field(name="delinq_12m", dtype=Int64),
        Field(name="avg_util", dtype=Float32),
    ]
    # De-duplicate by name while preserving order
    seen = set(f.name for f in fields)
    for f in extras:
        if f.name not in seen:
            fields.append(f)
            seen.add(f.name)
    return fields

