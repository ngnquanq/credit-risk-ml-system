"""
Async client for querying the external Bureau database.

Provides high-level helpers to fetch bureau and bureau_balance data by loan ID
(sk_id_curr) and returns JSON-serializable structures.
"""

from typing import Any, Dict, List
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from loguru import logger

from core.config import settings


# Dedicated async engine for the external bureau database
_engine = create_async_engine(
    settings.bureau_database_url,
    pool_size=settings.bureau_db_pool_size,
    max_overflow=settings.bureau_db_max_overflow,
    echo=settings.debug,
    future=True,
)

_SessionLocal = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def fetch_bureau_by_loan_id(sk_id_curr: int) -> Dict[str, Any]:
    """Fetch bureau records and their balances for a given sk_id_curr (loan id).

    Returns a structure with two lists: bureau and bureau_balance.
    """
    logger.bind(event="bureau_query").info({"sk_id_curr": sk_id_curr})
    async with _SessionLocal() as session:
        bureau_rows = await _fetch_bureau(session, sk_id_curr)
        # collect all sk_id_bureau to join with balance
        bureau_ids = [row.get("sk_id_bureau") for row in bureau_rows]
        balance_rows: List[Dict[str, Any]] = []
        if bureau_ids:
            balance_rows = await _fetch_bureau_balance(session, bureau_ids)

        return {
            "sk_id_curr": sk_id_curr,
            "bureau": bureau_rows,
            "bureau_balance": balance_rows,
        }


async def _fetch_bureau(session: AsyncSession, sk_id_curr: int) -> List[Dict[str, Any]]:
    q = text(
        """
        SELECT 
            sk_id_curr,
            sk_id_bureau,
            credit_active,
            credit_currency,
            days_credit,
            credit_day_overdue,
            days_credit_enddate,
            days_enddate_fact,
            amt_credit_max_overdue,
            cnt_credit_prolong,
            amt_credit_sum,
            amt_credit_sum_debt,
            amt_credit_sum_limit,
            amt_credit_sum_overdue,
            credit_type,
            days_credit_update,
            amt_annuity,
            created_at,
            updated_at
        FROM bureau
        WHERE sk_id_curr = :sk_id_curr
        ORDER BY sk_id_bureau
        """
    )
    res = await session.execute(q, {"sk_id_curr": sk_id_curr})
    cols = res.keys()
    return [dict(zip(cols, row)) for row in res.fetchall()]


async def _fetch_bureau_balance(session: AsyncSession, sk_id_bureau_list: List[int]) -> List[Dict[str, Any]]:
    # Use UNNEST with parameter array for efficiency if supported by driver
    q = text(
        """
        SELECT 
            bb.sk_id_bureau,
            bb.months_balance,
            bb.status,
            bb.created_at,
            bb.updated_at
        FROM bureau_balance bb
        WHERE bb.sk_id_bureau = ANY(:bureau_ids)
        ORDER BY bb.sk_id_bureau, bb.months_balance
        """
    )
    res = await session.execute(q, {"bureau_ids": sk_id_bureau_list})
    cols = res.keys()
    return [dict(zip(cols, row)) for row in res.fetchall()]


async def close_bureau_client() -> None:
    """Dispose bureau DB engine (called on app shutdown)."""
    try:
        await _engine.dispose()
    except Exception as e:
        logger.error(f"Error disposing bureau DB engine: {e}")
