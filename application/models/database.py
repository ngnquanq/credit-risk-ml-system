"""
Database models matching the flattened schema created in migrations.
Uses proper field-based storage instead of JSONB blob.
"""

from sqlalchemy import Column, Integer, String, DateTime, func, Date, Numeric
from sqlalchemy.dialects.postgresql import BIGINT, JSONB
from .base import Base


class LoanApplication(Base):
    """Matches the flattened loan_applications table schema."""
    __tablename__ = "loan_applications"

    # Primary Key & Identity
    sk_id_curr = Column(String(255), primary_key=True)
    
    # Basic Demographics
    code_gender = Column(String(1))
    birth_date = Column(Date, nullable=False)
    cnt_children = Column(Integer, default=0)
    
    # Financial Information
    amt_income_total = Column(Numeric(15,2), nullable=False)
    amt_credit = Column(Numeric(15,2), nullable=False)
    amt_annuity = Column(Numeric(15,2))
    amt_goods_price = Column(Numeric(15,2))
    
    # Employment & Personal Details
    name_contract_type = Column(String(50), default="Cash loans")
    name_income_type = Column(String(50))
    name_education_type = Column(String(50))
    name_family_status = Column(String(50))
    name_housing_type = Column(String(50))
    
    # Employment Details
    employment_start_date = Column(Date)
    occupation_type = Column(String(100))
    organization_type = Column(String(100))
    
    # Contact Information Flags
    flag_mobil = Column(Integer, default=0)
    flag_emp_phone = Column(Integer, default=0)
    flag_work_phone = Column(Integer, default=0)
    flag_phone = Column(Integer, default=0)
    flag_email = Column(Integer, default=0)
    
    # Asset Ownership
    flag_own_car = Column(Integer, default=0)
    flag_own_realty = Column(Integer, default=0)
    own_car_age = Column(Integer)
    
    # Document Storage (MinIO Document IDs) - Ranges from 2 to 21
    document_id_2 = Column(String(255))
    document_id_3 = Column(String(255))
    document_id_4 = Column(String(255))
    document_id_5 = Column(String(255))
    document_id_6 = Column(String(255))
    document_id_7 = Column(String(255))
    document_id_8 = Column(String(255))
    document_id_9 = Column(String(255))
    document_id_10 = Column(String(255))
    document_id_11 = Column(String(255))
    document_id_12 = Column(String(255))
    document_id_13 = Column(String(255))
    document_id_14 = Column(String(255))
    document_id_15 = Column(String(255))
    document_id_16 = Column(String(255))
    document_id_17 = Column(String(255))
    document_id_18 = Column(String(255))
    document_id_19 = Column(String(255))
    document_id_20 = Column(String(255))
    document_id_21 = Column(String(255))
    
    # Audit Fields
    created_at = Column(DateTime, server_default=func.current_timestamp())
    updated_at = Column(DateTime, server_default=func.current_timestamp())


class ApplicationStatusLog(Base):
    """Event sourcing table for application status changes."""
    __tablename__ = "application_status_log"
    
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    sk_id_curr = Column(String(255), nullable=False)  # Foreign key to loan_applications
    
    # Status Information
    status = Column(String(50), nullable=False)
    
    # Metadata
    created_at = Column(DateTime, server_default=func.current_timestamp(), nullable=False)
    created_by = Column(String(100), nullable=False)
    event_metadata = Column(JSONB)  # Using JSONB to match database schema