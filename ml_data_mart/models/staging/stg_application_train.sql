{{
  config(
    materialized='view',
    description='Staging model for application training data with basic cleaning'
  )
}}

-- This demonstrates basic dbt concepts:
-- 1. Source references using source() macro
-- 2. Jinja templating with curly braces
-- 3. Basic data transformations
-- 4. Column aliasing and type casting
-- 5. Comments and documentation

SELECT
    -- Primary key
    SK_ID_CURR as application_id,
    
    -- Target variable (what we're predicting)
    TARGET as is_default,
    
    -- Core application features (from our 26 selected features)
    AMT_CREDIT as loan_amount,
    AMT_ANNUITY as annuity_amount,
    AMT_GOODS_PRICE as goods_price,
    AMT_INCOME_TOTAL as total_income,
    
    -- External scores (top importance features)
    EXT_SOURCE_1 as external_score_1,
    EXT_SOURCE_2 as external_score_2, 
    EXT_SOURCE_3 as external_score_3,
    
    -- Demographic features
    DAYS_BIRTH as days_birth,
    DAYS_EMPLOYED as days_employed,
    DAYS_ID_PUBLISH as days_id_published,
    CNT_CHILDREN as children_count,
    
    -- Categorical features
    CODE_GENDER as gender,
    NAME_EDUCATION_TYPE as education_type,
    NAME_FAMILY_STATUS as family_status,
    NAME_INCOME_TYPE as income_type,
    ORGANIZATION_TYPE as organization_type,
    
    -- Geographic feature
    REGION_POPULATION_RELATIVE as region_population_relative,
    
    -- Derived fields with transformations
    CASE 
        WHEN DAYS_BIRTH IS NOT NULL 
        THEN round(-DAYS_BIRTH / 365.25, 1) 
        ELSE NULL 
    END as age_years,
    
    CASE 
        WHEN AMT_CREDIT > 0 AND AMT_INCOME_TOTAL > 0 
        THEN round(AMT_CREDIT / AMT_INCOME_TOTAL, 2) 
        ELSE NULL 
    END as credit_income_ratio,
    
    -- Data quality flags
    CASE 
        WHEN EXT_SOURCE_1 IS NULL AND EXT_SOURCE_2 IS NULL AND EXT_SOURCE_3 IS NULL 
        THEN 1 
        ELSE 0 
    END as missing_all_external_scores,
    
    -- Metadata
    current_timestamp() as dbt_loaded_at

FROM {{ source('application_dwh', 'application_train') }}

-- Basic data quality filters
WHERE SK_ID_CURR IS NOT NULL
  AND AMT_CREDIT > 0  -- Valid loan amount

-- Optional: Add a limit for development/testing
{% if target.name == 'dev' %}
LIMIT 10000
{% endif %}