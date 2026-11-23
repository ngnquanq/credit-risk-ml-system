CREATE TABLE IF NOT EXISTS loan_applications (
    -- Primary Key & Identity
    sk_id_curr VARCHAR(255) PRIMARY KEY,
    
    -- Basic Demographics (User Input - Raw Data)
    code_gender CHAR(1) CHECK (code_gender IN ('M', 'F')),
    birth_date DATE NOT NULL,  -- Store actual birth date, convert to days_birth in analytics
    cnt_children INTEGER DEFAULT 0 CHECK (cnt_children >= 0),
    
    -- Financial Information
    amt_income_total DECIMAL(15,2) NOT NULL CHECK (amt_income_total > 0),
    amt_credit DECIMAL(15,2) NOT NULL CHECK (amt_credit > 0),
    amt_annuity DECIMAL(15,2) CHECK (amt_annuity > 0),
    amt_goods_price DECIMAL(15,2) CHECK (amt_goods_price >= 0),
    
    -- Employment & Personal Details
    name_contract_type VARCHAR(50) DEFAULT 'Cash loans' CHECK (name_contract_type IN ('Cash loans', 'Revolving loans')),
    name_income_type VARCHAR(50) CHECK (name_income_type IN ('Working', 'Commercial associate', 'Pensioner', 'State servant', 'Student', 'Businessman', 'Maternity leave')),
    name_education_type VARCHAR(50) CHECK (name_education_type IN ('Secondary / secondary special', 'Higher education', 'Incomplete higher', 'Lower secondary', 'Academic degree')),
    name_family_status VARCHAR(50) CHECK (name_family_status IN ('Single / not married', 'Married', 'Civil marriage', 'Widow', 'Separated')),
    name_housing_type VARCHAR(50) CHECK (name_housing_type IN ('House / apartment', 'Rented apartment', 'With parents', 'Municipal apartment', 'Office apartment', 'Co-op apartment')),
    
    -- Employment Details
    employment_start_date DATE,  -- When person started current employment, convert to days_employed in analytics
    occupation_type VARCHAR(100),
    organization_type VARCHAR(100),
    
    -- Contact Information Flags
    flag_mobil INTEGER DEFAULT 0 CHECK (flag_mobil IN (0, 1)),
    flag_emp_phone INTEGER DEFAULT 0 CHECK (flag_emp_phone IN (0, 1)),
    flag_work_phone INTEGER DEFAULT 0 CHECK (flag_work_phone IN (0, 1)),
    flag_phone INTEGER DEFAULT 0 CHECK (flag_phone IN (0, 1)),
    flag_email INTEGER DEFAULT 0 CHECK (flag_email IN (0, 1)),
    
    -- Asset Ownership
    flag_own_car INTEGER DEFAULT 0 CHECK (flag_own_car IN (0, 1)),
    flag_own_realty INTEGER DEFAULT 0 CHECK (flag_own_realty IN (0, 1)),
    own_car_age INTEGER CHECK (own_car_age >= 0),
    
    -- Document Storage (MinIO Document IDs) - Ranges from 2 to 21
    document_id_2 VARCHAR(255),   -- Document type 2
    document_id_3 VARCHAR(255),   -- Document type 3
    document_id_4 VARCHAR(255),   -- Document type 4
    document_id_5 VARCHAR(255),   -- Document type 5
    document_id_6 VARCHAR(255),   -- Document type 6
    document_id_7 VARCHAR(255),   -- Document type 7
    document_id_8 VARCHAR(255),   -- Document type 8
    document_id_9 VARCHAR(255),   -- Document type 9
    document_id_10 VARCHAR(255),  -- Document type 10
    document_id_11 VARCHAR(255),  -- Document type 11
    document_id_12 VARCHAR(255),  -- Document type 12
    document_id_13 VARCHAR(255),  -- Document type 13
    document_id_14 VARCHAR(255),  -- Document type 14
    document_id_15 VARCHAR(255),  -- Document type 15
    document_id_16 VARCHAR(255),  -- Document type 16
    document_id_17 VARCHAR(255),  -- Document type 17
    document_id_18 VARCHAR(255),  -- Document type 18
    document_id_19 VARCHAR(255),  -- Document type 19
    document_id_20 VARCHAR(255),  -- Document type 20
    document_id_21 VARCHAR(255),  -- Document type 21
    
    -- Audit Fields
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create computed columns for FLAG_DOCUMENT_X (for ML compatibility)
-- These will be computed by dbt: flag_document_X = CASE WHEN document_id_X IS NOT NULL THEN 1 ELSE 0 END

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_loan_applications_created_at ON loan_applications(created_at);
CREATE INDEX IF NOT EXISTS idx_loan_applications_sk_id ON loan_applications(sk_id_curr);

-- Create updated_at trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_loan_applications_updated_at 
    BEFORE UPDATE ON loan_applications 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Comments for documentation
COMMENT ON TABLE loan_applications IS 'Operational loan applications table with raw user-provided data. ML training transformations happen in analytics pipeline.';
COMMENT ON COLUMN loan_applications.sk_id_curr IS 'Unique identifier for loan application';
COMMENT ON COLUMN loan_applications.birth_date IS 'Customer birth date (raw PII data, converted to days_birth in analytics for privacy)';
COMMENT ON COLUMN loan_applications.employment_start_date IS 'Employment start date (converted to days_employed in analytics pipeline)';
COMMENT ON COLUMN loan_applications.created_at IS 'Application submission timestamp (weekday/hour extracted in analytics)';

