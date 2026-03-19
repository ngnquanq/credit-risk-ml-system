"""Integration test fixtures: in-memory SQLite, httpx ASGI client."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, date

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import JSON, event
from sqlalchemy.dialects.postgresql import JSONB
try:
    from sqlalchemy.ext.asyncio import async_sessionmaker
except ImportError:
    from sqlalchemy.orm import sessionmaker as _sm

    def async_sessionmaker(*a, **kw):
        return _sm(*a, **kw)

from infrastructure.persistence.models.base import Base
from workflows.dtos import SubmitLoanOutput


# Register a compilation hook so SQLite renders JSONB as plain JSON
from sqlalchemy.ext.compiler import compiles

@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return compiler.visit_JSON(type_, **kw)


@pytest.fixture
async def async_engine():
    """In-memory SQLite engine with tables created."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(async_engine):
    """Async session that rolls back after each test."""
    session_factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def mock_workflow():
    """AsyncMock SubmitLoanWorkflow returning a valid output."""
    from workflows.submit_loan import SubmitLoanWorkflow

    wf = AsyncMock(spec=SubmitLoanWorkflow)
    wf.execute.return_value = SubmitLoanOutput(
        application_id="100001",
        status="submitted",
        is_approved=None,
        risk_score=None,
    )
    return wf


@pytest.fixture
async def test_app(db_session, mock_workflow):
    """FastAPI app with dependency overrides for DB and workflow."""
    # Patch module-level side effects before importing the app module
    with patch("core.tracing.setup.OTLPSpanExporter", MagicMock()), \
         patch("core.tracing.setup.BatchSpanProcessor", MagicMock()), \
         patch("opentelemetry.instrumentation.fastapi.FastAPIInstrumentor") as mock_instr, \
         patch("minio.Minio") as MockMinio:

        mock_instr_instance = MagicMock()
        mock_instr.return_value = mock_instr_instance

        mock_minio = MagicMock()
        mock_minio.bucket_exists.return_value = True
        mock_minio.presigned_put_object.return_value = "https://minio.test/presigned"
        MockMinio.return_value = mock_minio

        from entrypoints.api.main import app
        from core.database import get_db
        from entrypoints.api.dependencies import get_submit_loan_workflow

        async def override_get_db():
            yield db_session

        async def override_get_workflow():
            return mock_workflow

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_submit_loan_workflow] = override_get_workflow

        yield app

        app.dependency_overrides.clear()


@pytest.fixture
async def api_client(test_app):
    """httpx AsyncClient bound to the test app."""
    import httpx
    from httpx import ASGITransport

    transport = ASGITransport(app=test_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
