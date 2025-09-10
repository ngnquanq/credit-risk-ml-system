import os
from datetime import timedelta
from feast import Field, FeatureView
from feast.stream_feature_view import StreamFeatureView
from feast.types import Float32, Int64, String
from feast import KafkaSource, FileSource
from feast.data_format import JsonFormat

from entities import customer
from dwh_schema import infer_dwh_fields
from feast import stream_feature_view

# Environment-driven configuration (single source of truth via env)
BOOTSTRAP = os.getenv("FEAST_KAFKA_BROKERS", "localhost:9092")
TOPIC_APP_FEATURES = os.getenv("FEAST_TOPIC_APP_FEATURES", "hc.application_features")
TOPIC_EXTERNAL = os.getenv("FEAST_TOPIC_EXTERNAL", "hc.application_ext")
TOPIC_DWH = os.getenv("FEAST_TOPIC_DWH", "hc.application_dwh")
TS_APP = os.getenv("FEAST_TS_FIELD_APP", "ts")
TS_EXT = os.getenv("FEAST_TS_FIELD_EXT", "ts")
TS_DWH = os.getenv("FEAST_TS_FIELD_DWH", "ts")


def _build_json_schema(fields: list[Field], ts_field: str) -> str:
    type_map = {
        Int64: {"type": "integer"},
        Float32: {"type": "number"},
        String: {"type": "string"},
    }
    props: dict[str, dict] = {
        "sk_id_curr": {"type": "string"},
        ts_field: {"type": "number"},
    }
    for f in fields:
        # f.dtype is a Type, compare via is
        if f.dtype in type_map:
            props[f.name] = type_map[f.dtype]
        else:
            props[f.name] = {"type": "string"}
    schema = {
        "type": "object",
        "properties": props,
        "additionalProperties": True,
    }
    import json as _json
    return _json.dumps(schema)


def _kafka_source(name: str, topic: str, ts_field: str, brokers: str, fields: list[Field]) -> KafkaSource:
    """Construct a KafkaSource compatible across Feast versions.

    Tries kafka_brokers → bootstrap_servers → brokers.
    """
    schema_json = _build_json_schema(fields, ts_field)
    fmt = JsonFormat(schema_json)
    kwargs_common = dict(name=name, topic=topic, timestamp_field=ts_field, message_format=fmt)
    # Try newest API first (kafka_bootstrap_servers)
    try:
        return KafkaSource(kafka_bootstrap_servers=BOOTSTRAP, **kwargs_common)  # type: ignore[arg-type]
    except TypeError:
        pass
    # Try newer API
    try:
        return KafkaSource(kafka_brokers=BOOTSTRAP, **kwargs_common)  # type: ignore[arg-type]
    except TypeError:
        pass
    # Try older API (bootstrap_servers)
    try:
        return KafkaSource(bootstrap_servers=BOOTSTRAP, **kwargs_common)  # type: ignore[arg-type]
    except TypeError:
        pass
    # Fallback
    return KafkaSource(brokers=BOOTSTRAP, **kwargs_common)  # type: ignore[arg-type]


def _kafka_source_with_optional_batch(
    name: str,
    topic: str,
    ts_field: str,
    brokers: str,
    fields: list[Field],
    batch_source: FileSource,
) -> KafkaSource:
    """Construct a KafkaSource and attach batch_source if supported (Feast >= 0.47).

    Falls back to creating a KafkaSource without batch_source if the constructor
    does not accept it (older Feast versions).
    """
    schema_json = _build_json_schema(fields, ts_field)
    fmt = JsonFormat(schema_json)
    base_kwargs = dict(name=name, topic=topic, timestamp_field=ts_field, message_format=fmt)

    # Try with batch_source
    for broker_kw in ("kafka_bootstrap_servers", "kafka_brokers", "bootstrap_servers", "brokers"):
        try:
            kwargs = {broker_kw: BOOTSTRAP, **base_kwargs, "batch_source": batch_source}
            return KafkaSource(**kwargs)  # type: ignore[arg-type]
        except TypeError:
            continue

    # Fallback: without batch_source
    for broker_kw in ("kafka_bootstrap_servers", "kafka_brokers", "bootstrap_servers", "brokers"):
        try:
            kwargs = {broker_kw: BOOTSTRAP, **base_kwargs}
            return KafkaSource(**kwargs)  # type: ignore[arg-type]
        except TypeError:
            continue
    return KafkaSource(brokers=BOOTSTRAP, **base_kwargs)  # type: ignore[arg-type]


