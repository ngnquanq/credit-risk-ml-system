"""Pure applicant-feature transforms used by the Flink UDFs (E2).

No PyFlink import, so the training-serving parity tests can call these directly.
Conventions follow the Kaggle training data the model learned from.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

# Kaggle convention for "not employed" (pensioners, unemployed).
DAYS_EMPLOYED_NOT_EMPLOYED = 365243


def date_from_days_since_epoch(days) -> Optional[date]:
    if days is None:
        return None
    try:
        return date(1970, 1, 1) + timedelta(days=int(days))
    except Exception:
        return None


def _parse_date(value: str) -> Optional[date]:
    from dateutil import parser as dtparser

    value = value.strip()
    if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
        return date_from_days_since_epoch(int(value))  # Debezium encodes DATE as days since epoch
    return dtparser.parse(value).date()


def days_employed(employment_start: Optional[str], created_at: Optional[str]) -> Optional[int]:
    """Days from the application date back to the start of the current job.

    Matches training: zero or negative while employed (``start - application``),
    and ``365243`` when there is no employment start date. ``None`` only when the
    application timestamp itself is missing or unparsable.
    """
    if not created_at:
        return None
    try:
        created = _parse_date(created_at)
    except Exception:
        return None
    if created is None:
        return None
    if not employment_start:
        return DAYS_EMPLOYED_NOT_EMPLOYED
    try:
        start = _parse_date(employment_start)
    except Exception:
        return None
    if start is None:
        return None
    return (start - created).days
