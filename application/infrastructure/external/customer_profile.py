"""Internal factors about a customer for staff (ADR-0013): history with us and a bureau summary.

Aggregates come from the dbt marts in ClickHouse. Only summary figures leave this module;
no raw contract rows and no personal fields.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol


class CustomerProfileProvider(Protocol):
    async def profile(self, sk_id_curr: str) -> dict: ...


def _pick(row: dict, *names: str) -> Optional[Any]:
    lowered = {str(k).lower(): v for k, v in row.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value is not None:
            return value
    return None


def summarize(marts: dict[str, list[dict]], bureau: Optional[dict]) -> dict:
    prev = (marts.get("mart_previous_application") or [{}])[0] or {}
    pos = (marts.get("mart_pos_cash_balance") or [{}])[0] or {}
    card = (marts.get("mart_credit_card_balance") or [{}])[0] or {}
    bureau = bureau or {}
    return {
        "previous_applications": {
            "count": _pick(prev, "PREV_COUNT", "PREV_APPLICATIONS_COUNT"),
            "refusal_rate": _pick(prev, "PREV_REFUSAL_RATE"),
        },
        "pos_loans": {
            "count": _pick(pos, "POS_COUNT_LOANS_TOTAL"),
            "problem_loans": _pick(pos, "POS_COUNT_PROBLEM_LOANS"),
            "max_days_past_due": _pick(pos, "POS_MAX_MAX_DPD"),
            "months_observed": _pick(pos, "POS_TOTAL_MONTHS_OBSERVED"),
        },
        "credit_card": {
            "utilization": _pick(card, "CC_MEAN_UTILIZATION", "CC_UTILIZATION_MEAN"),
        },
        "bureau": {
            "active_credits": _pick(bureau, "BUREAU_ACTIVE_COUNT"),
            "outstanding": _pick(bureau, "BUREAU_ACTIVE_DEBT_SUM"),
            "overdue_count": _pick(bureau, "BUREAU_OVERDUE_COUNT"),
        },
    }


class ClickHouseProfileProvider:
    async def profile(self, sk_id_curr: str) -> dict:
        from infrastructure.external import dwh_client_ch

        customer = int(sk_id_curr)  # ids are numeric in the warehouse; int() also rules out injection
        marts = await dwh_client_ch.fetch_all_by_sk_id_curr(customer)
        rows = await dwh_client_ch.run(
            dwh_client_ch._query_dicts,
            f"SELECT * FROM mart_bureau_features WHERE SK_ID_CURR = {customer} LIMIT 1",
        )
        return summarize(marts, rows[0] if rows else None)
