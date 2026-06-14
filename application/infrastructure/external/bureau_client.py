"""
Async-ish client for querying bureau data from ClickHouse.

Exposes high-level helpers to fetch bureau and bureau_balance data by loan ID
(sk_id_curr) and returns JSON-serializable structures. Uses clickhouse-connect
under the hood and wraps calls with asyncio.to_thread to keep async signatures.
"""

from contextlib import contextmanager
from typing import Any, Dict, List
import asyncio
import os
import queue

from loguru import logger
import clickhouse_connect

from core.config import settings


_pool = None

POOL_SIZE = int(os.getenv("CH_BUREAU_POOL_SIZE", "20"))


def _init_pool():
    global _pool
    if _pool is not None:
        return
    _pool = queue.Queue(maxsize=POOL_SIZE)
    for _ in range(POOL_SIZE):
        client = clickhouse_connect.get_client(
            host=settings.clickhouse_host,
            port=settings.clickhouse_port,
            username=settings.clickhouse_user,
            password=settings.clickhouse_password.get_secret_value() if settings.clickhouse_password else "",
            database=settings.clickhouse_db_external,
        )
        _pool.put(client)
    logger.info(
        f"CH Bureau pool initialized: size={POOL_SIZE} "
        f"host={settings.clickhouse_host}:{settings.clickhouse_port} db={settings.clickhouse_db_external}"
    )


@contextmanager
def _borrow_client():
    _init_pool()
    client = _pool.get()
    try:
        yield client
    finally:
        _pool.put(client)


def _query_dicts(sql: str) -> List[Dict[str, Any]]:
    with _borrow_client() as client:
        result = client.query(sql)
        cols = result.column_names
        rows = result.result_rows
        # Normalize column names to lowercase to match service expectations
        lower_cols = [c.lower() for c in cols]
        return [dict(zip(lower_cols, r)) for r in rows]


async def fetch_bureau_by_loan_id(sk_id_curr: int) -> Dict[str, Any]:
    """Fetch bureau records and their balances for a given sk_id_curr (loan id).

    Returns a structure with two lists: bureau and bureau_balance.
    """
    logger.bind(event="bureau_query").info({"sk_id_curr": sk_id_curr})

    # Bureau rows
    bureau_sql = (
        f"SELECT * FROM {settings.clickhouse_db_external}.bureau "
        f"WHERE SK_ID_CURR = {int(sk_id_curr)} ORDER BY SK_ID_BUREAU"
    )
    bureau_rows: List[Dict[str, Any]] = await asyncio.to_thread(_query_dicts, bureau_sql)

    # Collect sk_id_bureau to fetch balances
    bureau_ids = [row.get("sk_id_bureau") for row in bureau_rows if row.get("sk_id_bureau") is not None]
    balance_rows: List[Dict[str, Any]] = []
    if bureau_ids:
        ids_csv = ",".join(str(int(x)) for x in bureau_ids)
        balance_sql = (
            f"SELECT * FROM {settings.clickhouse_db_external}.bureau_balance "
            f"WHERE SK_ID_BUREAU IN ({ids_csv}) ORDER BY SK_ID_BUREAU, MONTHS_BALANCE"
        )
        balance_rows = await asyncio.to_thread(_query_dicts, balance_sql)

    return {
        "sk_id_curr": sk_id_curr,
        "bureau": bureau_rows,
        "bureau_balance": balance_rows,
    }


async def fetch_external_scores(sk_id_curr: int) -> Dict[str, Any]:
    """Fetch normalized external scores for a given sk_id_curr from external_score table.

    If not found, returns an empty dict.
    """
    sql = (
        f"SELECT * FROM {settings.clickhouse_db_external}.external_score "
        f"WHERE SK_ID_CURR = {int(sk_id_curr)} LIMIT 1"
    )
    rows = await asyncio.to_thread(_query_dicts, sql)
    return rows[0] if rows else {}


async def close_bureau_client() -> None:
    global _pool
    if _pool is None:
        return
    while not _pool.empty():
        try:
            client = _pool.get_nowait()
            client.close()
        except Exception as e:
            logger.error(f"Error closing ClickHouse client: {e}")
    _pool = None
