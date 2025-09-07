"""
Customer-focused API schemas based on Home Credit data analysis.
Only includes fields that customers can realistically provide.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
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


class DocumentType(int, Enum):
    """Document types based on Home Credit FLAG_DOCUMENT_* fields."""
    PASSPORT = 2
    IDENTITY_CARD = 3
    DRIVERS_LICENSE = 4
    BIRTH_CERTIFICATE = 5
    INCOME_CERTIFICATE = 6
    BANK_STATEMENT = 7
    EMPLOYMENT_LETTER = 8
    TAX_RETURN = 9
    UTILITY_BILL = 10
    PROPERTY_DEED = 11
    MARRIAGE_CERTIFICATE = 12
    DIVORCE_DECREE = 13
    EDUCATION_CERTIFICATE = 14
    MEDICAL_CERTIFICATE = 15
    PENSION_CERTIFICATE = 16
    BUSINESS_LICENSE = 17
    INSURANCE_POLICY = 18
    LOAN_AGREEMENT = 19
    COURT_JUDGMENT = 20
    OTHER_DOCUMENT = 21


class DocumentUpload(BaseModel):
    """Document upload information."""
    document_type: DocumentType = Field(..., description="Type of document")
    file_name: str = Field(..., description="Original filename")
    file_size: int = Field(..., description="File size in bytes")
    file_url: Optional[str] = Field(None, description="URL to uploaded file (set by system)")
    upload_timestamp: Optional[datetime] = Field(None, description="When document was uploaded")
    is_verified: bool = Field(False, description="Whether document has been verified")


class LoanApplicationCreate(BaseModel):
    """Customer loan application matching flattened database schema."""
    
    # Customer Identity
    sk_id_curr: str = Field(..., description="Customer ID")
    
    # Basic Demographics 
    code_gender: GenderType = Field(..., description="Gender of the applicant")
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
    document_ids: Optional[dict] = Field(None, description="Document IDs from uploaded files")

    model_config = {
        "json_schema_extra": {
            "example": {
                "gender": "M",
                "age": 35,
                "children_count": 2,
                "family_status": "Married",
                "education_type": "Higher education",
                "income_type": "Working",
                "annual_income": 180000.0,
                "occupation_type": "Core staff",
                "organization_type": "Business Entity Type 3",
                "employment_years": 5,
                "contract_type": "Cash loans",
                "credit_amount": 406597.5,
                "goods_price": 351000.0,
                "loan_purpose": "Repairs",
                "owns_car": True,
                "car_age": 12,
                "owns_realty": True,
                "housing_type": "House / apartment",
                "has_mobile_phone": True,
                "has_work_phone": False,
                "has_phone": True,
                "has_email": True,
                "family_members_count": 4,
                "documents": [
                    {
                        "document_type": 3,
                        "file_name": "passport.pdf",
                        "file_size": 2048576
                    },
                    {
                        "document_type": 6,
                        "file_name": "salary_certificate.pdf", 
                        "file_size": 1024768
                    }
                ]
            }
        }
    }


class LoanApplicationResponse(BaseModel):
    """Response schema for loan applications."""
    sk_id_curr: str
    code_gender: str
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


class DocumentUploadRequest(BaseModel):
    """Request schema for uploading individual documents."""
    application_id: int = Field(..., description="ID of the loan application")
    document_type: DocumentType = Field(..., description="Type of document being uploaded")
    
    
class DocumentUploadResponse(BaseModel):
    """Response after successful document upload."""
    id: int
    application_id: int
    document_type: DocumentType
    file_name: str
    file_size: int
    file_url: str
    upload_timestamp: datetime
    is_verified: bool
    

class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "healthy"
    timestamp: datetime