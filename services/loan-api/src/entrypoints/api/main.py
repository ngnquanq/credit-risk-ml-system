"""
Main FastAPI application entry point.
Home Credit Loan Application API.

Every application is addressed by its opaque ``public_id`` (ADR-0014). The internal customer key
(``sk_id_curr``) joins the operational, streaming and warehouse data and never leaves the API.
Applicant names, citizen IDs and phone numbers live encrypted in ``applicant_identity``; responses
carry masked values, and the unmasked ones only come from ``identity:reveal`` with a reason.
"""

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal

from audit.writer import AuditReader, AuditWriter
from authz import Action, Principal, Resource, authorize
from authz.policy import CUSTOMER_REALM
from core import close_db, get_db, init_db, settings
from core.tracing import setup_tracing
from decisions.reasons import reason_texts
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from identity import mask_citizen_id
from identity.repository import IdentityRepository
from infrastructure.persistence.models import (
    ApplicationSubmission,
    HealthResponse,
    LoanApplicationResponse,
)
from infrastructure.persistence.models.sqlalchemy_models import (
    ApplicationStatusLog as DbApplicationStatusLog,
)
from infrastructure.persistence.models.sqlalchemy_models import (
    CaseNote as DbCaseNote,
)
from infrastructure.persistence.models.sqlalchemy_models import (
    LoanApplication as DbLoanApplication,
)
from loguru import logger

# Tracing
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from workflows.submit_loan import SubmitLoanWorkflow

from .access import require_action
from .dependencies import (
    _document_store,
    get_audit_reader,
    get_audit_writer,
    get_document_uploads,
    get_identity_repository,
    get_profile_provider,
    get_submit_loan_workflow,
)
from .documents import DocumentUploads
from .policy_changes import router as policy_changes_router
from .security import get_principal

# Initialize tracing
tracer = setup_tracing("api-service", sampling_rate=0.1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Starting Home Credit Loan API...")
    if not settings.debug:
        # E11: never serve /api/v1 without a trusted identity provider outside debug mode.
        if not settings.oidc_issuer_list:
            raise RuntimeError("APP_OIDC_ISSUERS is empty; refusing to start without token verification")
        # ADR-0014: never accept personal data without the keys to encrypt it.
        if settings.pii_keks is None or settings.pii_hmac_key is None:
            raise RuntimeError("APP_PII_KEKS and APP_PII_HMAC_KEY are required")
    await init_db()
    await asyncio.to_thread(_document_store().ensure_bucket)
    yield
    logger.info("Shutting down Home Credit Loan API...")
    await close_db()


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="API for Home Credit loan applications with document upload support",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in settings.cors_origins if o != "*"],
    # Portals call the API from their server (BFF, ADR-0012); browsers never send credentials here.
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization", "Accept-Language"],
)

# Auto-instrument FastAPI with tracing
FastAPIInstrumentor.instrument_app(app)

NOT_FOUND = "Application not found"
NO_STORE = {"Cache-Control": "no-store"}


class PreSignedURLRequest(BaseModel):
    document_type: int = Field(..., description="Document slot (2-21)")
    content_type: Literal["application/pdf", "image/jpeg", "image/png"]


class PreSignedURLResponse(BaseModel):
    upload_url: str = Field(..., description="POST the form here (multipart), fields first, file last")
    fields: dict[str, str]
    document_id: str
    max_bytes: int


class SubmissionResponse(BaseModel):
    id: str
    status: str


# Health check endpoint
@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check(db: AsyncSession = Depends(get_db)):
    """Health check endpoint."""
    try:
        await db.execute(select(1))
        database_connected = True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        database_connected = False

    return HealthResponse(
        status="healthy" if database_connected else "unhealthy",
        timestamp=datetime.utcnow()
    )


# ---------------------------------------------------------------------------
# Lookups and authorization helpers (E11): load only what the policy needs, decide, audit.
# ---------------------------------------------------------------------------
def _locale(request: Request) -> str:
    return "en" if request.headers.get("accept-language", "").lower().startswith("en") else "vi"


