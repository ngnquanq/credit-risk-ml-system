"""Audit writers (E13).

``AuditWriter.record`` is the one call the API, the decision recorder and the promotion
watcher make. Adapters:
  - InMemoryAuditWriter: tests.
  - LoggingAuditWriter: structured log only; used until the audit database is configured.
  - PostgresAuditWriter: appends to audit_event under an advisory lock, hash-chained.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional, Protocol

from .chain import GENESIS_HASH, chain_hash
from .sanitizer import sanitize


@dataclass(frozen=True)
class AuditEvent:
    actor_sub: str
    actor_realm: str  # staff | customers | service
    actor_roles: tuple[str, ...]
    action: str
    resource_type: str
    resource_id: str
    outcome: str  # allowed | denied | error
    trace_id: Optional[str] = None
    details: dict = field(default_factory=dict)
    occurred_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        if self.outcome not in {"allowed", "denied", "error"}:
            raise ValueError(f"Invalid audit outcome {self.outcome!r}")
        object.__setattr__(self, "details", sanitize(self.action, self.details))
        object.__setattr__(self, "actor_roles", tuple(sorted(self.actor_roles)))

    def record(self) -> dict:
        data = asdict(self)
        data["actor_roles"] = list(self.actor_roles)
        return data


class AuditWriter(Protocol):
    async def record(self, event: AuditEvent) -> None: ...


class InMemoryAuditWriter:
    def __init__(self) -> None:
        self.rows: list[tuple[int, bytes, bytes, dict]] = []

    async def record(self, event: AuditEvent) -> None:
        prev = self.rows[-1][2] if self.rows else GENESIS_HASH
        data = event.record()
        self.rows.append((len(self.rows) + 1, prev, chain_hash(prev, data), data))

    @property
    def events(self) -> list[dict]:
        return [row[3] for row in self.rows]


class LoggingAuditWriter:
    async def record(self, event: AuditEvent) -> None:
        from loguru import logger

        logger.bind(event="audit").info(event.record())


class PostgresAuditWriter:
    """Appends to the separate ``audit`` database. The connection's role holds INSERT and SELECT only."""

    _LOCK_KEY = 4242

    def __init__(self, engine):
        self._engine = engine  # SQLAlchemy AsyncEngine for the audit database

    async def record(self, event: AuditEvent) -> None:
        import json

        from sqlalchemy import text

        data = event.record()
        async with self._engine.begin() as conn:
            await conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": self._LOCK_KEY})
            prev = (await conn.execute(text("SELECT hash FROM audit_event ORDER BY id DESC LIMIT 1"))).scalar()
            prev = bytes(prev) if prev is not None else GENESIS_HASH
            await conn.execute(
                text(
                    "INSERT INTO audit_event (occurred_at, actor_sub, actor_realm, actor_roles, action, "
                    "resource_type, resource_id, outcome, trace_id, details, prev_hash, hash) VALUES "
                    "(CAST(:occurred_at AS timestamptz), :actor_sub, :actor_realm, :actor_roles, :action, "
                    ":resource_type, :resource_id, :outcome, :trace_id, CAST(:details AS jsonb), :prev_hash, :hash)"
                ),
                {**data, "details": json.dumps(data["details"]), "prev_hash": prev, "hash": chain_hash(prev, data)},
            )
