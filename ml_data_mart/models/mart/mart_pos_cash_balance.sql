{{
  config(
    materialized='table',
    description='POS cash balance features aggregated to customer (SK_ID_CURR) level via loan-level step'
  )
}}

WITH base AS (
    SELECT *
    FROM {{ source('application_dwh', 'pos_cash_balance') }}
),
/* Step 1: Loan-level aggregation (SK_ID_PREV, SK_ID_CURR) */
basic_agg AS (
    SELECT
        SK_ID_PREV,
        SK_ID_CURR,
        count() AS TOTAL_MONTHS_OBSERVED,

        /* DPD stats */
        max(SK_DPD) AS MAX_DPD,
        avg(SK_DPD) AS MEAN_DPD,
        max(SK_DPD_DEF) AS MAX_DPD_DEF,

        /* Installment stats */
        max(CNT_INSTALMENT) AS MAX_CNT_INSTALMENT,
        min(CNT_INSTALMENT_FUTURE) AS MIN_CNT_INSTALMENT_FUTURE,

        /* Time range */
        min(MONTHS_BALANCE) AS EARLIEST_MONTH,
        max(MONTHS_BALANCE) AS LATEST_MONTH
    FROM base
    GROUP BY SK_ID_PREV, SK_ID_CURR
),
counts_by_prev AS (
    SELECT
        SK_ID_PREV,
        /* DPD counts */
        countIf(SK_DPD > 0) AS MONTHS_DPD_POSITIVE,
        countIf(SK_DPD > 7) AS MONTHS_DPD_7PLUS,
        countIf(SK_DPD > 30) AS MONTHS_DPD_30PLUS,

        /* Status counts */
        countIf(NAME_CONTRACT_STATUS = 'Active') AS MONTHS_ACTIVE,
        countIf(NAME_CONTRACT_STATUS = 'Completed') AS MONTHS_COMPLETED,
        countIf(NAME_CONTRACT_STATUS = 'Demand') AS MONTHS_DEMAND
    FROM base
    GROUP BY SK_ID_PREV
),
loan_features AS (
    SELECT
        b.SK_ID_PREV,
        b.SK_ID_CURR,
        b.TOTAL_MONTHS_OBSERVED,
        b.MAX_DPD,
        b.MEAN_DPD,
        b.MAX_DPD_DEF,
        b.MAX_CNT_INSTALMENT,
        b.MIN_CNT_INSTALMENT_FUTURE,
        b.EARLIEST_MONTH,
        b.LATEST_MONTH,

        /* fill missing counts with 0 */
        coalesce(c.MONTHS_DPD_POSITIVE, 0) AS MONTHS_DPD_POSITIVE,
        coalesce(c.MONTHS_DPD_7PLUS, 0) AS MONTHS_DPD_7PLUS,
        coalesce(c.MONTHS_DPD_30PLUS, 0) AS MONTHS_DPD_30PLUS,
        coalesce(c.MONTHS_ACTIVE, 0) AS MONTHS_ACTIVE,
        coalesce(c.MONTHS_COMPLETED, 0) AS MONTHS_COMPLETED,
        coalesce(c.MONTHS_DEMAND, 0) AS MONTHS_DEMAND,

        /* Derived ratios at loan level */
        if(b.MAX_CNT_INSTALMENT > 0,
           1.0 - (b.MIN_CNT_INSTALMENT_FUTURE / nullIf(b.MAX_CNT_INSTALMENT, 0)),
           0.0) AS REPAYMENT_PROGRESS_RATIO,

        MONTHS_DPD_POSITIVE / nullIf(toFloat64(b.TOTAL_MONTHS_OBSERVED), 0) AS DPD_RATE,
        MONTHS_DPD_7PLUS / nullIf(toFloat64(b.TOTAL_MONTHS_OBSERVED), 0) AS DPD_7PLUS_RATE,
        MONTHS_DPD_30PLUS / nullIf(toFloat64(b.TOTAL_MONTHS_OBSERVED), 0) AS DPD_30PLUS_RATE,

        coalesce(c.MONTHS_ACTIVE, 0) / nullIf(toFloat64(b.TOTAL_MONTHS_OBSERVED), 0) AS ACTIVE_RATE,
        coalesce(c.MONTHS_COMPLETED, 0) / nullIf(toFloat64(b.TOTAL_MONTHS_OBSERVED), 0) AS COMPLETED_RATE,
        coalesce(c.MONTHS_DEMAND, 0) / nullIf(toFloat64(b.TOTAL_MONTHS_OBSERVED), 0) AS DEMAND_RATE,

        toInt8(coalesce(c.MONTHS_DEMAND, 0) > 0) AS EVER_DEMAND,
        toInt8(b.MAX_DPD > 30) AS SEVERE_DPD_FLAG,
        toInt8(coalesce(c.MONTHS_DEMAND, 0) > 0) AS IS_PROBLEM_LOAN
    FROM basic_agg b
    LEFT JOIN counts_by_prev c USING (SK_ID_PREV)
),
/* Step 2: Customer-level aggregation (SK_ID_CURR) */
customer_agg AS (
    SELECT
        SK_ID_CURR,

        /* Basic loan counts */
        count() AS POS_COUNT_LOANS_TOTAL,
        sum(IS_PROBLEM_LOAN) AS POS_COUNT_PROBLEM_LOANS,
        sum(EVER_DEMAND) AS POS_COUNT_LOANS_DEMAND,

        /* DPD statistics across loans */
        avg(MAX_DPD) AS POS_MEAN_MAX_DPD,
        max(MAX_DPD) AS POS_MAX_MAX_DPD,
        min(MAX_DPD) AS POS_MIN_MAX_DPD,

        avg(MEAN_DPD) AS POS_MEAN_MEAN_DPD,
        avg(DPD_RATE) AS POS_MEAN_DPD_RATE,
        max(DPD_RATE) AS POS_MAX_DPD_RATE,

        /* Severe DPD */
        avg(DPD_7PLUS_RATE) AS POS_MEAN_DPD_7PLUS_RATE,
        max(DPD_7PLUS_RATE) AS POS_MAX_DPD_7PLUS_RATE,
        avg(DPD_30PLUS_RATE) AS POS_MEAN_DPD_30PLUS_RATE,
        max(DPD_30PLUS_RATE) AS POS_MAX_DPD_30PLUS_RATE,

        /* Repayment stats */
        avg(REPAYMENT_PROGRESS_RATIO) AS POS_MEAN_REPAYMENT_PROGRESS,
        max(REPAYMENT_PROGRESS_RATIO) AS POS_MAX_REPAYMENT_PROGRESS,
        min(REPAYMENT_PROGRESS_RATIO) AS POS_MIN_REPAYMENT_PROGRESS,

        /* Contract length */
        avg(MAX_CNT_INSTALMENT) AS POS_MEAN_CONTRACT_LENGTH,
        max(MAX_CNT_INSTALMENT) AS POS_MAX_CONTRACT_LENGTH,
        min(MAX_CNT_INSTALMENT) AS POS_MIN_CONTRACT_LENGTH,

        /* Status rate averages */
        avg(COMPLETED_RATE) AS POS_MEAN_COMPLETED_RATE,
        avg(ACTIVE_RATE) AS POS_MEAN_ACTIVE_RATE,
        avg(DEMAND_RATE) AS POS_MEAN_DEMAND_RATE,

        /* High risk flags */
        toInt8(max(EVER_DEMAND)) AS POS_FLAG_ANY_DEMAND,
        toInt8(max(SEVERE_DPD_FLAG)) AS POS_FLAG_ANY_SEVERE_DPD,

        /* Time range across loans */
        sum(TOTAL_MONTHS_OBSERVED) AS POS_TOTAL_MONTHS_OBSERVED,
        min(EARLIEST_MONTH) AS POS_EARLIEST_MONTH,
        max(LATEST_MONTH) AS POS_LATEST_MONTH
    FROM loan_features
    GROUP BY SK_ID_CURR
)
SELECT
    ca.*,
    /* Ratios and segments */
    POS_COUNT_PROBLEM_LOANS / nullIf(toFloat64(POS_COUNT_LOANS_TOTAL), 0) AS POS_RATIO_PROBLEM_LOANS,
    POS_COUNT_LOANS_DEMAND / nullIf(toFloat64(POS_COUNT_LOANS_TOTAL), 0) AS POS_RATIO_LOANS_DEMAND,
    (POS_LATEST_MONTH - POS_EARLIEST_MONTH) AS POS_OBSERVATION_SPAN_MONTHS,
    multiIf(
        POS_MAX_MAX_DPD > 90, 'HIGH_RISK',
        (POS_FLAG_ANY_DEMAND = 1) OR (POS_MAX_MAX_DPD > 30), 'MEDIUM_RISK',
        POS_MEAN_DPD_RATE > 0.05, 'LOW_MEDIUM_RISK',
        'LOW_RISK'
    ) AS POS_RISK_SEGMENT
FROM customer_agg ca