def _public_id(value: str) -> str | None:
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return None


async def _application(db: AsyncSession, application_id: str) -> DbLoanApplication | None:
    public_id = _public_id(application_id)
    if public_id is None:
        return None
    return (
        await db.execute(select(DbLoanApplication).where(DbLoanApplication.public_id == public_id))
    ).scalar_one_or_none()


async def _status_rows(db: AsyncSession, customer_ref: str) -> list[DbApplicationStatusLog]:
    return list((await db.execute(
        select(DbApplicationStatusLog)
        .where(DbApplicationStatusLog.sk_id_curr == customer_ref)
        .order_by(DbApplicationStatusLog.id)
    )).scalars())


async def _latest_status(db: AsyncSession, customer_ref: str) -> DbApplicationStatusLog | None:
    return (await db.execute(
        select(DbApplicationStatusLog)
        .where(DbApplicationStatusLog.sk_id_curr == customer_ref)
        .order_by(DbApplicationStatusLog.id.desc())
        .limit(1)
    )).scalar_one_or_none()


async def _resource(db: AsyncSession, row: DbLoanApplication) -> Resource:
    latest = await _latest_status(db, row.sk_id_curr)
    return Resource(
        type="application",
        id=str(row.public_id),
        channel=row.channel,
        applicant_sub=row.applicant_sub,
        created_by_sub=row.created_by_sub,
        branch_id=row.branch_id,
        status=latest.status if latest else "submitted",
        consent_recorded=row.bureau_consent_at is not None,
    )


def _new_application_resource(principal: Principal, public_id: str) -> Resource:
    if principal.realm == CUSTOMER_REALM:
        return Resource(type="application", id=public_id, channel="self", applicant_sub=principal.sub,
                        created_by_sub=principal.sub)
    return Resource(type="application", id=public_id, channel="staff", created_by_sub=principal.sub,
                    branch_id=principal.branch_id)


async def _require_application(db: AsyncSession, application_id: str, principal: Principal, action: Action,
                               audit: AuditWriter, details: dict | None = None
                               ) -> tuple[DbLoanApplication, Resource]:
    row = await _application(db, application_id)
    if row is None:
        # Same answer for malformed, unknown and other people's guesses: ids are not an oracle.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)
    resource = await _resource(db, row)
    await require_action(principal, action, resource, audit, details)
    return row, resource


# ---------------------------------------------------------------------------
# Documents: browsers upload straight to storage with a presigned POST policy.
# ---------------------------------------------------------------------------
@app.post("/api/v1/presigned-url", response_model=PreSignedURLResponse, tags=["Documents"])
async def get_presigned_url(
    request: PreSignedURLRequest,
    principal: Principal = Depends(get_principal),
    audit: AuditWriter = Depends(get_audit_writer),
    uploads: DocumentUploads = Depends(get_document_uploads),
):
    """One-object upload policy: key, content type and size are fixed by the API."""
    # Uploading is part of submitting: the same rules decide who may do it (E11).
    await require_action(principal, Action.SUBMIT_APPLICATION, _new_application_resource(principal, "upload"), audit,
                   {"document_type": request.document_type})
    key, url, fields = uploads.presign(request.document_type, request.content_type)
    return PreSignedURLResponse(upload_url=url, fields=fields, document_id=key, max_bytes=uploads.max_bytes)


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
@app.post("/api/v1/applications", response_model=SubmissionResponse, status_code=status.HTTP_201_CREATED,
          tags=["Applications"])
