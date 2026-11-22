"""PostgresAuditWriter and the chain verification against a real PostgreSQL (E13).

Runs against the local UI stack (`make local-ui-up`), which creates the `audit` database.
Skipped when it is not running. Set LOCAL_AUDIT_DSN to point elsewhere.
"""

import os
from pathlib import Path

import pytest

from audit import AuditEvent
from audit.writer import PostgresAuditReader, PostgresAuditWriter

ENV_FILE = Path(__file__).resolve().parents[3] / "scripts" / "local" / ".generated" / "postgres.env"


def _dsn() -> str | None:
    if os.getenv("LOCAL_AUDIT_DSN"):
        return os.environ["LOCAL_AUDIT_DSN"]
    if ENV_FILE.exists():
        password = ENV_FILE.read_text().split("POSTGRES_PASSWORD=", 1)[1].strip()
        return f"postgresql://ops_admin:{password}@localhost:5433/audit"
    return None


@pytest.fixture
async def engine():
    dsn = _dsn()
    if dsn is None:
        pytest.skip("local stack not configured (make local-ui-up)")
    pytest.importorskip("asyncpg")
    from sqlalchemy.ext.asyncio import create_async_engine

    eng = create_async_engine(dsn.replace("postgresql://", "postgresql+asyncpg://"))
    try:
        async with eng.connect():
            pass
    except Exception:
        await eng.dispose()
        pytest.skip("local PostgreSQL is not running")
    yield eng
    await eng.dispose()


def _event(resource_id: str, outcome: str = "allowed") -> AuditEvent:
    return AuditEvent(
        actor_sub="test-runner",
        actor_realm="staff",
        actor_roles=("auditor",),
        action="read_audit",
        resource_type="application",
        resource_id=resource_id,
        outcome=outcome,
        details={"rule": "any"},
    )


async def test_events_are_stored_and_the_chain_verifies(engine):
    """Regression: occurred_at used to be sent as a string, which asyncpg rejects (HTTP 500)."""
    import psycopg

    from audit.verify_job import _rows, verify_chain

    writer = PostgresAuditWriter(engine)
    resource = f"pytest-{os.getpid()}"
    await writer.record(_event(resource))
    await writer.record(_event(resource, "denied"))

    trace = await PostgresAuditReader(engine).trace("application", resource)
    assert [e["outcome"] for e in trace] == ["allowed", "denied"]

    with psycopg.connect(_dsn()) as conn, conn.cursor() as cur:
        assert verify_chain(_rows(cur, 1)) is None