_app_fields = [
    # Entity + core numerics
    Field(name="sk_id_curr", dtype=String),
    Field(name="cnt_children", dtype=Int64),
    Field(name="amt_income_total", dtype=Float32),
    Field(name="amt_credit", dtype=Float32),
    Field(name="amt_annuity", dtype=Float32),
    Field(name="amt_goods_price", dtype=Float32),
    # Categoricals
    Field(name="name_contract_type", dtype=String),
    Field(name="name_income_type", dtype=String),
    Field(name="name_education_type", dtype=String),
    Field(name="name_family_status", dtype=String),
    Field(name="name_housing_type", dtype=String),
    Field(name="occupation_type", dtype=String),
    Field(name="organization_type", dtype=String),
    # Derived durations
    Field(name="days_birth", dtype=Int64),
    Field(name="days_employed", dtype=Int64),
    # Contact/ownership flags
    Field(name="flag_mobil", dtype=Int64),
    Field(name="flag_emp_phone", dtype=Int64),
    Field(name="flag_work_phone", dtype=Int64),
    Field(name="flag_phone", dtype=Int64),
    Field(name="flag_email", dtype=Int64),
    Field(name="flag_own_car", dtype=Int64),
    Field(name="flag_own_realty", dtype=Int64),
    Field(name="own_car_age", dtype=Int64),
    # Document flags 2..21
    Field(name="flag_document_2", dtype=Int64),
    Field(name="flag_document_3", dtype=Int64),
    Field(name="flag_document_4", dtype=Int64),
    Field(name="flag_document_5", dtype=Int64),
    Field(name="flag_document_6", dtype=Int64),
    Field(name="flag_document_7", dtype=Int64),
    Field(name="flag_document_8", dtype=Int64),
    Field(name="flag_document_9", dtype=Int64),
    Field(name="flag_document_10", dtype=Int64),
    Field(name="flag_document_11", dtype=Int64),
    Field(name="flag_document_12", dtype=Int64),
    Field(name="flag_document_13", dtype=Int64),
    Field(name="flag_document_14", dtype=Int64),
    Field(name="flag_document_15", dtype=Int64),
    Field(name="flag_document_16", dtype=Int64),
    Field(name="flag_document_17", dtype=Int64),
    Field(name="flag_document_18", dtype=Int64),
    Field(name="flag_document_19", dtype=Int64),
    Field(name="flag_document_20", dtype=Int64),
    Field(name="flag_document_21", dtype=Int64),
]

# Batch sources (defined early so they can be referenced by stream sources when supported)
application_batch_source = FileSource(
    name="application_batch_source",
    path="/tmp/application_features.parquet",
    timestamp_field=TS_APP,
)

external_batch_source = FileSource(
    name="external_batch_source",
    path="/tmp/external_features.parquet",
    timestamp_field=TS_EXT,
)

dwh_batch_source = FileSource(
    name="dwh_batch_source",
    path="/tmp/dwh_features.parquet",
    timestamp_field=TS_DWH,
)

application_features_source = _kafka_source_with_optional_batch(
    name="application_features_source",
    topic=TOPIC_APP_FEATURES,
    ts_field=TS_APP,
    brokers=BOOTSTRAP,
    fields=_app_fields,
    batch_source=application_batch_source,
)

