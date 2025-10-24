"""
ClickHouse DWH client that returns all rows for a given sk_id_curr
from every table in the configured mart database that contains SK_ID_CURR.

For now we return raw rows (no transformation); Feast will pick columns later.
"""

from typing import Any, Dict, List
import asyncio

from loguru import logger
import clickhouse_connect

from core.config import settings


_client = None
_schema_cache: Dict[str, List[str]] = {}

# Restrict to specific mart tables for the initial implementation
MART_TABLES = [
    "mart_credit_card_balance",
    "mart_pos_cash_balance",
    "mart_previous_application",
]


def _get_client():
    global _client
    if _client is None:
        _client = clickhouse_connect.get_client(
            host=settings.clickhouse_host,
            port=settings.clickhouse_port,
            username=settings.clickhouse_user,
            password=settings.clickhouse_password,
            database=settings.clickhouse_db_dwh,
        )
        logger.info(
            f"Connected CH DWH client to {settings.clickhouse_host}:{settings.clickhouse_port} db={settings.clickhouse_db_dwh}"
        )
    return _client


def _query(sql: str):
    client = _get_client()
    return client.query(sql)


def _query_dicts(sql: str) -> List[Dict[str, Any]]:
    res = _query(sql)
    cols = [c.lower() for c in res.column_names]
    return [dict(zip(cols, row)) for row in res.result_rows]


def get_table_columns(table: str) -> List[str]:
    """Return lowercased column names for a mart table, cached.

    Excludes no columns here; callers may drop `sk_id_curr` if desired.
    """
    global _schema_cache
    if table in _schema_cache:
        return _schema_cache[table]
    db = settings.clickhouse_db_dwh
    # Use system.columns for reliable schema discovery
    sql = (
        "SELECT name FROM system.columns "
        f"WHERE database = '{db}' AND table = '{table}' ORDER BY position"
    )
    result = _query(sql)
    names = [str(row[0]).lower() for row in result.result_rows]
    _schema_cache[table] = names
    return names


async def fetch_all_by_sk_id_curr(sk_id_curr: int) -> Dict[str, List[Dict[str, Any]]]:
    """Return a mapping of table_name -> rows for tables in the mart
    database that have a SK_ID_CURR column.
    """
    db = settings.clickhouse_db_dwh
    tables = MART_TABLES
    logger.info({"sk_id_curr": sk_id_curr, "tables": tables})

    results: Dict[str, List[Dict[str, Any]]] = {}
    for tbl in tables:
        sql = f"SELECT * FROM {db}.{tbl} WHERE SK_ID_CURR = {int(sk_id_curr)}"
        rows = await asyncio.to_thread(_query_dicts, sql)
        results[tbl] = rows
    return results


async def close_dwh_client() -> None:
    try:
        if _client is not None:
            _client.close()
    except Exception as e:
        logger.error(f"Error closing CH DWH client: {e}")