async def create_loan_application(
    submission: ApplicationSubmission,
    workflow: SubmitLoanWorkflow = Depends(get_submit_loan_workflow),
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
    audit: AuditWriter = Depends(get_audit_writer),
    identities: IdentityRepository = Depends(get_identity_repository),
    uploads: DocumentUploads = Depends(get_document_uploads),
):
    """Create a loan application. Ownership comes from the verified caller, never from the body."""
    public_id = str(uuid.uuid4())
    resource = _new_application_resource(principal, public_id)
    await require_action(principal, Action.SUBMIT_APPLICATION, resource, audit,
                   {"channel": resource.channel, "branch_id": resource.branch_id,
                    "consent": submission.bureau_consent, "documents": sorted(submission.document_ids or {})})
    await uploads.validate(
        submission.document_ids, require_identity=resource.channel == "self"
    )

    applicant = submission.applicant
    customer_ref = await identities.resolve_or_create(applicant.full_name, applicant.citizen_id, applicant.phone)
    if (await db.execute(select(DbLoanApplication.sk_id_curr).where(DbLoanApplication.sk_id_curr == customer_ref))).first():
        # One open application per customer (inherited from the data model; ADR-0014).
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="This customer already has an application; please contact the branch")
    ownership = {
        "public_id": public_id,
        "channel": resource.channel,
        "created_by_sub": resource.created_by_sub,
        "applicant_sub": resource.applicant_sub,
        "branch_id": resource.branch_id,
        "bureau_consent_at": datetime.utcnow() if submission.bureau_consent else None,
    }
    try:
        from workflows.dtos import SubmitLoanInput

        data = submission.model_dump(exclude={"applicant"})
        output = await workflow.execute(SubmitLoanInput(sk_id_curr=customer_ref, **data), ownership)
    except Exception as e:
        logger.exception(f"Failed to create loan application {public_id}: {type(e).__name__}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create loan application",
        )
    return SubmissionResponse(id=public_id, status=output.status)


@app.get("/api/v1/me/applications", tags=["Applications"])
async def my_applications(
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
    audit: AuditWriter = Depends(get_audit_writer),
):
    """The signed-in applicant's own applications, newest first."""
    await require_action(principal, Action.READ_APPLICATION,
                   Resource(type="application", id="me", channel="self", applicant_sub=principal.sub), audit)
    rows = (await db.execute(
        select(DbLoanApplication).where(DbLoanApplication.applicant_sub == principal.sub)
        .order_by(DbLoanApplication.created_at.desc())
    )).scalars().all()
    out = []
    for row in rows:
        latest = await _latest_status(db, row.sk_id_curr)
        out.append({"id": str(row.public_id), "amt_credit": float(row.amt_credit), "created_at": row.created_at,
                    "status": latest.status if latest else "submitted"})
    return out


@app.get("/api/v1/applications/{application_id}", response_model=LoanApplicationResponse, tags=["Applications"])
async def get_loan_application(
    application_id: str,
    response: Response,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
    audit: AuditWriter = Depends(get_audit_writer),
    identities: IdentityRepository = Depends(get_identity_repository),
):
    """Loan data with the applicant's name and masked citizen ID and phone."""
    row, _ = await _require_application(db, application_id, principal, Action.READ_APPLICATION, audit)
    response.headers.update(NO_STORE)
    masked = await identities.masked(row.sk_id_curr)
    data = {c.key: getattr(row, c.key) for c in DbLoanApplication.__table__.columns}
    data.update(id=str(row.public_id), applicant=masked.as_dict() if masked else None,
                documents=sorted(k for k, v in data.items() if k.startswith("document_id_") and v))
    return LoanApplicationResponse.model_validate(data)


class RevealRequest(BaseModel):
    reason: str = Field(..., min_length=10, max_length=500)


@app.post("/api/v1/applications/{application_id}/identity:reveal", tags=["Applications"])
async def reveal_identity(
    application_id: str,
    body: RevealRequest,
    response: Response,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
    audit: AuditWriter = Depends(get_audit_writer),
    identities: IdentityRepository = Depends(get_identity_repository),
):
    """Unmasked citizen ID and phone for whoever works the case; the reason is audited, the values never."""
    row, _ = await _require_application(db, application_id, principal, Action.REVEAL_IDENTITY, audit,
                                        {"reason": body.reason, "fields": ["citizen_id", "phone"]})
    response.headers.update(NO_STORE)
    revealed = await identities.reveal(row.sk_id_curr)
    if revealed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No identity recorded")
    return revealed


