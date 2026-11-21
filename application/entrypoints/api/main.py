"""
Main FastAPI application entry point.
Home Credit Loan Application API.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime, timedelta
from loguru import logger
from pydantic import BaseModel
from minio import Minio
from minio.error import S3Error
import uuid

from core import settings, get_db, init_db, close_db
from infrastructure.persistence.models.sqlalchemy_models import (
    LoanApplication as DbLoanApplication,
    ApplicationStatusLog as DbApplicationStatusLog,
    PolicyChange as DbPolicyChange,
)
from infrastructure.persistence.models import (
    LoanApplicationCreate,
    LoanApplicationResponse,
    HealthResponse,
)
from .dependencies import get_audit_writer, get_submit_loan_workflow
from .security import get_principal
from audit.writer import AuditEvent, AuditWriter
from authz import Action, Principal, Resource, authorize
from authz.policy import CUSTOMER_REALM
from decisions.reasons import reason_texts
from workflows.submit_loan import SubmitLoanWorkflow

from pydantic import Field

# Tracing
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from core.tracing import setup_tracing

# Initialize tracing
tracer = setup_tracing("api-service", sampling_rate=0.1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting Home Credit Loan API...")
    if not settings.oidc_issuer_list and not settings.debug:
        # E11: never serve /api/v1 without a trusted identity provider outside debug mode.
        raise RuntimeError("APP_OIDC_ISSUERS is empty; refusing to start without token verification")
    await init_db()
    yield
    # Shutdown
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
    allow_headers=["Content-Type", "Authorization"],
)

# Auto-instrument FastAPI with tracing
FastAPIInstrumentor.instrument_app(app)

# Initialize MinIO client for document uploads (from settings)
minio_client = Minio(
    settings.minio_endpoint,
    access_key=settings.minio_access_key.get_secret_value() if settings.minio_access_key else None,
    secret_key=settings.minio_secret_key.get_secret_value() if settings.minio_secret_key else None,
    secure=settings.minio_secure,
)

# Ensure bucket exists
try:
    if not minio_client.bucket_exists(settings.minio_bucket):
        minio_client.make_bucket(settings.minio_bucket)
        logger.info(f"Created MinIO bucket: {settings.minio_bucket}")
    else:
        logger.info(f"MinIO bucket exists: {settings.minio_bucket}")
except Exception as e:
    logger.error(f"Failed to initialize MinIO: {e}")

# Document type to folder mapping
DOCUMENT_FOLDERS = {
    2: "identity",           # Passport/ID
    3: "financial/income",   # Income proof  
    4: "employment",         # Employment certificate
    5: "financial/banking",  # Bank statement
    6: "personal",          # Utility bills
    7: "personal",          # Property ownership
    8: "personal",          # Vehicle registration
    9: "financial/insurance", # Insurance policy
    10: "financial/tax",     # Tax returns
    11: "personal",         # Medical certificate
    12: "personal",         # Education certificate
    13: "personal",         # Marriage certificate
    14: "personal",         # Divorce certificate
    15: "identity",         # Birth certificate
    16: "financial/pension", # Pension certificate
    17: "personal",         # Military service
    18: "employment",       # Business license
    19: "financial/credit", # Credit report
    20: "employment",       # Reference letter
    21: "other",           # Other document
} # These are all make up, nothing is real

# Pydantic models for document upload
class PreSignedURLRequest(BaseModel):
    sk_id_curr: str = Field(..., description="Customer ID (sk_id_curr) used for folder organization")
    document_type: int = Field(..., description="Document type (2-21)")
    file_extension: str = Field(..., description="File extension (pdf, jpg, png)")

class PreSignedURLResponse(BaseModel):
    upload_url: str
    document_id: str


# Health check endpoint
@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check(db: AsyncSession = Depends(get_db)):
    """Health check endpoint."""
    try:
        # Test database connection
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
# Authorization helpers (E11): load only what the policy needs, decide, audit.
# ---------------------------------------------------------------------------
async def _latest_status(db: AsyncSession, customer_id: str):
    result = await db.execute(
        select(DbApplicationStatusLog)
        .where(DbApplicationStatusLog.sk_id_curr == customer_id)
        .order_by(DbApplicationStatusLog.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _application_resource(db: AsyncSession, customer_id: str) -> Resource | None:
    row = (
        await db.execute(select(DbLoanApplication).where(DbLoanApplication.sk_id_curr == customer_id))
    ).scalar_one_or_none()
    if row is None:
        return None
    latest = await _latest_status(db, customer_id)
    return Resource(
        type="application",
        id=customer_id,
        channel=row.channel,
        applicant_sub=row.applicant_sub,
        created_by_sub=row.created_by_sub,
        branch_id=row.branch_id,
        status=latest.status if latest else "submitted",
        consent_recorded=row.bureau_consent_at is not None,
    )


def _new_application_resource(principal: Principal, customer_id: str) -> Resource:
    if principal.realm == CUSTOMER_REALM:
        return Resource(type="application", id=customer_id, channel="self", applicant_sub=principal.sub,
                        created_by_sub=principal.sub)
    return Resource(type="application", id=customer_id, channel="staff", created_by_sub=principal.sub,
                    branch_id=principal.branch_id)


async def _require(principal: Principal, action: Action, resource: Resource, audit: AuditWriter,
                   details: dict | None = None) -> None:
    decision = authorize(principal, action, resource)
    await audit.record(AuditEvent(
        actor_sub=principal.sub,
        actor_realm=principal.realm,
        actor_roles=tuple(principal.roles),
        action=action.value,
        resource_type=resource.type,
        resource_id=resource.id or "-",
        outcome="allowed" if decision.allowed else "denied",
        details={"rule": decision.rule, **(details or {})},
    ))
    if not decision.allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": "forbidden", "rule": decision.rule})


async def _require_application(db: AsyncSession, customer_id: str, principal: Principal, action: Action,
                               audit: AuditWriter) -> Resource:
    resource = await _application_resource(db, customer_id)
    if resource is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Application with ID {customer_id} not found")
    await _require(principal, action, resource, audit)
    return resource


# Pre-signed URL endpoint for document uploads
@app.post("/api/v1/presigned-url", response_model=PreSignedURLResponse, tags=["Documents"])
async def get_presigned_url(
    request: PreSignedURLRequest,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
    audit: AuditWriter = Depends(get_audit_writer),
):
    """Generate pre-signed URL for document upload to MinIO with organized folder structure."""
    # Uploading for an application is part of submitting it: same ownership rules (E11).
    resource = await _application_resource(db, request.sk_id_curr) or _new_application_resource(principal, request.sk_id_curr)
    await _require(principal, Action.SUBMIT_APPLICATION, resource, audit)
    try:
        # Validate document type
        if request.document_type not in DOCUMENT_FOLDERS:
            raise HTTPException(status_code=400, detail=f"Invalid document type: {request.document_type}")

        # Validate and sanitize sk_id_curr and extension
        sk_id_curr = (request.sk_id_curr or "").strip()
        if not sk_id_curr:
            raise HTTPException(status_code=400, detail="sk_id_curr is required")

        # Prevent path traversal and unsafe characters
        import re
        safe_sk = re.sub(r"[^A-Za-z0-9_.:-]", "_", sk_id_curr)
        if safe_sk != sk_id_curr:
            logger.warning(f"Sanitized sk_id_curr from '{sk_id_curr}' to '{safe_sk}' for object key safety")
        sk_id_curr = safe_sk

        ext = (request.file_extension or "").lstrip(".").lower()
        allowed_exts = {"pdf", "jpg", "jpeg", "png"}
        if ext not in allowed_exts:
            raise HTTPException(status_code=400, detail=f"Unsupported file extension: {ext}")

        # Generate unique document ID
        doc_id = f"doc_{uuid.uuid4().hex}"
        
        # Get folder for this document type
        folder = DOCUMENT_FOLDERS[request.document_type]
        
        # Create organized object path: {sk_id_curr}/{folder}/{doc_id}.{extension}
        # Each sk_id_curr has its own folder inside the bucket (no extra prefix)
        object_name = f"{sk_id_curr}/{folder}/{doc_id}.{ext}"
        
        # Generate pre-signed URL with configurable expiry
        upload_url = minio_client.presigned_put_object(
            settings.minio_bucket,
            object_name,
            expires=timedelta(minutes=settings.minio_presigned_expiry_minutes)
        )
        
        logger.info(
            f"Generated pre-signed URL for sk_id_curr={sk_id_curr}, type={request.document_type} ({folder}), doc_id={doc_id}"
        )
        
        return PreSignedURLResponse(
            upload_url=upload_url,
            document_id=doc_id
        )
        
    except HTTPException:
        raise
    except S3Error as e:
        logger.error(f"MinIO error generating pre-signed URL: {e}")
        raise HTTPException(status_code=500, detail=f"MinIO error: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to generate pre-signed URL: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate pre-signed URL: {str(e)}")


@app.post(
    "/api/v1/applications",
    response_model=LoanApplicationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Applications"]
)
async def create_loan_application(
    application_data: LoanApplicationCreate,
    workflow: SubmitLoanWorkflow = Depends(get_submit_loan_workflow),
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
    audit: AuditWriter = Depends(get_audit_writer),
):
    """Create a loan application. Ownership comes from the verified caller, never from the body."""
    if await _application_resource(db, application_data.sk_id_curr) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Application already exists")
    resource = _new_application_resource(principal, application_data.sk_id_curr)
    await _require(principal, Action.SUBMIT_APPLICATION, resource, audit,
                   {"channel": resource.channel, "branch_id": resource.branch_id,
                    "consent": application_data.bureau_consent})
    ownership = {
        "channel": resource.channel,
        "created_by_sub": resource.created_by_sub,
        "applicant_sub": resource.applicant_sub,
        "branch_id": resource.branch_id,
        "bureau_consent_at": datetime.utcnow() if application_data.bureau_consent else None,
    }
    try:
        from workflows.dtos import SubmitLoanInput

        output = await workflow.execute(SubmitLoanInput(**application_data.model_dump()), ownership)
        return LoanApplicationResponse(
            sk_id_curr=output.application_id,
            status=output.status,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            **application_data.model_dump(exclude={'sk_id_curr', 'bureau_consent'})
        )
    except Exception as e:
        logger.exception(f"Failed to create loan application: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create loan application",
        )


@app.get(
    "/api/v1/applications/{customer_id}",
    response_model=LoanApplicationResponse,
    tags=["Applications"]
)
async def get_loan_application(
    customer_id: str,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
    audit: AuditWriter = Depends(get_audit_writer),
):
    """Get a loan application (personal data) by customer ID."""
    await _require_application(db, customer_id, principal, Action.READ_APPLICATION, audit)
    row = (
        await db.execute(select(DbLoanApplication).where(DbLoanApplication.sk_id_curr == customer_id))
    ).scalar_one()
    return LoanApplicationResponse.model_validate(row)


@app.get("/api/v1/applications/{customer_id}/status", tags=["Applications"])
async def get_application_status(
    customer_id: str,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
    audit: AuditWriter = Depends(get_audit_writer),
):
    """Latest status; ``submitted`` until a decision is recorded (E5)."""
    await _require_application(db, customer_id, principal, Action.READ_DECISION, audit)
    latest = await _latest_status(db, customer_id)
    if latest is None:
        return {"customer_id": customer_id, "status": "submitted", "updated_at": None, "updated_by": None}
    return {
        "customer_id": customer_id,
        "status": latest.status,
        "updated_at": latest.created_at,
        "updated_by": latest.created_by,
    }


@app.get("/api/v1/applications/{customer_id}/decision", tags=["Decisions"])
async def get_decision(
    customer_id: str,
    locale: str = Query("vi", pattern="^(vi|en)$"),
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
    audit: AuditWriter = Depends(get_audit_writer),
):
    """Decision with plain-language reasons. No score or contributions (ADR-0013)."""
    await _require_application(db, customer_id, principal, Action.READ_DECISION, audit)
    latest = await _latest_status(db, customer_id)
    if latest is None:
        return {"customer_id": customer_id, "status": "submitted", "decided_at": None, "reasons": []}
    codes = list((latest.event_metadata or {}).get("reason_codes") or [])
    return {
        "customer_id": customer_id,
        "status": latest.status,
        "decided_at": latest.created_at,
        "reasons": reason_texts(codes, locale) if latest.status != "approved" else [],
    }


@app.get("/api/v1/applications/{customer_id}/explanation", tags=["Decisions"])
async def get_explanation(
    customer_id: str,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
    audit: AuditWriter = Depends(get_audit_writer),
):
    """Score, band, contributions and versions of the automated decision (underwriter, auditor)."""
    await _require_application(db, customer_id, principal, Action.READ_EXPLANATION, audit)
    row = (
        await db.execute(
            select(DbApplicationStatusLog)
            .where(DbApplicationStatusLog.sk_id_curr == customer_id,
                   DbApplicationStatusLog.created_by == "decision-recorder")
            .order_by(DbApplicationStatusLog.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No automated decision recorded yet")
    meta = row.event_metadata or {}
    return {
        "customer_id": customer_id,
        "status": row.status,
        "decided_at": row.created_at,
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
        await _require(principal, Action.CLAIM_REVIEW, Resource(type="review_queue", id="-"), audit)
    rows = (await db.execute(select(DbApplicationStatusLog).order_by(DbApplicationStatusLog.id))).scalars().all()
    latest: dict[str, object] = {}
    for row in rows:
        latest[row.sk_id_curr] = row
    queue = []
    for sk_id_curr, row in latest.items():
        if row.status != "manual_review":
            continue
        resource = await _application_resource(db, sk_id_curr)
        meta = row.event_metadata or {}
        queue.append({
            "customer_id": sk_id_curr,
            "since": row.created_at,
            "score": meta.get("score"),
            "reasons": meta.get("reasons", []),
            "branch_id": resource.branch_id if resource else None,
            "can_review": bool(resource) and authorize(principal, Action.REVIEW_DECISION, resource).allowed,
        })
    return sorted(queue, key=lambda r: r["since"])[:limit]


@app.post("/api/v1/reviews/{customer_id}/decision", status_code=status.HTTP_201_CREATED, tags=["Reviews"])
async def decide_review(
    customer_id: str,
    body: ReviewDecisionRequest,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
    audit: AuditWriter = Depends(get_audit_writer),
):
    """Record an underwriter's decision on an application in manual review."""
    resource = await _application_resource(db, customer_id)
    if resource is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Application with ID {customer_id} not found")
    await _require(principal, Action.REVIEW_DECISION, resource, audit, {
        "from_status": resource.status, "to_status": body.outcome,
        "reason_code": body.reason_code, "reason": body.reason,
    })
    db.add(DbApplicationStatusLog(
        sk_id_curr=customer_id,
        status=body.outcome,
        created_by=principal.sub,
        event_id=f"review:{uuid.uuid4().hex}",
        event_metadata={"reviewer": principal.sub, "from_status": resource.status,
                        "reason_code": body.reason_code, "reason": body.reason},
    ))
    await db.commit()
    return {"customer_id": customer_id, "status": body.outcome}


