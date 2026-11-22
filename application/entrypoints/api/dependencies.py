from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from infrastructure.persistence.postgres_loan_repo import PostgresLoanRepository
from infrastructure.external.kafka_scoring import KafkaScoringGateway
from workflows.submit_loan import SubmitLoanWorkflow
from domain.interfaces.loan_repository import LoanRepository
from domain.interfaces.scoring_gateway import ScoringGateway
from functools import lru_cache

from audit.writer import AuditReader, AuditWriter, LoggingAuditWriter, PostgresAuditReader, PostgresAuditWriter

async def get_loan_repository(db: AsyncSession = Depends(get_db)) -> LoanRepository:
    """Dependency for LoanRepository."""
    return PostgresLoanRepository(db)

@lru_cache(maxsize=1)
def _scoring_gateway() -> ScoringGateway:
    return KafkaScoringGateway()


async def get_scoring_gateway() -> ScoringGateway:
    """One producer per process. A producer per request leaked librdkafka threads and, with the
    broker down, destroying each one (with a message still queued) stalled later submissions."""
    return _scoring_gateway()

async def get_submit_loan_workflow(
    repo: LoanRepository = Depends(get_loan_repository),
    gateway: ScoringGateway = Depends(get_scoring_gateway)
) -> SubmitLoanWorkflow:
    """Dependency for SubmitLoanWorkflow."""
    return SubmitLoanWorkflow(repo, gateway)


@lru_cache(maxsize=1)
def _audit_writer() -> AuditWriter:
    from core import settings

    if settings.audit_database_url is None:
        return LoggingAuditWriter()
    from sqlalchemy.ext.asyncio import create_async_engine

    return PostgresAuditWriter(create_async_engine(settings.audit_database_url.get_secret_value(), pool_size=5))


async def get_audit_writer() -> AuditWriter:
    """Dependency for the audit writer (E13)."""
    return _audit_writer()


@lru_cache(maxsize=1)
def _audit_reader() -> AuditReader | None:
    from core import settings

    if settings.audit_reader_database_url is None:
        return None
    from sqlalchemy.ext.asyncio import create_async_engine

    return PostgresAuditReader(create_async_engine(settings.audit_reader_database_url.get_secret_value(), pool_size=2))


async def get_audit_reader() -> AuditReader | None:
    """Dependency for reading the audit trail (auditor role only, E13)."""
    return _audit_reader()


async def get_profile_provider():
    """Dependency for internal customer factors (ADR-0013)."""
    from infrastructure.external.customer_profile import ClickHouseProfileProvider

    return ClickHouseProfileProvider()



@lru_cache(maxsize=1)
def _pii_cipher():
    from core import settings
    from identity import PiiCipher

    if settings.pii_keks is None or settings.pii_hmac_key is None:
        raise RuntimeError("APP_PII_KEKS and APP_PII_HMAC_KEY are required (ADR-0014)")
    return PiiCipher.from_settings(settings.pii_keks.get_secret_value(), settings.pii_hmac_key.get_secret_value())


async def get_pii_cipher():
    """Field encryption and keyed hashing for applicant personal data (ADR-0014)."""
    return _pii_cipher()


async def get_identity_repository(db: AsyncSession = Depends(get_db), cipher=Depends(get_pii_cipher)):
    from identity.repository import IdentityRepository

    return IdentityRepository(db, cipher)


@lru_cache(maxsize=1)
def _document_store():
    from core import settings
    from infrastructure.storage.documents import DocumentStore

    return DocumentStore.from_settings(settings)


async def get_document_store():
    """Presigned uploads and existence checks for applicant documents."""
    return _document_store()
