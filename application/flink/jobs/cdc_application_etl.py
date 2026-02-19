#!/usr/bin/env python3
"""
PyFlink job: consume Debezium CDC events from loan_applications and transform
into ML-ready feature vectors. Handles Debezium decimal decoding, date transformations,
and produces features to hc.application_features topic for Feast feature store.

Mirrors the transformation logic from the Python demo script but runs as a
distributed Flink streaming job for production scalability.
"""

import os
from pyflink.table import EnvironmentSettings, TableEnvironment

# Import custom UDFs for CDC data transformations
from cdc_udfs import (
    decode_decimal_base64,
    safe_parse_decimal,
    calculate_days_birth,
    calculate_days_employed,
    document_flag,
)


def main():
    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    source_topic = os.getenv(
        "CDC_SOURCE_TOPIC", "hc.applications.public.loan_applications"
    )
    sink_topic_features = os.getenv("SINK_TOPIC_FEATURES", "hc.application_features")

    env_settings = EnvironmentSettings.in_streaming_mode()
    t_env = TableEnvironment.create(env_settings)

    # Allow running as a standalone Python worker by supplying connector jars
    # via environment variables (local mini-cluster execution).
    # Set FLINK_SQL_CONNECTOR_KAFKA_JAR to the absolute path of the Kafka SQL connector jar,
    # and optionally FLINK_FORMATS_JAR for JSON/debezium formats if needed.
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

    # Register custom UDFs for CDC transformations
    t_env.create_temporary_function("decode_decimal_base64", decode_decimal_base64)
    t_env.create_temporary_function("safe_parse_decimal", safe_parse_decimal)
    t_env.create_temporary_function("calculate_days_birth", calculate_days_birth)
    t_env.create_temporary_function("calculate_days_employed", calculate_days_employed)
    t_env.create_temporary_function("document_flag", document_flag)

    # Clean re-definitions to ensure latest schema is applied when job restarts
    t_env.execute_sql("DROP TABLE IF EXISTS application_features")
    t_env.execute_sql("DROP TABLE IF EXISTS loan_applications_cdc")

    # Source: Debezium CDC JSON
    # This approach handles both direct values and encoded formats from Debezium
    t_env.execute_sql(
        f"""
        CREATE TABLE loan_applications_cdc (
            sk_id_curr STRING,
            code_gender STRING,
            birth_date STRING,  -- Handle both ISO strings and integer days
            cnt_children INT,
            -- Read amounts as STRING to be robust to Debezium JSON encodings; parse via UDF
            amt_income_total STRING,
            amt_credit STRING,
            amt_annuity STRING,
            amt_goods_price STRING,
            name_contract_type STRING,
            name_income_type STRING,
            name_education_type STRING,
            name_family_status STRING,
            name_housing_type STRING,
            employment_start_date STRING,
            occupation_type STRING,
            organization_type STRING,
            flag_mobil INT,
            flag_emp_phone INT,
            flag_work_phone INT,
            flag_phone INT,
            flag_email INT,
            flag_own_car INT,
            flag_own_realty INT,
            own_car_age INT,
            document_id_2 STRING,
            document_id_3 STRING,
            document_id_4 STRING,
            document_id_5 STRING,
            document_id_6 STRING,
            document_id_7 STRING,
            document_id_8 STRING,
            document_id_9 STRING,
            document_id_10 STRING,
            document_id_11 STRING,
            document_id_12 STRING,
            document_id_13 STRING,
            document_id_14 STRING,
            document_id_15 STRING,
            document_id_16 STRING,
            document_id_17 STRING,
            document_id_18 STRING,
            document_id_19 STRING,
            document_id_20 STRING,
            document_id_21 STRING,
            created_at TIMESTAMP(3),
            updated_at TIMESTAMP(3)
        ) WITH (
            'connector' = 'kafka',
            'topic' = '{source_topic}',
            'properties.bootstrap.servers' = '{bootstrap}',
            'properties.group.id' = 'flink-cdc-applications',
            'scan.startup.mode' = 'earliest-offset',
            'format' = 'debezium-json',
            'debezium-json.schema-include' = 'true',
            'debezium-json.ignore-parse-errors' = 'true'
        )
        """
    )

    # Sink topic: use upsert-kafka so sink supports UPDATE/DELETE change-log from Debezium source
    t_env.execute_sql(
        f"""
        CREATE TABLE application_features (
            sk_id_curr STRING,
            cnt_children INT,
            amt_income_total DOUBLE,
            amt_credit DOUBLE,
            amt_annuity DOUBLE,
            amt_goods_price DOUBLE,
            name_contract_type STRING,
            name_income_type STRING,
            name_education_type STRING,
            name_family_status STRING,
            name_housing_type STRING,
            occupation_type STRING,
            organization_type STRING,
            days_birth INT,
            days_employed INT,
            flag_mobil INT,
            flag_emp_phone INT,
            flag_work_phone INT,
            flag_phone INT,
            flag_email INT,
            flag_own_car INT,
            flag_own_realty INT,
            own_car_age INT,
            -- Computed document flags (FLAG_DOCUMENT_X for ML compatibility)
            flag_document_2 INT,
            flag_document_3 INT,
            flag_document_4 INT,
            flag_document_5 INT,
            flag_document_6 INT,
            flag_document_7 INT,
            flag_document_8 INT,
            flag_document_9 INT,
            flag_document_10 INT,
            flag_document_11 INT,
            flag_document_12 INT,
            flag_document_13 INT,
            flag_document_14 INT,
            flag_document_15 INT,
            flag_document_16 INT,
            flag_document_17 INT,
            flag_document_18 INT,
            flag_document_19 INT,
            flag_document_20 INT,
            flag_document_21 INT,
            ts DOUBLE,
            PRIMARY KEY (sk_id_curr) NOT ENFORCED
        ) WITH (
            'connector' = 'upsert-kafka',
            'topic' = '{sink_topic_features}',
            'properties.bootstrap.servers' = '{bootstrap}',
            'key.format' = 'raw',
            'key.raw.charset' = 'UTF-8',
            'value.format' = 'json'
        )
        """
    )

    # Production-grade transformation using custom UDFs for robust CDC handling
    t_env.execute_sql(
        """
        INSERT INTO application_features
        SELECT 
            -- Ensure string IDs for Feast entity keys (mirrors Python demo logic)
            COALESCE(CAST(sk_id_curr AS STRING), '') as sk_id_curr,
            cnt_children,
            -- Robustly parse DECIMALs: try numeric/string first, then base64 decode (scale 2)
            COALESCE(safe_parse_decimal(amt_income_total), decode_decimal_base64(amt_income_total, 2)) as amt_income_total,
            COALESCE(safe_parse_decimal(amt_credit),       decode_decimal_base64(amt_credit, 2))       as amt_credit,
            COALESCE(safe_parse_decimal(amt_annuity),      decode_decimal_base64(amt_annuity, 2))      as amt_annuity,
            COALESCE(safe_parse_decimal(amt_goods_price),  decode_decimal_base64(amt_goods_price, 2))  as amt_goods_price,
            name_contract_type,
            name_income_type,
            name_education_type,
            name_family_status,
            name_housing_type,
            occupation_type,
            organization_type,
            -- Use custom UDFs for sophisticated date transformations
            calculate_days_birth(birth_date, CAST(created_at AS STRING)) as days_birth,
            calculate_days_employed(employment_start_date, CAST(created_at AS STRING)) as days_employed,
            flag_mobil,
            flag_emp_phone,
            flag_work_phone,
            flag_phone,
            flag_email,
            flag_own_car,
            flag_own_realty,
            own_car_age,
            -- Use UDF for clean document flag computation
            document_flag(document_id_2) as flag_document_2,
            document_flag(document_id_3) as flag_document_3,
            document_flag(document_id_4) as flag_document_4,
            document_flag(document_id_5) as flag_document_5,
            document_flag(document_id_6) as flag_document_6,
            document_flag(document_id_7) as flag_document_7,
            document_flag(document_id_8) as flag_document_8,
            document_flag(document_id_9) as flag_document_9,
            document_flag(document_id_10) as flag_document_10,
            document_flag(document_id_11) as flag_document_11,
            document_flag(document_id_12) as flag_document_12,
            document_flag(document_id_13) as flag_document_13,
            document_flag(document_id_14) as flag_document_14,
            document_flag(document_id_15) as flag_document_15,
            document_flag(document_id_16) as flag_document_16,
            document_flag(document_id_17) as flag_document_17,
            document_flag(document_id_18) as flag_document_18,
            document_flag(document_id_19) as flag_document_19,
            document_flag(document_id_20) as flag_document_20,
            document_flag(document_id_21) as flag_document_21,
            -- Use epoch seconds for Feast numeric timestamp compatibility
            CAST(UNIX_TIMESTAMP() AS DOUBLE) as ts
        FROM loan_applications_cdc
        """
    )


if __name__ == "__main__":
    main()
