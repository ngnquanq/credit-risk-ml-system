"""Integration test fixtures: in-memory SQLite, httpx ASGI client."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import types

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
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


def _install_otel_fastapi_stub():
    instrumentation = sys.modules.get("opentelemetry.instrumentation")
    if instrumentation is None:
        instrumentation = types.ModuleType("opentelemetry.instrumentation")
        sys.modules["opentelemetry.instrumentation"] = instrumentation

    fastapi_mod = types.ModuleType("opentelemetry.instrumentation.fastapi")
    fastapi_mod.FastAPIInstrumentor = MagicMock()
    sys.modules["opentelemetry.instrumentation.fastapi"] = fastapi_mod
    setattr(instrumentation, "fastapi", fastapi_mod)


def _test_cipher():
    import base64
    import os

    from identity import PiiCipher

    key = lambda: base64.urlsafe_b64encode(os.urandom(32)).decode()  # noqa: E731
    return PiiCipher.from_settings(f"t1:{key()}", key())


class FakeDocumentStore:
    """Signs nothing and stores nothing; ``uploaded`` is what a browser would have posted."""

    def __init__(self):
        self.uploaded: set[str] = set()
        self.fail: Exception | None = None

    def upload_policy(self, key, content_type, max_bytes):
        if self.fail:
            raise self.fail
        return "http://storage.test/loan-documents", {"key": key, "Content-Type": content_type, "policy": "p"}

    async def exists(self, key):
        return key in self.uploaded


@pytest.fixture
async def test_app(db_session, mock_workflow):
    """FastAPI app with dependency overrides for DB and workflow."""
    # Patch module-level side effects before importing the app module
    _install_otel_fastapi_stub()
    with patch("core.tracing.setup.OTLPSpanExporter", MagicMock()), \
         patch("core.tracing.setup.BatchSpanProcessor", MagicMock()), \
         patch("opentelemetry.instrumentation.fastapi.FastAPIInstrumentor") as mock_instr:

        mock_instr_instance = MagicMock()
        mock_instr.return_value = mock_instr_instance

        from entrypoints.api.main import app
        from core.database import get_db
        from entrypoints.api.dependencies import get_submit_loan_workflow

        async def override_get_db():
            yield db_session

        async def override_get_workflow():
            return mock_workflow

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_submit_loan_workflow] = override_get_workflow

        # E11/E13: a signed-in loan officer by default; tests switch identity with `act_as`.
        from audit.writer import InMemoryAuditWriter
        from authz import Principal
        from entrypoints.api.dependencies import get_audit_writer
        from entrypoints.api.security import get_principal

        audit_writer = InMemoryAuditWriter()
        app.state.test_principal = Principal("off-1", "staff", frozenset({"loan_officer"}), "HN01")
        app.state.audit_writer = audit_writer

        async def override_get_principal():
            return app.state.test_principal

        async def override_get_audit_writer():
            return audit_writer

        app.dependency_overrides[get_principal] = override_get_principal
        app.dependency_overrides[get_audit_writer] = override_get_audit_writer

        from entrypoints.api.dependencies import get_audit_reader

        async def override_get_audit_reader():
            return audit_writer  # the in-memory writer also serves traces

        app.dependency_overrides[get_audit_reader] = override_get_audit_reader

        # ADR-0014: a throwaway keyring per test, and storage that remembers what was "uploaded".
        from entrypoints.api.dependencies import get_document_store, get_pii_cipher

        app.state.cipher = _test_cipher()
        app.state.document_store = FakeDocumentStore()

        async def override_get_pii_cipher():
            return app.state.cipher

        async def override_get_document_store():
            return app.state.document_store

        app.dependency_overrides[get_pii_cipher] = override_get_pii_cipher
        app.dependency_overrides[get_document_store] = override_get_document_store

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


@pytest.fixture
def act_as(test_app):
    """Switch the caller identity: act_as(sub, realm, roles, branch_id=None)."""
    from authz import Principal

    def _act_as(sub, realm, roles, branch_id=None):
        test_app.state.test_principal = Principal(sub, realm, frozenset(roles), branch_id)

    return _act_as


@pytest.fixture
def audit(test_app):
    """The in-memory audit writer; read ``audit.events`` after the calls under test."""
    return test_app.state.audit_writer


@pytest.fixture
def upload(test_app):
    """upload(sub, slot=2) -> a document id that ``sub`` uploaded (as the API would have keyed it)."""
    import uuid

    from entrypoints.api.main import DOCUMENT_FOLDERS

    def _upload(sub, slot=2):
        key = f"{test_app.state.cipher.owner_tag(sub)}/{DOCUMENT_FOLDERS[slot]}/doc_{uuid.uuid4().hex}.jpg"
        test_app.state.document_store.uploaded.add(key)
        return key

    return _upload


@pytest.fixture
def valid_payload():
    return {
        "applicant": {"full_name": "Nguyễn Văn Thử", "citizen_id": "001099000123", "phone": "0900 000 123"},
        "birth_date": "1990-01-15",
        "cnt_children": 0,
        "amt_income_total": 180_000.0,
        "amt_credit": 406_597.5,
        "name_income_type": "Working",
        "name_education_type": "Higher education",
        "name_family_status": "Married",
        "name_housing_type": "House / apartment",
        "bureau_consent": True,
    }
