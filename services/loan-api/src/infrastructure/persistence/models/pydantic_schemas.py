"""
Customer-focused API schemas based on Home Credit data analysis.
Only includes fields that customers can realistically provide.
"""

import re

from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime, date
from enum import Enum


class GenderType(str, Enum):
    MALE = "M"
    FEMALE = "F"


class ContractType(str, Enum):
    CASH_LOANS = "Cash loans"
    REVOLVING_LOANS = "Revolving loans"


class IncomeType(str, Enum):
    WORKING = "Working"
    COMMERCIAL_ASSOCIATE = "Commercial associate"
    PENSIONER = "Pensioner"
    STATE_SERVANT = "State servant"
    BUSINESSMAN = "Businessman"


class EducationType(str, Enum):
    SECONDARY = "Secondary / secondary special"
    HIGHER_EDUCATION = "Higher education"
    INCOMPLETE_HIGHER = "Incomplete higher"
    LOWER_SECONDARY = "Lower secondary"
    ACADEMIC_DEGREE = "Academic degree"


class FamilyStatus(str, Enum):
    SINGLE = "Single / not married"
    MARRIED = "Married" 
    CIVIL_MARRIAGE = "Civil marriage"
    WIDOW = "Widow"
    SEPARATED = "Separated"


class HousingType(str, Enum):
    HOUSE_APARTMENT = "House / apartment"
    RENTING = "Renting"
    WITH_PARENTS = "With parents"
    MUNICIPAL_APARTMENT = "Municipal apartment"
    OFFICE_APARTMENT = "Office apartment"
    CO_OP_APARTMENT = "Co-op apartment"


class ApplicationFields(BaseModel):
    """What an applicant or a loan officer enters about the loan (no identity, no internal keys)."""

    # Basic Demographics 
    # Not asked in the portals and never a model input (ADR-0013, E6); kept optional for KYC data and bias audits.
    code_gender: Optional[GenderType] = Field(None, description="Gender of the applicant (optional, audit only)")
    birth_date: date = Field(..., description="Date of birth")
    cnt_children: int = Field(0, description="Number of children", ge=0)
    
    # Financial Information
    amt_income_total: float = Field(..., description="Total annual income", gt=0)
    amt_credit: float = Field(..., description="Requested credit amount", gt=0)
    amt_annuity: Optional[float] = Field(None, description="Loan annuity", gt=0)
    amt_goods_price: Optional[float] = Field(0, description="Price of goods", ge=0)
    
    # Employment & Personal Details
    name_contract_type: ContractType = Field("Cash loans", description="Type of loan contract")
    name_income_type: IncomeType = Field(..., description="Type of income source")
    name_education_type: EducationType = Field(..., description="Education level")
    name_family_status: FamilyStatus = Field(..., description="Family status")
    name_housing_type: HousingType = Field(..., description="Housing situation")
    
    # Employment Details
    employment_start_date: Optional[date] = Field(None, description="Employment start date")
    occupation_type: Optional[str] = Field(None, description="Occupation/job type")
    organization_type: Optional[str] = Field(None, description="Organization type")
    
    # Contact Information Flags
    flag_mobil: int = Field(0, description="Has mobile phone", ge=0, le=1)
    flag_emp_phone: int = Field(0, description="Has work phone", ge=0, le=1)
    flag_work_phone: int = Field(0, description="Has work phone", ge=0, le=1)
    flag_phone: int = Field(0, description="Has home phone", ge=0, le=1)
    flag_email: int = Field(0, description="Has email address", ge=0, le=1)
    
    # Asset Ownership
    flag_own_car: int = Field(0, description="Owns a car", ge=0, le=1)
    flag_own_realty: int = Field(0, description="Owns house or flat", ge=0, le=1)
    own_car_age: Optional[int] = Field(None, description="Age of car in years", ge=0)
    
    # Document IDs (from MinIO uploads)
    document_ids: Optional[dict[str, str]] = Field(
        None, description="document_id_N -> document_id returned by POST /api/v1/presigned-url"
    )

    # Consent to the credit bureau check (E11); recorded with a timestamp
    bureau_consent: bool = Field(False, description="Applicant consented to the credit bureau check")

    @field_validator("document_ids")
    @classmethod
    def _document_slots(cls, value: Optional[dict[str, str]]) -> Optional[dict[str, str]]:
        for key in value or {}:
            match = re.fullmatch(r"document_id_(\d{1,2})", key)
            if not match or not 2 <= int(match.group(1)) <= 21:
                raise ValueError(f"Unknown document slot {key!r}")
        return value


class ApplicantIn(BaseModel):
    """Identity of the applicant (ADR-0014): stored encrypted, apart from the loan data."""

    full_name: str = Field(..., min_length=2, max_length=120)
    citizen_id: str = Field(..., description="12-digit citizen identity card number (CCCD)")
    phone: str = Field(..., description="Vietnamese mobile number")

    @field_validator("citizen_id")
    @classmethod
    def _citizen_id(cls, value: str) -> str:
        from identity import normalize_citizen_id

        return normalize_citizen_id(value)

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        from identity import normalize_phone

        return normalize_phone(value)


class ApplicationSubmission(ApplicationFields):
    """POST /api/v1/applications. The customer key is resolved by the API from the citizen ID."""

    applicant: ApplicantIn

    model_config = {
        "json_schema_extra": {
            "example": {
                "applicant": {"full_name": "Nguyễn Văn Ví Dụ", "citizen_id": "001099000123", "phone": "0900000123"},
                "birth_date": "1991-03-14",
                "cnt_children": 0,
                "amt_income_total": 180000000,
                "amt_credit": 40000000,
                "amt_annuity": 2035832,
                "name_income_type": "Working",
                "name_education_type": "Higher education",
                "name_family_status": "Married",
                "name_housing_type": "House / apartment",
                "employment_start_date": "2025-06-01",
                "document_ids": {"document_id_2": "<from /api/v1/presigned-url>"},
                "bureau_consent": True,
            }
        }
    }


class LoanApplicationCreate(ApplicationFields):
    """Internal workflow input: the loan data plus the customer key the API resolved."""

    sk_id_curr: str = Field(..., description="Internal customer key; never accepted from callers")


class MaskedApplicant(BaseModel):
    full_name: str
    citizen_id_masked: str
    phone_masked: str


class LoanApplicationResponse(BaseModel):
    """Response schema for loan applications. ``id`` is the opaque public id (ADR-0014)."""
    id: str
    applicant: Optional[MaskedApplicant] = None
    channel: Optional[str] = None
    branch_id: Optional[str] = None
    documents: list[str] = Field(default_factory=list, description="Document slots that hold a file")
    code_gender: Optional[str] = None
    birth_date: date
    cnt_children: int
    amt_income_total: float
    amt_credit: float
    amt_annuity: Optional[float]
    amt_goods_price: Optional[float]
    name_contract_type: str
    name_income_type: str
    name_education_type: str
    name_family_status: str
    name_housing_type: str
    employment_start_date: Optional[date]
    occupation_type: Optional[str]
    organization_type: Optional[str]
    flag_mobil: int
    flag_emp_phone: int
    flag_work_phone: int
    flag_phone: int
    flag_email: int
    flag_own_car: int
    flag_own_realty: int
    own_car_age: Optional[int]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "healthy"
    timestamp: datetime