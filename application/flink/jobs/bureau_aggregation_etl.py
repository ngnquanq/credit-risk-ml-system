#!/usr/bin/env python3
"""
PyFlink Job: Bureau Data Aggregation

Consumes raw bureau data from hc.application_ext_raw and produces
aggregated features to hc.application_ext.

This job replaces the Python-based aggregation in external_bureau_service.py
with distributed parallel processing using Apache Flink.

Architecture:
- Source: hc.application_ext_raw (JSON messages with bureau + bureau_balance arrays)
- Processing: PyFlink UDF applies aggregation logic (60+ features)
- Sink: hc.application_ext (upsert-kafka for stateful updates)
"""

import os
from pyflink.table import EnvironmentSettings, TableEnvironment
from bureau_aggregation_udfs import aggregate_bureau_features


def main():
    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    source_topic = os.getenv("RAW_TOPIC_EXT", "hc.application_ext_raw")
    sink_topic = os.getenv("SINK_TOPIC_EXT", "hc.application_ext")

    env_settings = EnvironmentSettings.in_streaming_mode()
    t_env = TableEnvironment.create(env_settings)

    # Configure Kafka connector jars
    cfg = t_env.get_config().get_configuration()
    jars = []
    kafka_jar = os.getenv("FLINK_SQL_CONNECTOR_KAFKA_JAR")
    if kafka_jar:
        jars.append(f"file://{kafka_jar}")
    formats_jar = os.getenv("FLINK_FORMATS_JAR")
    if formats_jar:
        jars.append(f"file://{formats_jar}")
    if jars:
        cfg.set_string("pipeline.jars", ";".join(jars))

    # Register aggregation UDF
    t_env.create_temporary_function("aggregate_bureau_features", aggregate_bureau_features)

    # Clean re-definitions
    t_env.execute_sql("DROP TABLE IF EXISTS external_raw")
    t_env.execute_sql("DROP TABLE IF EXISTS external_features")

    # Source: Raw bureau data from hc.application_ext_raw
    t_env.execute_sql(
        f"""
        CREATE TABLE external_raw (
            raw_data STRING  -- Full JSON message as string for UDF processing
        ) WITH (
            'connector' = 'kafka',
            'topic' = '{source_topic}',
            'properties.bootstrap.servers' = '{bootstrap}',
            'properties.group.id' = 'flink-bureau-aggregation',
            'scan.startup.mode' = 'earliest-offset',
            'format' = 'raw',
            'raw.charset' = 'UTF-8'
        )
        """
    )

    # Sink: Aggregated features to hc.application_ext
    # Use upsert-kafka to support updates (keyed by sk_id_curr)
    t_env.execute_sql(
        f"""
        CREATE TABLE external_features (
            sk_id_curr STRING,
            ext_source_1 DOUBLE,
            ext_source_2 DOUBLE,
            ext_source_3 DOUBLE,
            BUREAU_TOTAL_COUNT INT,
            BUREAU_CREDIT_TYPES_COUNT INT,
            BUREAU_ACTIVE_COUNT INT,
            BUREAU_CLOSED_COUNT INT,
            BUREAU_BAD_DEBT_COUNT INT,
            BUREAU_SOLD_COUNT INT,
            BUREAU_BAD_DEBT_RATIO DOUBLE,
            BUREAU_SOLD_RATIO DOUBLE,
            BUREAU_HIGH_RISK_RATIO DOUBLE,
            BUREAU_OVERDUE_DAYS_TOTAL INT,
            BUREAU_OVERDUE_DAYS_MEAN DOUBLE,
            BUREAU_OVERDUE_DAYS_MAX INT,
            BUREAU_OVERDUE_COUNT INT,
            BUREAU_OVERDUE_RATIO DOUBLE,
            BUREAU_AMT_OVERDUE_TOTAL DOUBLE,
            BUREAU_AMT_OVERDUE_MEAN DOUBLE,
            BUREAU_AMT_OVERDUE_MAX DOUBLE,
            BUREAU_AMT_MAX_OVERDUE_EVER DOUBLE,
            BUREAU_AMT_OVERDUE_COUNT INT,
            BUREAU_AMT_OVERDUE_RATIO DOUBLE,
            BUREAU_PROLONG_TOTAL INT,
            BUREAU_PROLONG_MEAN DOUBLE,
            BUREAU_PROLONG_MAX INT,
            BUREAU_PROLONG_COUNT INT,
            BUREAU_PROLONG_RATIO DOUBLE,
            BUREAU_CREDIT_UTILIZATION_RATIO DOUBLE,
            BUREAU_DEBT_TO_CREDIT_RATIO DOUBLE,
            BUREAU_OVERDUE_TO_CREDIT_RATIO DOUBLE,
            BUREAU_ACTIVE_CREDIT_SUM DOUBLE,
            BUREAU_ACTIVE_DEBT_SUM DOUBLE,
            BUREAU_ACTIVE_OVERDUE_SUM DOUBLE,
            BUREAU_ACTIVE_UTILIZATION_RATIO DOUBLE,
            BUREAU_MAXED_OUT_COUNT INT,
            BUREAU_MAXED_OUT_RATIO DOUBLE,
            BUREAU_HIGH_UTIL_COUNT INT,
            BUREAU_HIGH_UTIL_RATIO DOUBLE,
            BUREAU_WITH_BALANCE_COUNT INT,
            TOTAL_MONTHS_ALL_BUREAUS INT,
            TOTAL_MONTHS_ON_TIME INT,
            TOTAL_DPD_ALL_BUREAUS INT,
            TOTAL_SEVERE_DPD_MONTHS INT,
            WORST_DPD_RATIO DOUBLE,
            WORST_SEVERE_DPD_RATIO DOUBLE,
            WORST_ON_TIME_RATIO DOUBLE,
            AVG_DPD_RATIO DOUBLE,
            AVG_ON_TIME_RATIO DOUBLE,
            COUNT_BUREAUS_WITH_SEVERE_DPD INT,
            COUNT_BUREAUS_WITH_ANY_DPD INT,
            OVERALL_ON_TIME_RATIO DOUBLE,
            OVERALL_DPD_RATIO DOUBLE,
            OVERALL_SEVERE_DPD_RATIO DOUBLE,
            CLIENT_HAS_SEVERE_DPD_HISTORY INT,
            CLIENT_HAS_ANY_DPD_HISTORY INT,
            ts DOUBLE,
            PRIMARY KEY (sk_id_curr) NOT ENFORCED
        ) WITH (
            'connector' = 'upsert-kafka',
            'topic' = '{sink_topic}',
            'properties.bootstrap.servers' = '{bootstrap}',
            'key.format' = 'raw',
            'key.raw.charset' = 'UTF-8',
            'value.format' = 'json'
        )
        """
    )

    # Processing: Apply aggregation UDF
    # The UDF receives the full raw JSON message and returns aggregated features as JSON
    t_env.execute_sql(
        """
        INSERT INTO external_features
        SELECT
            sk_id_curr,
            CAST(JSON_VALUE(aggregated, '$.ext_source_1') AS DOUBLE) as ext_source_1,
            CAST(JSON_VALUE(aggregated, '$.ext_source_2') AS DOUBLE) as ext_source_2,
            CAST(JSON_VALUE(aggregated, '$.ext_source_3') AS DOUBLE) as ext_source_3,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_TOTAL_COUNT') AS INT) as BUREAU_TOTAL_COUNT,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_CREDIT_TYPES_COUNT') AS INT) as BUREAU_CREDIT_TYPES_COUNT,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_ACTIVE_COUNT') AS INT) as BUREAU_ACTIVE_COUNT,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_CLOSED_COUNT') AS INT) as BUREAU_CLOSED_COUNT,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_BAD_DEBT_COUNT') AS INT) as BUREAU_BAD_DEBT_COUNT,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_SOLD_COUNT') AS INT) as BUREAU_SOLD_COUNT,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_BAD_DEBT_RATIO') AS DOUBLE) as BUREAU_BAD_DEBT_RATIO,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_SOLD_RATIO') AS DOUBLE) as BUREAU_SOLD_RATIO,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_HIGH_RISK_RATIO') AS DOUBLE) as BUREAU_HIGH_RISK_RATIO,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_OVERDUE_DAYS_TOTAL') AS INT) as BUREAU_OVERDUE_DAYS_TOTAL,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_OVERDUE_DAYS_MEAN') AS DOUBLE) as BUREAU_OVERDUE_DAYS_MEAN,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_OVERDUE_DAYS_MAX') AS INT) as BUREAU_OVERDUE_DAYS_MAX,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_OVERDUE_COUNT') AS INT) as BUREAU_OVERDUE_COUNT,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_OVERDUE_RATIO') AS DOUBLE) as BUREAU_OVERDUE_RATIO,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_AMT_OVERDUE_TOTAL') AS DOUBLE) as BUREAU_AMT_OVERDUE_TOTAL,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_AMT_OVERDUE_MEAN') AS DOUBLE) as BUREAU_AMT_OVERDUE_MEAN,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_AMT_OVERDUE_MAX') AS DOUBLE) as BUREAU_AMT_OVERDUE_MAX,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_AMT_MAX_OVERDUE_EVER') AS DOUBLE) as BUREAU_AMT_MAX_OVERDUE_EVER,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_AMT_OVERDUE_COUNT') AS INT) as BUREAU_AMT_OVERDUE_COUNT,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_AMT_OVERDUE_RATIO') AS DOUBLE) as BUREAU_AMT_OVERDUE_RATIO,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_PROLONG_TOTAL') AS INT) as BUREAU_PROLONG_TOTAL,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_PROLONG_MEAN') AS DOUBLE) as BUREAU_PROLONG_MEAN,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_PROLONG_MAX') AS INT) as BUREAU_PROLONG_MAX,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_PROLONG_COUNT') AS INT) as BUREAU_PROLONG_COUNT,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_PROLONG_RATIO') AS DOUBLE) as BUREAU_PROLONG_RATIO,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_CREDIT_UTILIZATION_RATIO') AS DOUBLE) as BUREAU_CREDIT_UTILIZATION_RATIO,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_DEBT_TO_CREDIT_RATIO') AS DOUBLE) as BUREAU_DEBT_TO_CREDIT_RATIO,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_OVERDUE_TO_CREDIT_RATIO') AS DOUBLE) as BUREAU_OVERDUE_TO_CREDIT_RATIO,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_ACTIVE_CREDIT_SUM') AS DOUBLE) as BUREAU_ACTIVE_CREDIT_SUM,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_ACTIVE_DEBT_SUM') AS DOUBLE) as BUREAU_ACTIVE_DEBT_SUM,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_ACTIVE_OVERDUE_SUM') AS DOUBLE) as BUREAU_ACTIVE_OVERDUE_SUM,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_ACTIVE_UTILIZATION_RATIO') AS DOUBLE) as BUREAU_ACTIVE_UTILIZATION_RATIO,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_MAXED_OUT_COUNT') AS INT) as BUREAU_MAXED_OUT_COUNT,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_MAXED_OUT_RATIO') AS DOUBLE) as BUREAU_MAXED_OUT_RATIO,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_HIGH_UTIL_COUNT') AS INT) as BUREAU_HIGH_UTIL_COUNT,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_HIGH_UTIL_RATIO') AS DOUBLE) as BUREAU_HIGH_UTIL_RATIO,
            CAST(JSON_VALUE(aggregated, '$.BUREAU_WITH_BALANCE_COUNT') AS INT) as BUREAU_WITH_BALANCE_COUNT,
            CAST(JSON_VALUE(aggregated, '$.TOTAL_MONTHS_ALL_BUREAUS') AS INT) as TOTAL_MONTHS_ALL_BUREAUS,
            CAST(JSON_VALUE(aggregated, '$.TOTAL_MONTHS_ON_TIME') AS INT) as TOTAL_MONTHS_ON_TIME,
            CAST(JSON_VALUE(aggregated, '$.TOTAL_DPD_ALL_BUREAUS') AS INT) as TOTAL_DPD_ALL_BUREAUS,
            CAST(JSON_VALUE(aggregated, '$.TOTAL_SEVERE_DPD_MONTHS') AS INT) as TOTAL_SEVERE_DPD_MONTHS,
            CAST(JSON_VALUE(aggregated, '$.WORST_DPD_RATIO') AS DOUBLE) as WORST_DPD_RATIO,
            CAST(JSON_VALUE(aggregated, '$.WORST_SEVERE_DPD_RATIO') AS DOUBLE) as WORST_SEVERE_DPD_RATIO,
            CAST(JSON_VALUE(aggregated, '$.WORST_ON_TIME_RATIO') AS DOUBLE) as WORST_ON_TIME_RATIO,
            CAST(JSON_VALUE(aggregated, '$.AVG_DPD_RATIO') AS DOUBLE) as AVG_DPD_RATIO,
            CAST(JSON_VALUE(aggregated, '$.AVG_ON_TIME_RATIO') AS DOUBLE) as AVG_ON_TIME_RATIO,
            CAST(JSON_VALUE(aggregated, '$.COUNT_BUREAUS_WITH_SEVERE_DPD') AS INT) as COUNT_BUREAUS_WITH_SEVERE_DPD,
            CAST(JSON_VALUE(aggregated, '$.COUNT_BUREAUS_WITH_ANY_DPD') AS INT) as COUNT_BUREAUS_WITH_ANY_DPD,
            CAST(JSON_VALUE(aggregated, '$.OVERALL_ON_TIME_RATIO') AS DOUBLE) as OVERALL_ON_TIME_RATIO,
            CAST(JSON_VALUE(aggregated, '$.OVERALL_DPD_RATIO') AS DOUBLE) as OVERALL_DPD_RATIO,
            CAST(JSON_VALUE(aggregated, '$.OVERALL_SEVERE_DPD_RATIO') AS DOUBLE) as OVERALL_SEVERE_DPD_RATIO,
            CAST(JSON_VALUE(aggregated, '$.CLIENT_HAS_SEVERE_DPD_HISTORY') AS INT) as CLIENT_HAS_SEVERE_DPD_HISTORY,
            CAST(JSON_VALUE(aggregated, '$.CLIENT_HAS_ANY_DPD_HISTORY') AS INT) as CLIENT_HAS_ANY_DPD_HISTORY,
            CAST(JSON_VALUE(aggregated, '$.ts') AS DOUBLE) as ts
        FROM (
            SELECT
                CAST(JSON_VALUE(aggregated, '$.sk_id_curr') AS STRING) as sk_id_curr,
                aggregated
            FROM (
                SELECT aggregate_bureau_features(raw_data) as aggregated
                FROM external_raw
            )
        )
        """
    )


if __name__ == "__main__":
    main()