# ---------------------------------------------------------------------------
# Decision policy changes (E11): proposed by one risk manager, approved by another.
# The scoring service picks up the active bands at its next rollout (SCORING_APPROVE_BELOW,
# SCORING_REJECT_ABOVE); pushing them automatically is a follow-up.
# ---------------------------------------------------------------------------
class PolicyChangeRequest(BaseModel):
    approve_below: float = Field(..., gt=0, lt=1)
    reject_above: float = Field(..., gt=0, lt=1)
    rationale: str = Field(..., min_length=10, max_length=1000)


class PolicyDecisionRequest(BaseModel):
    approve: bool
    comment: str = Field("", max_length=1000)


def _policy_out(row: DbPolicyChange) -> dict:
    return {"id": row.id, "state": row.state, "payload": row.payload, "proposed_by": row.proposed_by,
            "approved_by": row.approved_by, "created_at": row.created_at, "decided_at": row.decided_at}


@app.get("/api/v1/policy-changes", tags=["Policy"])
async def list_policy_changes(
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
    audit: AuditWriter = Depends(get_audit_writer),
):
    await _require(principal, Action.PROPOSE_POLICY_CHANGE, Resource(type="policy", id="-"), audit)
    rows = (await db.execute(select(DbPolicyChange).order_by(DbPolicyChange.id.desc()).limit(50))).scalars().all()
    return [_policy_out(r) for r in rows]