class AttachDocumentRequest(BaseModel):
    slot: int = Field(..., ge=2, le=21)
    document_id: str


@app.post("/api/v1/applications/{application_id}/documents", status_code=status.HTTP_201_CREATED,
          tags=["Documents"])
async def attach_document(
    application_id: str,
    body: AttachDocumentRequest,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
    audit: AuditWriter = Depends(get_audit_writer),
    uploads: DocumentUploads = Depends(get_document_uploads),
):
    """Add a document the caller uploaded to an open application (e.g. payslips during review)."""
    slot = f"document_id_{body.slot}"
    row, resource = await _require_application(db, application_id, principal, Action.ATTACH_DOCUMENT, audit,
                                               {"slot": slot})
    await uploads.validate({slot: body.document_id})
    setattr(row, slot, body.document_id)
    row.updated_at = datetime.utcnow()
    await db.commit()
    return {"application_id": resource.id, "slot": slot}


@app.get("/api/v1/applications/{application_id}/status", tags=["Applications"])
async def get_application_status(
    application_id: str,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
    audit: AuditWriter = Depends(get_audit_writer),
):
    """Latest status; ``submitted`` until a decision is recorded (E5)."""
    row, resource = await _require_application(db, application_id, principal, Action.READ_DECISION, audit)
    latest = await _latest_status(db, row.sk_id_curr)
    return {
        "application_id": resource.id,
        "status": latest.status if latest else "submitted",
        "updated_at": latest.created_at if latest else None,
    }


@app.get("/api/v1/applications/{application_id}/decision", tags=["Decisions"])
async def get_decision(
    application_id: str,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
    audit: AuditWriter = Depends(get_audit_writer),
):
    """Decision, plain-language reasons (Accept-Language: vi or en) and the status timeline.

    No score or contributions (ADR-0013), and the timeline carries statuses and times only.
    """
    row, resource = await _require_application(db, application_id, principal, Action.READ_DECISION, audit)
    rows = await _status_rows(db, row.sk_id_curr)
    history = [{"status": "submitted", "at": row.created_at}] + [{"status": r.status, "at": r.created_at} for r in rows]
    latest = rows[-1] if rows else None
    codes = list((latest.event_metadata or {}).get("reason_codes") or []) if latest else []
    return {
        "application_id": resource.id,
        "status": latest.status if latest else "submitted",
        "amt_credit": float(row.amt_credit),
        "submitted_at": row.created_at,
        "decided_at": latest.created_at if latest else None,
        "reasons": reason_texts(codes, _locale(request)) if latest and latest.status != "approved" else [],
        "history": history,
    }


