"""Status log port and adapters (E5).

The decision recorder writes exactly one ``application_status_log`` row per event.
Idempotency comes from the partial unique index on ``event_id`` (migration 003):
a replayed event inserts nothing and is reported as a duplicate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol


class RecordResult(str, Enum):
    INSERTED = "INSERTED"
    DUPLICATE = "DUPLICATE"
    UNKNOWN_APPLICATION = "UNKNOWN_APPLICATION"


ALLOWED_STATUSES = frozenset({"approved", "rejected", "manual_review"})


@dataclass(frozen=True)
class StatusRow:
    event_id: str
    sk_id_curr: str
    status: str
    created_by: str
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in ALLOWED_STATUSES:
            raise ValueError(f"Decision status must be one of {sorted(ALLOWED_STATUSES)}, got {self.status!r}")
        if not self.event_id:
            raise ValueError("event_id is required for idempotent writes")


class StatusLogWriter(Protocol):
    def insert_once(self, row: StatusRow) -> RecordResult: ...


class InMemoryStatusLogWriter:
    """Test adapter with the same idempotency and foreign-key behaviour as PostgreSQL."""

    def __init__(self, known_applications: set[str] | None = None):
        self.rows: list[StatusRow] = []
        self._event_ids: set[str] = set()
        self.known_applications = known_applications

    def insert_once(self, row: StatusRow) -> RecordResult:
        if self.known_applications is not None and row.sk_id_curr not in self.known_applications:
            return RecordResult.UNKNOWN_APPLICATION
        if row.event_id in self._event_ids:
            return RecordResult.DUPLICATE
        self._event_ids.add(row.event_id)
        self.rows.append(row)
        return RecordResult.INSERTED


class PostgresStatusLogWriter:
    """Production adapter; ``connect`` returns a psycopg (v3) connection."""

    _SQL = (
        "INSERT INTO application_status_log (event_id, sk_id_curr, status, created_by, metadata) "
        "VALUES (%s, %s, %s, %s, %s::jsonb) "
        "ON CONFLICT (event_id) WHERE event_id IS NOT NULL DO NOTHING"
    )

    def __init__(self, connect):
        self._connect = connect

    def insert_once(self, row: StatusRow) -> RecordResult:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        self._SQL,
                        (row.event_id, row.sk_id_curr, row.status, row.created_by, json.dumps(row.metadata)),
                    )
                except Exception as exc:  # foreign key violation: application does not exist
                    if (getattr(exc, "sqlstate", None) or getattr(exc, "pgcode", None)) == "23503":
                        conn.rollback()
                        return RecordResult.UNKNOWN_APPLICATION
                    raise
                inserted = cur.rowcount == 1
            conn.commit()
            return RecordResult.INSERTED if inserted else RecordResult.DUPLICATE
        finally:
            conn.close()