@app.post("/api/v1/policy-changes", status_code=status.HTTP_201_CREATED, tags=["Policy"])
async def propose_policy_change(
    body: PolicyChangeRequest,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
    audit: AuditWriter = Depends(get_audit_writer),
):
    if not body.approve_below <= body.reject_above:
        raise HTTPException(status_code=422, detail="approve_below must not exceed reject_above")
    payload = {"approve_below": body.approve_below, "reject_above": body.reject_above, "rationale": body.rationale}
    await _require(principal, Action.PROPOSE_POLICY_CHANGE, Resource(type="policy", id="new"), audit,
                   {"payload": payload})
    row = DbPolicyChange(proposed_by=principal.sub, payload=payload, state="proposed")
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _policy_out(row)


@app.post("/api/v1/policy-changes/{change_id}/decision", tags=["Policy"])
async def decide_policy_change(
    change_id: int,
    body: PolicyDecisionRequest,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
    audit: AuditWriter = Depends(get_audit_writer),
):
    row = (await db.execute(select(DbPolicyChange).where(DbPolicyChange.id == change_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy change not found")
    if row.state != "proposed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Policy change is {row.state}")
    await _require(principal, Action.APPROVE_POLICY_CHANGE,
                   Resource(type="policy", id=str(change_id), proposed_by=row.proposed_by), audit,
                   {"payload": row.payload, "proposed_by": row.proposed_by})
    now = datetime.utcnow()
    if body.approve:
        for active in (await db.execute(select(DbPolicyChange).where(DbPolicyChange.state == "active"))).scalars():
            active.state = "superseded"
        row.state, row.approved_by = "active", principal.sub
    else:
        row.state = "rejected"
    row.decided_at = now
    await db.commit()
    return _policy_out(row)
