"""
Main FastAPI application entry point.
Home Credit Loan Application API.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime
from loguru import logger

from application.core import settings, get_db, init_db, close_db
from application.models import (
    LoanApplication,
    LoanApplicationCreate,
    LoanApplicationResponse,
    HealthResponse
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting Home Credit Loan API...")
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
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


# Loan application creation endpoint
@app.post(
    "/api/v1/applications", 
    response_model=LoanApplicationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Applications"]
)
async def create_loan_application(
    application_data: LoanApplicationCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new loan application.
    
    - **user_id**: Unique identifier for the customer
    - **gender**: Customer gender (M/F)  
    - **age**: Customer age in years
    - **annual_income**: Customer's annual income
    - **credit_amount**: Requested loan amount
    - **documents**: List of uploaded documents
    - And many more fields...
    
    Returns the created application with assigned ID and status.
    """
    try:
        logger.info(f"Creating loan application for user_id: {application_data.user_id}")
        
        # Convert Pydantic model to dict for JSONB storage
        application_dict = application_data.model_dump()
        
        # Create database record
        db_application = LoanApplication(
            user_id=application_data.user_id,
            application_data=application_dict,
            status="submitted"
        )
        
        # Save to database
        db.add(db_application)
        await db.flush()  # Get the ID without committing
        await db.refresh(db_application)
        
        logger.info(f"Successfully created loan application with ID: {db_application.id}")
        
        # Return response
        return LoanApplicationResponse(
            id=db_application.id,
            user_id=db_application.user_id,
            application_data=db_application.application_data,
            status=db_application.status,
            created_at=db_application.created_at,
            updated_at=db_application.updated_at
        )
        
    except Exception as e:
        logger.error(f"Failed to create loan application: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create loan application"
        )


# Get loan application by ID
@app.get(
    "/api/v1/applications/{application_id}",
    response_model=LoanApplicationResponse,
    tags=["Applications"]
)
async def get_loan_application(
    application_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get a loan application by ID."""
    try:
        result = await db.execute(
            select(LoanApplication).where(LoanApplication.id == application_id)
        )
        db_application = result.scalar_one_or_none()
        
        if not db_application:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Application with ID {application_id} not found"
            )
        
        return LoanApplicationResponse(
            id=db_application.id,
            user_id=db_application.user_id,
            application_data=db_application.application_data,
            status=db_application.status,
            created_at=db_application.created_at,
            updated_at=db_application.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get loan application {application_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve loan application"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "application.api.main:app", 
        host=settings.api_host, 
        port=settings.api_port,
        reload=settings.debug
    )