_ext_fields = [
    Field(name="sk_id_curr", dtype=String),
    # External sources
    Field(name="ext_source_1", dtype=Float32),
    Field(name="ext_source_2", dtype=Float32),
    Field(name="ext_source_3", dtype=Float32),
    # Bureau-derived features (full set seen in topic)
    Field(name="BUREAU_TOTAL_COUNT", dtype=Int64),
    Field(name="BUREAU_CREDIT_TYPES_COUNT", dtype=Int64),
    Field(name="BUREAU_ACTIVE_COUNT", dtype=Int64),
    Field(name="BUREAU_CLOSED_COUNT", dtype=Int64),
    Field(name="BUREAU_BAD_DEBT_COUNT", dtype=Int64),
    Field(name="BUREAU_SOLD_COUNT", dtype=Int64),
    Field(name="BUREAU_BAD_DEBT_RATIO", dtype=Float32),
    Field(name="BUREAU_SOLD_RATIO", dtype=Float32),
    Field(name="BUREAU_HIGH_RISK_RATIO", dtype=Float32),
    Field(name="BUREAU_OVERDUE_DAYS_TOTAL", dtype=Int64),
    Field(name="BUREAU_OVERDUE_DAYS_MEAN", dtype=Float32),
    Field(name="BUREAU_OVERDUE_DAYS_MAX", dtype=Int64),
    Field(name="BUREAU_OVERDUE_COUNT", dtype=Int64),
    Field(name="BUREAU_OVERDUE_RATIO", dtype=Float32),
    Field(name="BUREAU_AMT_OVERDUE_TOTAL", dtype=Float32),
    Field(name="BUREAU_AMT_OVERDUE_MEAN", dtype=Float32),
    Field(name="BUREAU_AMT_OVERDUE_MAX", dtype=Float32),
    Field(name="BUREAU_AMT_MAX_OVERDUE_EVER", dtype=Float32),
    Field(name="BUREAU_AMT_OVERDUE_COUNT", dtype=Int64),
    Field(name="BUREAU_AMT_OVERDUE_RATIO", dtype=Float32),
    Field(name="BUREAU_PROLONG_TOTAL", dtype=Int64),
    Field(name="BUREAU_PROLONG_MEAN", dtype=Float32),
    Field(name="BUREAU_PROLONG_MAX", dtype=Int64),
    Field(name="BUREAU_PROLONG_COUNT", dtype=Int64),
    Field(name="BUREAU_PROLONG_RATIO", dtype=Float32),
    Field(name="BUREAU_CREDIT_UTILIZATION_RATIO", dtype=Float32),
    Field(name="BUREAU_DEBT_TO_CREDIT_RATIO", dtype=Float32),
    Field(name="BUREAU_OVERDUE_TO_CREDIT_RATIO", dtype=Float32),
    Field(name="BUREAU_ACTIVE_CREDIT_SUM", dtype=Float32),
    Field(name="BUREAU_ACTIVE_DEBT_SUM", dtype=Float32),
    Field(name="BUREAU_ACTIVE_OVERDUE_SUM", dtype=Float32),
    Field(name="BUREAU_ACTIVE_UTILIZATION_RATIO", dtype=Float32),
    Field(name="BUREAU_MAXED_OUT_COUNT", dtype=Int64),
    Field(name="BUREAU_MAXED_OUT_RATIO", dtype=Float32),
    Field(name="BUREAU_HIGH_UTIL_COUNT", dtype=Int64),
    Field(name="BUREAU_HIGH_UTIL_RATIO", dtype=Float32),
    Field(name="BUREAU_WITH_BALANCE_COUNT", dtype=Int64),
    Field(name="TOTAL_MONTHS_ALL_BUREAUS", dtype=Int64),
    Field(name="TOTAL_MONTHS_ON_TIME", dtype=Int64),
    Field(name="TOTAL_DPD_ALL_BUREAUS", dtype=Int64),
    Field(name="TOTAL_SEVERE_DPD_MONTHS", dtype=Int64),
    Field(name="WORST_DPD_RATIO", dtype=Float32),
    Field(name="WORST_SEVERE_DPD_RATIO", dtype=Float32),
    Field(name="WORST_ON_TIME_RATIO", dtype=Float32),
    Field(name="AVG_DPD_RATIO", dtype=Float32),
    Field(name="AVG_ON_TIME_RATIO", dtype=Float32),
    Field(name="COUNT_BUREAUS_WITH_SEVERE_DPD", dtype=Int64),
    Field(name="COUNT_BUREAUS_WITH_ANY_DPD", dtype=Int64),
    Field(name="OVERALL_ON_TIME_RATIO", dtype=Float32),
    Field(name="OVERALL_DPD_RATIO", dtype=Float32),
    Field(name="OVERALL_SEVERE_DPD_RATIO", dtype=Float32),
    Field(name="CLIENT_HAS_SEVERE_DPD_HISTORY", dtype=Int64),
    Field(name="CLIENT_HAS_ANY_DPD_HISTORY", dtype=Int64),
]

