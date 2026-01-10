{{
  config(
    materialized='table',
    description='Application base features (no TARGET) for modeling. Columns restricted to the approved set.'
  )
}}

SELECT
    -- keys
    SK_ID_CURR,

    -- numeric amounts
    CNT_CHILDREN,
    AMT_INCOME_TOTAL,
    AMT_CREDIT,
    AMT_ANNUITY,
    AMT_GOODS_PRICE,

    -- categorical descriptors
    NAME_CONTRACT_TYPE,
    NAME_INCOME_TYPE,
    NAME_EDUCATION_TYPE,
    NAME_FAMILY_STATUS,
    NAME_HOUSING_TYPE,
    OCCUPATION_TYPE,
    ORGANIZATION_TYPE,

    -- time deltas
    DAYS_BIRTH,
    DAYS_EMPLOYED,

    -- flags
    FLAG_MOBIL,
    FLAG_EMP_PHONE,
    FLAG_WORK_PHONE,
    FLAG_PHONE,
    FLAG_EMAIL,
    FLAG_OWN_CAR,
    FLAG_OWN_REALTY,

    -- additional numeric
    OWN_CAR_AGE,

    -- document flags
    FLAG_DOCUMENT_2,
    FLAG_DOCUMENT_3,
    FLAG_DOCUMENT_4,
    FLAG_DOCUMENT_5,
    FLAG_DOCUMENT_6,
    FLAG_DOCUMENT_7,
    FLAG_DOCUMENT_8,
    FLAG_DOCUMENT_9,
    FLAG_DOCUMENT_10,
    FLAG_DOCUMENT_11,
    FLAG_DOCUMENT_12,
    FLAG_DOCUMENT_13,
    FLAG_DOCUMENT_14,
    FLAG_DOCUMENT_15,
    FLAG_DOCUMENT_16,
    FLAG_DOCUMENT_17,
    FLAG_DOCUMENT_18,
    FLAG_DOCUMENT_19,
    FLAG_DOCUMENT_20,
    FLAG_DOCUMENT_21
FROM {{ source('application_dwh', 'application_train') }}
WHERE SK_ID_CURR IS NOT NULL
