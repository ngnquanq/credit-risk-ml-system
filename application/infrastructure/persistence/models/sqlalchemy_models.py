"""
Database models matching the flattened schema created in migrations.
Uses proper field-based storage instead of JSONB blob.
"""

import uuid

from sqlalchemy import Column, Integer, String, DateTime, func, Date, Numeric, Text, Uuid
from sqlalchemy.dialects.postgresql import BIGINT, JSONB
from .base import Base


class LoanApplication(Base):
    """Matches the flattened loan_applications table schema."""
    __tablename__ = "loan_applications"

    # Primary Key & Identity: sk_id_curr is the internal customer key and never leaves the API;
    # public_id is the opaque id used in every URL and response (ADR-0014, migration 006).
    sk_id_curr = Column(String(255), primary_key=True)
    public_id = Column(Uuid(as_uuid=False), nullable=False, unique=True, default=lambda: str(uuid.uuid4()))
    
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
    # Ownership and consent (E11, migration 004)
    channel = Column(String(10), nullable=False, default="staff")  # staff | self
    created_by_sub = Column(String(64))   # who entered it (staff user or the applicant)
    applicant_sub = Column(String(64))    # customer-realm subject for self-service applications
    branch_id = Column(String(16))        # staff applications only
    bureau_consent_at = Column(DateTime)  # when the applicant consented to the bureau check

    created_at = Column(DateTime, server_default=func.current_timestamp())
    updated_at = Column(DateTime, server_default=func.current_timestamp())


class ApplicationStatusLog(Base):
    """Event sourcing table for application status changes."""
    __tablename__ = "application_status_log"
    
    # BIGSERIAL in PostgreSQL; INTEGER in SQLite so the test database autoincrements.
    id = Column(BIGINT().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=True)
    sk_id_curr = Column(String(255), nullable=False)  # Foreign key to loan_applications
    
    # Status Information
    status = Column(String(50), nullable=False)
    
    # Metadata
    created_at = Column(DateTime, server_default=func.current_timestamp(), nullable=False)
    created_by = Column(String(100), nullable=False)
    # Idempotency key of the decision event that produced this row (E5, migration 003)
    event_id = Column(String(64), nullable=True)
    # Map attribute 'event_metadata' to DB column named 'metadata' to avoid
    # clashing with SQLAlchemy's Base.metadata and match migration DDL.
    event_metadata = Column('metadata', JSONB)


class PolicyChange(Base):
    """Proposed decision-band changes; active only after a second risk manager approves (E11, migration 004)."""
    __tablename__ = "policy_change"

    id = Column(BIGINT().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=True)
    proposed_by = Column(String(64), nullable=False)
    approved_by = Column(String(64))
    payload = Column(JSONB, nullable=False)
    state = Column(String(12), nullable=False, default="proposed")
    created_at = Column(DateTime, server_default=func.current_timestamp(), nullable=False)
    decided_at = Column(DateTime)


class CaseNote(Base):
    """Verification notes and concerns from loan officers (ADR-0013, migration 005)."""
    __tablename__ = "case_note"

    id = Column(BIGINT().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=True)
    sk_id_curr = Column(String(255), nullable=False)
    kind = Column(String(10), nullable=False)  # note | concern
    text = Column(String(1000), nullable=False)
    author_sub = Column(String(64), nullable=False)
    created_at = Column(DateTime, server_default=func.current_timestamp(), nullable=False)



class ApplicantIdentity(Base):
    """Applicant personal data, encrypted per field; never replicated by CDC (ADR-0014, migration 006)."""
    __tablename__ = "applicant_identity"

    id = Column(BIGINT().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=True)
    customer_ref = Column(String(255), nullable=False, unique=True)
    citizen_id_hmac = Column(String(64), nullable=False, unique=True)
    full_name_enc = Column(Text, nullable=False)
    citizen_id_enc = Column(Text, nullable=False)
    phone_enc = Column(Text, nullable=False)
    citizen_id_last3 = Column(String(3), nullable=False)
    phone_last3 = Column(String(3), nullable=False)
    key_id = Column(String(16), nullable=False)
    created_at = Column(DateTime, server_default=func.current_timestamp(), nullable=False)
