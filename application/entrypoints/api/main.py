"""
Main FastAPI application entry point.
Home Credit Loan Application API.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime, timedelta
from loguru import logger
from pydantic import BaseModel
from minio import Minio
from minio.error import S3Error
import uuid
import json

from core import settings, get_db, init_db, close_db
from infrastructure.persistence.models.sqlalchemy_models import (
    LoanApplication as DbLoanApplication,
    ApplicationStatusLog as DbApplicationStatusLog
)
from infrastructure.persistence.models import (
    LoanApplicationCreate,
    LoanApplicationResponse,
    DocumentUploadRequest,
    DocumentUploadResponse,
    HealthResponse,
    ApplicationStatus
)
from infrastructure.external.bureau_client import close_bureau_client
from .dependencies import get_submit_loan_workflow
from workflows.submit_loan import SubmitLoanWorkflow

from pydantic import Field

# Tracing
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from core.tracing import setup_tracing, extract_or_create_trace_context

# Initialize tracing
tracer = setup_tracing("api-service", sampling_rate=0.1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting Home Credit Loan API...")
    await init_db()
    yield
    # Shutdown
    logger.info("Shutting down Home Credit Loan API...")
    # Close external clients
    await close_bureau_client()
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
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auto-instrument FastAPI with tracing
FastAPIInstrumentor.instrument_app(app)

# Initialize MinIO client for document uploads (from settings)
minio_client = Minio(
    settings.minio_endpoint,
    access_key=settings.minio_access_key,
    secret_key=settings.minio_secret_key,
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


# Pre-signed URL endpoint for document uploads
@app.post("/api/v1/presigned-url", response_model=PreSignedURLResponse, tags=["Documents"])
async def get_presigned_url(request: PreSignedURLRequest):
    """Generate pre-signed URL for document upload to MinIO with organized folder structure."""
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
    workflow: SubmitLoanWorkflow = Depends(get_submit_loan_workflow)
):
    """
    Create a new loan application (Clean Architecture).
    Delegates to SubmitLoanWorkflow.
    """
    try:
        from workflows.dtos import SubmitLoanInput
        
        # 1. Convert API Schema -> Workflow DTO
        # (Pass all fields as we did in the legacy controller, but cleaner)
        input_dto = SubmitLoanInput(
            **application_data.model_dump()
        )
        
        # 2. Execute Workflow
        output = await workflow.execute(input_dto)
        
        # 3. Convert Workflow Output -> API Response
        # We need to return the full response schema, so we might need to 
        # re-construct it or fetch it. For now, we return a basic response 
        # based on the input + status.
        return LoanApplicationResponse(
            sk_id_curr=output.application_id,
            status=output.status,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            # Map other fields from input for the response
            **application_data.model_dump(exclude={'sk_id_curr'})
        )

    except Exception as e:
        logger.exception(f"Failed to create loan application: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create loan application: {str(e)}"
        )


# Get loan application by customer ID
@app.get(
    "/api/v1/applications/{customer_id}",
    response_model=LoanApplicationResponse,
    tags=["Applications"]
)
async def get_loan_application(
    customer_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get a loan application by customer ID."""
    try:
        result = await db.execute(
            select(DbLoanApplication).where(DbLoanApplication.sk_id_curr == customer_id)
        )
        db_application = result.scalar_one_or_none()
        
        if not db_application:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Application with ID {customer_id} not found"
            )
        
        return LoanApplicationResponse.model_validate(db_application)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get loan application {customer_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve loan application"
        )


# Get application status by customer ID
@app.get(
    "/api/v1/applications/{customer_id}/status",
    tags=["Applications"]
)
async def get_application_status(
    customer_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get current status of loan application using event sourcing."""
    try:
        # Query the current status view
        result = await db.execute(
            select(DbApplicationStatusLog).where(
                DbApplicationStatusLog.sk_id_curr == customer_id
            ).order_by(DbApplicationStatusLog.created_at.desc()).limit(1)
        )
        status_record = result.scalar_one_or_none()
        
        if not status_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Application with ID {customer_id} not found"
            )
        
        return {
            "customer_id": customer_id,
            "status": status_record.status,
            "updated_at": status_record.created_at,
            "updated_by": status_record.created_by,
            "metadata": status_record.event_metadata
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get application status {customer_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve application status"
        )