external_features_source = _kafka_source_with_optional_batch(
    name="external_features_source",
    topic=TOPIC_EXTERNAL,
    ts_field=TS_EXT,
    brokers=BOOTSTRAP,
    fields=_ext_fields,
    batch_source=external_batch_source,
)

_dwh_fields = infer_dwh_fields()

dwh_features_source = _kafka_source_with_optional_batch(
    name="dwh_features_source",
    topic=TOPIC_DWH,
    ts_field=TS_DWH,
    brokers=BOOTSTRAP,
    fields=_dwh_fields,
    batch_source=dwh_batch_source,
)

# (Batch sources already defined above)

# For Feast 0.40.1, StreamFeatureView requires both stream_source and batch_source
# We need to modify the KafkaSource to include batch_source reference
# Create StreamFeatureViews with proper batch source configuration on the SFV itself
def _make_stream_fv(name: str, schema: list[Field], stream_src, batch_src, ttl_days: int) -> StreamFeatureView:
    """Create a StreamFeatureView using source only.

    On Feast 0.47+, batch_source must be attached to the DataSource (KafkaSource),
    not passed to StreamFeatureView. We rely on the KafkaSource being built with
    a batch_source when supported. Older versions also accept source-only.
    """
    kwargs_common = dict(name=name, entities=[customer], ttl=timedelta(days=ttl_days), schema=schema, online=True)
    try:
        return StreamFeatureView(source=stream_src, **kwargs_common)  # type: ignore[arg-type]
    except TypeError:
        return StreamFeatureView(stream_source=stream_src, **kwargs_common)  # type: ignore[arg-type]


fv_application_features = _make_stream_fv(
    name="application_features",
    schema=_app_fields,
    stream_src=application_features_source,
    batch_src=application_batch_source,
    ttl_days=1,
)

fv_external = _make_stream_fv(
    name="external_features",
    schema=_ext_fields,
    stream_src=external_features_source,
    batch_src=external_batch_source,
    ttl_days=7,
)

fv_dwh = _make_stream_fv(
    name="dwh_features",
    schema=_dwh_fields,
    stream_src=dwh_features_source,
    batch_src=dwh_batch_source,
    ttl_days=7,
)

# Also create regular batch feature views for historical data access
fv_application_features_batch = FeatureView(
    name="application_features_batch",
    entities=[customer],
    ttl=timedelta(days=1),
    schema=_app_fields,
    online=True,
    source=application_batch_source)

fv_external_batch = FeatureView(
    name="external_features_batch",
    entities=[customer],
    ttl=timedelta(days=7),
    schema=_ext_fields,
    online=True,
    source=external_batch_source)

fv_dwh_batch = FeatureView(
    name="dwh_features_batch",
    entities=[customer],
    ttl=timedelta(days=7),
    schema=_dwh_fields,
    online=True,
    source=dwh_batch_source)
