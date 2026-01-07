{{
  config(
    materialized='table',
    description='Training target table for applications (SK_ID_CURR, TARGET)'
  )
}}

SELECT
  SK_ID_CURR,
  TARGET
FROM {{ source('application_dwh', 'application_train') }}
WHERE SK_ID_CURR IS NOT NULL

