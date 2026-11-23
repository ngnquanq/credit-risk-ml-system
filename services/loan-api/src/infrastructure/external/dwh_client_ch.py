"""
ClickHouse DWH client that returns all rows for a given sk_id_curr
from every table in the configured mart database that contains SK_ID_CURR.

For now we return raw rows (no transformation); Feast will pick columns later.
"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Any, Dict, List
import asyncio
import os
import queue
import threading

from loguru import logger
import clickhouse_connect

from core.config import settings


_pool = None
_pool_lock = threading.Lock()
_schema_cache: Dict[str, List[str]] = {}

# Restrict to specific mart tables for the initial implementation
MART_TABLES = [
    "mart_credit_card_balance",
    "mart_pos_cash_balance",
    "mart_previous_application",
]

POOL_SIZE = int(os.getenv("CH_DWH_POOL_SIZE", "20"))
# E15: every warehouse call is bounded. A blocking call that outlives its asyncio timeout keeps
# its thread, so warehouse work runs on its own executor and can never starve the default one
# (which also serves document checks and other request work).
CONNECT_TIMEOUT_S = float(os.getenv("CH_DWH_CONNECT_TIMEOUT", "2"))
QUERY_TIMEOUT_S = float(os.getenv("CH_DWH_QUERY_TIMEOUT", "10"))
BORROW_TIMEOUT_S = float(os.getenv("CH_DWH_BORROW_TIMEOUT", "5"))
EXECUTOR = ThreadPoolExecutor(max_workers=POOL_SIZE, thread_name_prefix="dwh")


def _init_pool():
    """Create the pool only when every client connected; a failure leaves no half-built pool.

    (It used to assign an empty queue first: with the warehouse down, the first client failed and
    every later borrow waited forever, leaking one thread per request.)
    """
    global _pool
    if _pool is not None:
        return
    with _pool_lock:
        if _pool is not None:
            return
        pool: queue.Queue = queue.Queue(maxsize=POOL_SIZE)
        for _ in range(POOL_SIZE):
            pool.put(clickhouse_connect.get_client(
                host=settings.clickhouse_host,
                port=settings.clickhouse_port,
                username=settings.clickhouse_user,
                password=settings.clickhouse_password.get_secret_value() if settings.clickhouse_password else "",
                database=settings.clickhouse_db_dwh,
                connect_timeout=CONNECT_TIMEOUT_S,
                send_receive_timeout=QUERY_TIMEOUT_S,
            ))
        _pool = pool
    logger.info(
        f"CH DWH pool initialized: size={POOL_SIZE} "
        f"host={settings.clickhouse_host}:{settings.clickhouse_port} db={settings.clickhouse_db_dwh}"
    )


@contextmanager
def _borrow_client():
    _init_pool()
    try:
        client = _pool.get(timeout=BORROW_TIMEOUT_S)
    except queue.Empty:
        raise TimeoutError("No warehouse connection free") from None
    try:
        yield client
    finally:
        _pool.put(client)


async def run(fn, *args):
    """Run a blocking warehouse call on the warehouse executor."""
    return await asyncio.get_running_loop().run_in_executor(EXECUTOR, fn, *args)


def _query(sql: str):
    with _borrow_client() as client:
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
        rows = await run(_query_dicts, sql)
        results[tbl] = rows
    return results
