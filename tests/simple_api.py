#!/usr/bin/env python3
"""
Simplified FastAPI service for Home Credit loan applications
Handles loan application submissions and document uploads via pre-signed URLs
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, date
import psycopg2
from minio import Minio
from minio.error import S3Error
import uuid
import os
from dotenv import load_dotenv
from typing import Optional
import logging
import json

# Load environment variables
load_dotenv("application/.env")

# Configuration
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "loan-documents")

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5434")
POSTGRES_DB = os.getenv("POSTGRES_DB", "operations")
POSTGRES_USER = os.getenv("POSTGRES_USER", "ops_admin")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "ops_password")

# Initialize FastAPI
app = FastAPI(title="Home Credit API Service", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "*"],  # Streamlit default port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize MinIO client
minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False
)

# Ensure bucket exists
try:
    if not minio_client.bucket_exists(MINIO_BUCKET):
        minio_client.make_bucket(MINIO_BUCKET)
        print(f"✅ Created MinIO bucket: {MINIO_BUCKET}")
    else:
        print(f"✅ MinIO bucket exists: {MINIO_BUCKET}")
except Exception as e:
    print(f"❌ Failed to initialize MinIO: {e}")

# Pydantic models
class PreSignedURLRequest(BaseModel):
    document_type: int  # 2-21
    file_extension: str

class PreSignedURLResponse(BaseModel):
    upload_url: str
    document_id: str

class LoanApplicationRequest(BaseModel):
    # Basic Demographics 
    code_gender: str
    birth_date: str  # ISO format date string
    cnt_children: int = 0
    
    # Financial Information
    amt_income_total: float
    amt_credit: float
    amt_annuity: Optional[float] = None
    amt_goods_price: Optional[float] = 0.0
    
    # Employment & Personal Details
    name_contract_type: str = "Cash loans"
    name_income_type: str
    name_education_type: str
    name_family_status: str
    name_housing_type: str
    
    # Employment Details
    employment_start_date: Optional[str] = None  # ISO format date string
    occupation_type: Optional[str] = None
    organization_type: Optional[str] = None
    
    # Contact Information Flags
    flag_mobil: int = 0
    flag_emp_phone: int = 0
    flag_work_phone: int = 0
    flag_phone: int = 0
    flag_email: int = 0
    
    # Asset Ownership
    flag_own_car: int = 0
    flag_own_realty: int = 0
    own_car_age: Optional[int] = None
    
    # Document IDs (from MinIO uploads)
    document_ids: Optional[dict] = None

class HealthResponse(BaseModel):
    status: str = "healthy"
    timestamp: datetime

def get_db_connection():
    """Create database connection"""
    return psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        database=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD
    )

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        database_connected = True
    except Exception as e:
        print(f"Database health check failed: {e}")
        database_connected = False
    
    return HealthResponse(
        status="healthy" if database_connected else "unhealthy",
        timestamp=datetime.now()
    )

@app.post("/api/v1/presigned-url", response_model=PreSignedURLResponse)
async def get_presigned_url(request: PreSignedURLRequest):
    """Generate pre-signed URL for document upload to MinIO"""
    try:
        # Generate unique document ID
        doc_id = f"doc_{uuid.uuid4().hex}"
        object_name = f"{doc_id}.{request.file_extension}"
        
        # Generate pre-signed URL (valid for 1 hour)
        from datetime import timedelta
        upload_url = minio_client.presigned_put_object(
            MINIO_BUCKET,
            object_name,
            expires=timedelta(hours=1)  # 1 hour
        )
        
        print(f"Generated pre-signed URL for document type {request.document_type}: {doc_id}")
        
        return PreSignedURLResponse(
            upload_url=upload_url,
            document_id=doc_id
        )
        
    except S3Error as e:
        print(f"MinIO error generating pre-signed URL: {e}")
        raise HTTPException(status_code=500, detail=f"MinIO error: {str(e)}")
    except Exception as e:
        print(f"Failed to generate pre-signed URL: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate pre-signed URL: {str(e)}")

@app.post("/api/v1/applications")
async def create_loan_application(application: LoanApplicationRequest):
    """Submit loan application with optional document references"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Generate unique customer ID
        customer_id = f"CUSTOMER_{uuid.uuid4().hex[:8].upper()}"
        
        # Parse dates
        birth_date = datetime.fromisoformat(application.birth_date).date()
        employment_start_date = None
        if application.employment_start_date:
            employment_start_date = datetime.fromisoformat(application.employment_start_date).date()
        
        # Prepare document ID fields (2-21)
        doc_fields = {f"document_id_{i}": None for i in range(2, 22)}
        if application.document_ids:
            for doc_type, doc_id in application.document_ids.items():
                if doc_type.startswith("document_id_"):
                    doc_fields[doc_type] = doc_id
        
        # Simplified insert with just required fields
        insert_query = """
        INSERT INTO loan_applications (
            sk_id_curr, code_gender, birth_date, cnt_children,
            amt_income_total, amt_credit, amt_annuity, amt_goods_price,
            name_contract_type, name_income_type, name_education_type,
            name_family_status, name_housing_type, employment_start_date,
            occupation_type, organization_type, flag_mobil, flag_emp_phone,
            flag_work_phone, flag_phone, flag_email, flag_own_car,
            flag_own_realty, own_car_age, document_id_2, created_at, updated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        cursor.execute(insert_query, (
            customer_id, application.code_gender, birth_date, application.cnt_children,
            application.amt_income_total, application.amt_credit, application.amt_annuity, application.amt_goods_price,
            application.name_contract_type, application.name_income_type, application.name_education_type,
            application.name_family_status, application.name_housing_type, employment_start_date,
            application.occupation_type, application.organization_type, application.flag_mobil, application.flag_emp_phone,
            application.flag_work_phone, application.flag_phone, application.flag_email, application.flag_own_car,
            application.flag_own_realty, application.own_car_age,
            doc_fields.get("document_id_2"),  # Only include document_id_2 for now
            datetime.now(), datetime.now()
        ))
        
        # Insert initial status log
        status_query = """
        INSERT INTO application_status_log (sk_id_curr, status, created_by, metadata)
        VALUES (%s, %s, %s, %s)
        """
        
        cursor.execute(status_query, (
            customer_id,
            "submitted",
            "api-service",
            '{"source": "api_endpoint", "submission_time": "' + datetime.now().isoformat() + '"}'
        ))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"Successfully created loan application: {customer_id}")
        
        return {"customer_id": customer_id, "status": "submitted", "message": "Application submitted successfully"}
        
    except Exception as e:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()
        print(f"Failed to submit application: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to submit application: {str(e)}")

@app.get("/api/v1/applications/{customer_id}/status")
async def get_application_status(customer_id: str):
    """Get current status of loan application"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT status, created_at, created_by, metadata 
            FROM application_status_log 
            WHERE sk_id_curr = %s 
            ORDER BY created_at DESC 
            LIMIT 1
        """, (customer_id,))
        result = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if result:
            return {
                "customer_id": customer_id,
                "status": result[0],
                "updated_at": result[1],
                "updated_by": result[2],
                "metadata": result[3]
            }
        else:
            raise HTTPException(status_code=404, detail="Application not found")
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"Failed to get application status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get application status: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Home Credit API Service...")
    uvicorn.run(app, host="0.0.0.0", port=8000)