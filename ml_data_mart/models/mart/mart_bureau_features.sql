{{
  config(
    materialized='table',
    description='Bureau and bureau_balance risk features aggregated at SK_ID_CURR level'
  )
}}

WITH bureau_base AS (
    SELECT
        SK_ID_CURR,
        SK_ID_BUREAU,
        CREDIT_TYPE,
        CREDIT_ACTIVE,
        CAST(CREDIT_DAY_OVERDUE, 'Nullable(Int64)') AS CREDIT_DAY_OVERDUE,
        CAST(AMT_CREDIT_SUM_OVERDUE, 'Nullable(Float64)') AS AMT_CREDIT_SUM_OVERDUE,
        CAST(AMT_CREDIT_MAX_OVERDUE, 'Nullable(Float64)') AS AMT_CREDIT_MAX_OVERDUE,
        CAST(CNT_CREDIT_PROLONG, 'Nullable(Int64)') AS CNT_CREDIT_PROLONG,
        CAST(AMT_CREDIT_SUM_DEBT, 'Nullable(Float64)') AS AMT_CREDIT_SUM_DEBT,
        CAST(AMT_CREDIT_SUM_LIMIT, 'Nullable(Float64)') AS AMT_CREDIT_SUM_LIMIT,
        CAST(AMT_CREDIT_SUM, 'Nullable(Float64)') AS AMT_CREDIT_SUM
    FROM {{ source('application_dwh', 'bureau') }}
),
bureau_risk AS (
    SELECT
        SK_ID_CURR,
        /* Basic counts and diversity */
        count() AS BUREAU_TOTAL_COUNT,
        uniq(CREDIT_TYPE) AS BUREAU_CREDIT_TYPES_COUNT,

        /* Credit status counts */
        countIf(CREDIT_ACTIVE = 'Active') AS BUREAU_ACTIVE_COUNT,
        countIf(CREDIT_ACTIVE = 'Closed') AS BUREAU_CLOSED_COUNT,
        countIf(CREDIT_ACTIVE = 'Bad debt') AS BUREAU_BAD_DEBT_COUNT,
        countIf(CREDIT_ACTIVE = 'Sold') AS BUREAU_SOLD_COUNT,

        /* High-risk status ratios */
        countIf(CREDIT_ACTIVE = 'Bad debt') / nullIf(toFloat64(count()), 0) AS BUREAU_BAD_DEBT_RATIO,
        countIf(CREDIT_ACTIVE = 'Sold') / nullIf(toFloat64(count()), 0) AS BUREAU_SOLD_RATIO,
        (countIf(CREDIT_ACTIVE = 'Bad debt') + countIf(CREDIT_ACTIVE = 'Sold')) / nullIf(toFloat64(count()), 0) AS BUREAU_HIGH_RISK_RATIO,

        /* Overdue risk indicators */
        sum(CREDIT_DAY_OVERDUE) AS BUREAU_OVERDUE_DAYS_TOTAL,
        avg(CREDIT_DAY_OVERDUE) AS BUREAU_OVERDUE_DAYS_MEAN,
        max(CREDIT_DAY_OVERDUE) AS BUREAU_OVERDUE_DAYS_MAX,
        countIf(CREDIT_DAY_OVERDUE > 0) AS BUREAU_OVERDUE_COUNT,
        countIf(CREDIT_DAY_OVERDUE > 0) / nullIf(toFloat64(count()), 0) AS BUREAU_OVERDUE_RATIO,

        /* Amount-based overdue risk */
        sum(AMT_CREDIT_SUM_OVERDUE) AS BUREAU_AMT_OVERDUE_TOTAL,
        avg(AMT_CREDIT_SUM_OVERDUE) AS BUREAU_AMT_OVERDUE_MEAN,
        max(AMT_CREDIT_SUM_OVERDUE) AS BUREAU_AMT_OVERDUE_MAX,
        max(AMT_CREDIT_MAX_OVERDUE) AS BUREAU_AMT_MAX_OVERDUE_EVER,
        countIf(AMT_CREDIT_SUM_OVERDUE > 0) AS BUREAU_AMT_OVERDUE_COUNT,
        countIf(AMT_CREDIT_SUM_OVERDUE > 0) / nullIf(toFloat64(count()), 0) AS BUREAU_AMT_OVERDUE_RATIO,

        /* Credit prolongation risk */
        sum(CNT_CREDIT_PROLONG) AS BUREAU_PROLONG_TOTAL,
        avg(CNT_CREDIT_PROLONG) AS BUREAU_PROLONG_MEAN,
        max(CNT_CREDIT_PROLONG) AS BUREAU_PROLONG_MAX,
        countIf(CNT_CREDIT_PROLONG > 0) AS BUREAU_PROLONG_COUNT,
        countIf(CNT_CREDIT_PROLONG > 0) / nullIf(toFloat64(count()), 0) AS BUREAU_PROLONG_RATIO
    FROM bureau_base
    GROUP BY SK_ID_CURR
),
bureau_adv AS (
    SELECT
        SK_ID_CURR,
        /* Utilization and financial stress */
        sum(AMT_CREDIT_SUM_DEBT) / nullIf(sum(AMT_CREDIT_SUM_LIMIT), 0) AS BUREAU_CREDIT_UTILIZATION_RATIO,
        sum(AMT_CREDIT_SUM_DEBT) / nullIf(sum(AMT_CREDIT_SUM), 0) AS BUREAU_DEBT_TO_CREDIT_RATIO,
        sum(AMT_CREDIT_SUM_OVERDUE) / nullIf(sum(AMT_CREDIT_SUM), 0) AS BUREAU_OVERDUE_TO_CREDIT_RATIO,

        /* Active portfolio */
        sumIf(AMT_CREDIT_SUM, CREDIT_ACTIVE = 'Active') AS BUREAU_ACTIVE_CREDIT_SUM,
        sumIf(AMT_CREDIT_SUM_DEBT, CREDIT_ACTIVE = 'Active') AS BUREAU_ACTIVE_DEBT_SUM,
        sumIf(AMT_CREDIT_SUM_OVERDUE, CREDIT_ACTIVE = 'Active') AS BUREAU_ACTIVE_OVERDUE_SUM,
        sumIf(AMT_CREDIT_SUM_DEBT, CREDIT_ACTIVE = 'Active') / nullIf(sumIf(AMT_CREDIT_SUM_LIMIT, CREDIT_ACTIVE = 'Active'), 0) AS BUREAU_ACTIVE_UTILIZATION_RATIO,

        /* Maxed out / High utilization */
        countIf(AMT_CREDIT_SUM_DEBT >= AMT_CREDIT_SUM_LIMIT) AS BUREAU_MAXED_OUT_COUNT,
        countIf(AMT_CREDIT_SUM_DEBT >= AMT_CREDIT_SUM_LIMIT) / nullIf(toFloat64(count()), 0) AS BUREAU_MAXED_OUT_RATIO,
        countIf(AMT_CREDIT_SUM_DEBT > AMT_CREDIT_SUM_LIMIT * 0.8) AS BUREAU_HIGH_UTIL_COUNT,
        countIf(AMT_CREDIT_SUM_DEBT > AMT_CREDIT_SUM_LIMIT * 0.8) / nullIf(toFloat64(count()), 0) AS BUREAU_HIGH_UTIL_RATIO
    FROM bureau_base
    GROUP BY SK_ID_CURR
),
bb_base AS (
    SELECT
        SK_ID_BUREAU,
        CAST(MONTHS_BALANCE, 'Nullable(Int32)') AS MONTHS_BALANCE,
        STATUS
    FROM {{ source('application_dwh', 'bureau_balance') }}
),
bb_agg AS (
    SELECT
        SK_ID_BUREAU,
        count() AS TOTAL_MONTHS_OBSERVED,
        countIf(STATUS = '0') AS MONTHS_ON_TIME,
        countIf(STATUS = 'C') AS MONTHS_CLOSED,
        countIf(STATUS = 'X') AS MONTHS_UNKNOWN,
        countIf(STATUS = '1') AS MONTHS_DPD_1_30,
        countIf(STATUS = '2') AS MONTHS_DPD_31_60,
        countIf(STATUS = '3') AS MONTHS_DPD_61_90,
        countIf(STATUS = '4') AS MONTHS_DPD_91_120,
        countIf(STATUS = '5') AS MONTHS_DPD_120_PLUS,
        min(MONTHS_BALANCE) AS EARLIEST_MONTH,
        max(MONTHS_BALANCE) AS LATEST_MONTH,
        /* Derived per-bureau ratios and flags */
        (countIf(STATUS = '1') + countIf(STATUS = '2') + countIf(STATUS = '3') + countIf(STATUS = '4') + countIf(STATUS = '5')) AS TOTAL_DPD_MONTHS,
        (countIf(STATUS = '1') + countIf(STATUS = '2') + countIf(STATUS = '3') + countIf(STATUS = '4') + countIf(STATUS = '5')) / nullIf(toFloat64(count()), 0) AS DPD_RATIO,
        countIf(STATUS = '5') / nullIf(toFloat64(count()), 0) AS SEVERE_DPD_RATIO,
        toInt8(countIf(STATUS = '5') > 0) AS HAS_SEVERE_DPD,
        toInt8((countIf(STATUS = '1') + countIf(STATUS = '2') + countIf(STATUS = '3') + countIf(STATUS = '4') + countIf(STATUS = '5')) > 0) AS HAS_ANY_DPD,
        MONTHS_ON_TIME / nullIf(toFloat64(count()), 0) AS ON_TIME_RATIO,
        MONTHS_UNKNOWN / nullIf(toFloat64(count()), 0) AS UNKNOWN_RATIO
    FROM bb_base
    GROUP BY SK_ID_BUREAU
),
bb_joined AS (
    SELECT
        b.SK_ID_CURR,
        b.SK_ID_BUREAU,
        a.* EXCEPT (SK_ID_BUREAU)
    FROM bureau_base b
    LEFT JOIN bb_agg a USING (SK_ID_BUREAU)
),
bb_client AS (
    SELECT
        SK_ID_CURR,
        count(SK_ID_BUREAU) AS BUREAU_WITH_BALANCE_COUNT,
        sum(TOTAL_MONTHS_OBSERVED) AS TOTAL_MONTHS_ALL_BUREAUS,
        sum(MONTHS_ON_TIME) AS TOTAL_MONTHS_ON_TIME,
        sum(TOTAL_DPD_MONTHS) AS TOTAL_DPD_ALL_BUREAUS,
        sum(MONTHS_DPD_120_PLUS) AS TOTAL_SEVERE_DPD_MONTHS,
        max(DPD_RATIO) AS WORST_DPD_RATIO,
        max(SEVERE_DPD_RATIO) AS WORST_SEVERE_DPD_RATIO,
        min(ON_TIME_RATIO) AS WORST_ON_TIME_RATIO,
        avg(DPD_RATIO) AS AVG_DPD_RATIO,
        avg(ON_TIME_RATIO) AS AVG_ON_TIME_RATIO,
        sum(HAS_SEVERE_DPD) AS COUNT_BUREAUS_WITH_SEVERE_DPD,
        sum(HAS_ANY_DPD) AS COUNT_BUREAUS_WITH_ANY_DPD
    FROM bb_joined
    GROUP BY SK_ID_CURR
),
bb_client_final AS (
    SELECT
        SK_ID_CURR,
        BUREAU_WITH_BALANCE_COUNT,
        TOTAL_MONTHS_ALL_BUREAUS,
        TOTAL_MONTHS_ON_TIME,
        TOTAL_DPD_ALL_BUREAUS,
        TOTAL_SEVERE_DPD_MONTHS,
        WORST_DPD_RATIO,
        WORST_SEVERE_DPD_RATIO,
        WORST_ON_TIME_RATIO,
        AVG_DPD_RATIO,
        AVG_ON_TIME_RATIO,
        COUNT_BUREAUS_WITH_SEVERE_DPD,
        COUNT_BUREAUS_WITH_ANY_DPD,
        /* Final client-level ratios and flags */
        TOTAL_MONTHS_ON_TIME / nullIf(toFloat64(TOTAL_MONTHS_ALL_BUREAUS), 0) AS OVERALL_ON_TIME_RATIO,
        TOTAL_DPD_ALL_BUREAUS / nullIf(toFloat64(TOTAL_MONTHS_ALL_BUREAUS), 0) AS OVERALL_DPD_RATIO,
        TOTAL_SEVERE_DPD_MONTHS / nullIf(toFloat64(TOTAL_MONTHS_ALL_BUREAUS), 0) AS OVERALL_SEVERE_DPD_RATIO,
        toInt8(COUNT_BUREAUS_WITH_SEVERE_DPD > 0) AS CLIENT_HAS_SEVERE_DPD_HISTORY,
        toInt8(COUNT_BUREAUS_WITH_ANY_DPD > 0) AS CLIENT_HAS_ANY_DPD_HISTORY
    FROM bb_client
)
SELECT
    r.SK_ID_CURR,
    r.* EXCEPT (SK_ID_CURR),
    a.* EXCEPT (SK_ID_CURR),
    c.* EXCEPT (SK_ID_CURR)
FROM bureau_risk r
LEFT JOIN bureau_adv a USING (SK_ID_CURR)
LEFT JOIN bb_client_final c USING (SK_ID_CURR)