@app.get("/api/v1/applications/{application_id}/explanation", tags=["Decisions"])
async def get_explanation(
    application_id: str,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
    audit: AuditWriter = Depends(get_audit_writer),
):
    """Score, band, contributions and versions of the automated decision (underwriter, auditor)."""
    row, resource = await _require_application(db, application_id, principal, Action.READ_EXPLANATION, audit)
    decided = (
        await db.execute(
            select(DbApplicationStatusLog)
            .where(DbApplicationStatusLog.sk_id_curr == row.sk_id_curr,
                   DbApplicationStatusLog.created_by == "decision-recorder")
            .order_by(DbApplicationStatusLog.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if decided is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No automated decision recorded yet")
    meta = decided.event_metadata or {}
    return {
        "application_id": resource.id,
        "status": decided.status,
        "decided_at": decided.created_at,
        **{k: meta.get(k) for k in ("band", "score", "bands", "reasons", "reason_codes", "contributions",
                                    "explanation", "model", "model_version", "feature_set_sha256")},
    }


# ---------------------------------------------------------------------------
# Manual review (E5, E11): underwriters decide; never on their own submissions.
# ---------------------------------------------------------------------------
class ReviewDecisionRequest(BaseModel):
    outcome: str = Field(..., pattern="^(approved|rejected)$")
    reason_code: str = Field(..., min_length=3, max_length=64)
    reason: str = Field(..., min_length=10, max_length=1000)


@app.get("/api/v1/reviews", tags=["Reviews"])
async def list_reviews(
    limit: int = Query(50, ge=1, le=200),
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
    audit: AuditWriter = Depends(get_audit_writer),
):
    """Applications whose latest status is manual_review, oldest first."""
    if "underwriter" not in principal.roles:
        await require_action(principal, Action.CLAIM_REVIEW, Resource(type="review_queue", id="-"), audit)
    latest: dict[str, DbApplicationStatusLog] = {}
    for row in (await db.execute(select(DbApplicationStatusLog).order_by(DbApplicationStatusLog.id))).scalars():
        latest[row.sk_id_curr] = row
    in_review = {ref: row for ref, row in latest.items() if row.status == "manual_review"}
    applications = (await db.execute(
        select(DbLoanApplication).where(DbLoanApplication.sk_id_curr.in_(list(in_review)))
    )).scalars().all() if in_review else []
    queue = []
    for application in applications:
        status_row = in_review[application.sk_id_curr]
        resource = await _resource(db, application)
        meta = status_row.event_metadata or {}
        queue.append({
            "application_id": resource.id,
            "since": status_row.created_at,
            "amt_credit": float(application.amt_credit),
            "score": meta.get("score"),
            "reasons": meta.get("reasons", []),
            "branch_id": application.branch_id,
            "can_review": authorize(principal, Action.REVIEW_DECISION, resource).allowed,
        })
    return sorted(queue, key=lambda r: r["since"])[:limit]


@app.post("/api/v1/reviews/{application_id}/decision", status_code=status.HTTP_201_CREATED, tags=["Reviews"])
async def decide_review(
    application_id: str,
    body: ReviewDecisionRequest,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
    audit: AuditWriter = Depends(get_audit_writer),
):
    """Record an underwriter's decision on an application in manual review."""
    row = await _application(db, application_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)
    resource = await _resource(db, row)
    await require_action(principal, Action.REVIEW_DECISION, resource, audit, {
        "from_status": resource.status, "to_status": body.outcome,
        "reason_code": body.reason_code, "reason": body.reason,
    })
    db.add(DbApplicationStatusLog(
        sk_id_curr=row.sk_id_curr,
        status=body.outcome,
        created_by=principal.sub,
        event_id=f"review:{uuid.uuid4().hex}",
        event_metadata={"reviewer": principal.sub, "from_status": resource.status,
                        "reason_code": body.reason_code, "reason": body.reason},
    ))
    await db.commit()
    return {"application_id": resource.id, "status": body.outcome}


app.include_router(policy_changes_router)


# ---------------------------------------------------------------------------
# Audit trace (E13): auditors reconstruct who did what to one resource.
# ---------------------------------------------------------------------------
@app.get("/api/v1/audit", tags=["Audit"])
async def audit_trace(
    resource: str = Query(..., pattern=r"^(application|policy|customer):[A-Za-z0-9_.:-]{1,64}$"),
    principal: Principal = Depends(get_principal),
    audit: AuditWriter = Depends(get_audit_writer),
    reader: AuditReader | None = Depends(get_audit_reader),
):
    resource_type, resource_id = resource.split(":", 1)
    # The auditor's own search is audited too.
    await require_action(principal, Action.READ_AUDIT, Resource(type=resource_type, id=resource_id), audit)
    if reader is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Audit store is not configured")
    return {"resource": resource, "events": await reader.trace(resource_type, resource_id)}


# ---------------------------------------------------------------------------
# Case notes, internal customer factors and lookups (ADR-0013)
# ---------------------------------------------------------------------------
class CaseNoteRequest(BaseModel):
    kind: str = Field(..., pattern="^(note|concern)$")
    text: str = Field(..., min_length=10, max_length=1000)


@app.post("/api/v1/applications/{application_id}/notes", status_code=status.HTTP_201_CREATED, tags=["Cases"])
async def add_case_note(
    application_id: str,
    body: CaseNoteRequest,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
    audit: AuditWriter = Depends(get_audit_writer),
):
    action = Action.FLAG_CONCERN if body.kind == "concern" else Action.ADD_CASE_NOTE
    row, resource = await _require_application(db, application_id, principal, action, audit,
                                               {"note_length": len(body.text), "concern_type": body.kind})
    db.add(DbCaseNote(sk_id_curr=row.sk_id_curr, kind=body.kind, text=body.text, author_sub=principal.sub))
    await db.commit()
    return {"application_id": resource.id, "kind": body.kind}


@app.get("/api/v1/applications/{application_id}/notes", tags=["Cases"])
async def list_case_notes(
    application_id: str,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
    audit: AuditWriter = Depends(get_audit_writer),
):
    row, _ = await _require_application(db, application_id, principal, Action.READ_APPLICATION, audit)
    rows = (await db.execute(
        select(DbCaseNote).where(DbCaseNote.sk_id_curr == row.sk_id_curr).order_by(DbCaseNote.id)
    )).scalars().all()
    return [{"kind": r.kind, "text": r.text, "author_sub": r.author_sub, "created_at": r.created_at} for r in rows]


@app.get("/api/v1/applications/{application_id}/customer-profile", tags=["Cases"])
async def customer_profile(
    application_id: str,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
    audit: AuditWriter = Depends(get_audit_writer),
    provider=Depends(get_profile_provider),
):
    """Internal factors, only for the application being handled and after consent (ADR-0013)."""
    row, _ = await _require_application(db, application_id, principal, Action.READ_CUSTOMER_PROFILE, audit)
    customer_ref = row.sk_id_curr
    # End the read transaction before calling the warehouse: a slow external call must never
    # hold database locks (seen locally: an idle transaction blocked TRUNCATE for minutes).
    await db.commit()
    try:
        return await asyncio.wait_for(provider.profile(customer_ref), timeout=settings.profile_timeout_seconds)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No history for this customer")
    except Exception as exc:  # timeout or warehouse down: degrade, never hang the case view (E15)
        logger.warning(f"Customer profile unavailable for application {application_id}: {type(exc).__name__}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Customer history is unavailable")


class CustomerLookupRequest(BaseModel):
    """The citizen ID travels in the body, never in a path or query string (ADR-0014)."""

    citizen_id: str
    purpose: Literal["co_applicant", "guarantor", "customer_present"]

    @field_validator("citizen_id")
    @classmethod
    def _citizen_id(cls, value: str) -> str:
        from identity import normalize_citizen_id

        return normalize_citizen_id(value)


@app.post("/api/v1/customers:lookup", tags=["Cases"])
async def lookup_customer(
    body: CustomerLookupRequest,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
    audit: AuditWriter = Depends(get_audit_writer),
    identities: IdentityRepository = Depends(get_identity_repository),
):
    """Exact citizen-ID lookup with a stated purpose; counts and statuses only (ADR-0013)."""
    customer_ref = await identities.customer_ref_for(body.citizen_id)
    rows = (await db.execute(
        select(DbLoanApplication).where(DbLoanApplication.sk_id_curr == customer_ref)
    )).scalars().all() if customer_ref else []
    same_branch = bool(principal.branch_id) and any(r.branch_id == principal.branch_id for r in rows)
    await require_action(principal, Action.LOOKUP_CUSTOMER,
                   Resource(type="customer", id=customer_ref or "unknown", purpose=body.purpose), audit,
                   {"purpose": body.purpose, "result_count": len(rows), "same_branch": same_branch})
    statuses = []
    for row in rows:
        latest = await _latest_status(db, row.sk_id_curr)
        statuses.append(latest.status if latest else "submitted")
    return {"citizen_id_masked": mask_citizen_id(body.citizen_id[-3:]), "found": customer_ref is not None,
            "applications": len(rows), "statuses": statuses, "same_branch": same_branch}
