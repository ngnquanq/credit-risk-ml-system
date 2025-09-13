"""BentoML service for credit risk scoring with optional Kafka consumer.

- REST endpoints for direct scoring and Feast-backed scoring by ID
- Optional Kafka consumer for streaming scoring from `hc.loan_application`
"""

from __future__ import annotations

from typing import Dict, Any, Optional, List
from datetime import datetime
import json
import threading

import bentoml
from loguru import logger
from fastapi import FastAPI
import pandas as pd

from config import settings
from schemas import ScoreRequest, ScoreResponse, ScoreByIdRequest
from model_registry import load_model
from pipeline import as_vector, postprocess
from logger import configure_logger
from feature_registry import get_model_expected_columns, get_feast_to_model_mapping, FEATURE_REGISTRY

try:
    from kafka import KafkaConsumer, KafkaProducer  # kafka-python
except Exception:  # pragma: no cover
    KafkaConsumer = None  # type: ignore
    KafkaProducer = None  # type: ignore


# Configure logging (defaults from core, overridable via SCORING_*)
configure_logger(settings.log_level, settings.log_format)


# Load model and metadata once per worker
model, MODEL_NAME, MODEL_VERSION = load_model(
    source=settings.model_source,
    path=settings.model_path,
    mlflow_uri=(settings.mlflow_model_uri or "models:/credit_risk_model/Production"),
)
# Apply explicit overrides if provided via settings (from mlflow.env)
if settings.model_name:
    MODEL_NAME = settings.model_name
if settings.model_version:
    MODEL_VERSION = settings.model_version


def _map_feast_features(feast_result: Dict[str, Any], feature_refs: List[str]) -> Dict[str, Any]:
    """Map Feast features to ML model column names using centralized registry."""
    
    # AUTO-GENERATED mapping from feature_registry.py (single source of truth)
    feature_mapping = get_feast_to_model_mapping()
    
    features = {}
    for ref in feature_refs:
        fname = ref.split(":", 1)[-1]  # Strip view prefix
        vals = feast_result.get(ref) or feast_result.get(fname)
        if vals:
            val = vals[0]
            if val is not None:
                # Map to ML model column name
                model_col = feature_mapping.get(fname, fname.upper())
                try:
                    # Keep strings as strings for categorical features
                    if isinstance(val, str):
                        features[model_col] = val
                    else:
                        features[model_col] = float(val)
                except Exception:
                    features[model_col] = val
    
    return features


def _predict_proba_local(X):
    """Return positive-class probability if available, else prediction.

    Supports sklearn estimators and MLflow pyfunc models (via params method).
    """
    # Native sklearn path
    if hasattr(model, "predict_proba"):
        try:
            proba = model.predict_proba(X)
            return proba[:, 1] if hasattr(proba, "shape") and proba.shape[-1] > 1 else proba
        except Exception:
            pass

    # MLflow pyfunc path: request predict_proba explicitly
    try:
        proba = model.predict(X, params={"method": "predict_proba"})  # type: ignore[attr-defined]
        # proba can be ndarray, list, or DataFrame
        if hasattr(proba, "values"):
            proba = proba.values
        if hasattr(proba, "shape") and proba.shape[-1] > 1:
            return proba[:, 1]
        return proba
    except Exception:
        # Fallback to default predict (may be 0/1)
        if hasattr(model, "predict"):
            return model.predict(X)
    raise RuntimeError("Model does not support prediction")


svc = bentoml.Service("credit_risk_scoring")
app = FastAPI(title="Credit Risk Scoring")

# AUTO-GENERATED MLflow model input schema from feature_registry.py (single source of truth)
EXPECTED_COLUMNS: List[str] = get_model_expected_columns()

def _as_dataframe_row(features: Dict[str, Any]) -> pd.DataFrame:
    """Return a single-row DataFrame with all expected columns present.

    Categorical fields should be strings; numeric as numbers. Missing
    columns are included with None to satisfy schema column presence.
    """
    row = {col: features.get(col, None) for col in EXPECTED_COLUMNS}
    return pd.DataFrame([row], columns=EXPECTED_COLUMNS)


def _extract_sk_id_curr_from_cdc(message: Dict[str, Any]) -> Optional[str]:
    """Extract sk_id_curr from Debezium-like envelopes.

    Supports {"payload":{"after":{...}}} and plain records.
    """
    try:
        m = message or {}
        if isinstance(m.get("payload"), dict):
            m = m["payload"]
        if isinstance(m.get("after"), dict):
            rec = m["after"]
        elif isinstance(m.get("before"), dict):
            rec = m["before"]
        else:
            rec = m
        if isinstance(rec, dict):
            if "sk_id_curr" in rec:
                return str(rec["sk_id_curr"])  # common path
            if isinstance(rec.get("value"), dict) and "sk_id_curr" in rec["value"]:
                return str(rec["value"]["sk_id_curr"])  # fallback
        return None
    except Exception:
        return None


@app.post("/healthz")
def health(_: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "model": MODEL_NAME,
        "version": MODEL_VERSION,
    }


@app.post("/v1/score")
def score(req: ScoreRequest) -> Dict[str, Any]:
    X_df = _as_dataframe_row(req.features)
    raw = _predict_proba_local(X_df)
    prob = float(raw[0]) if hasattr(raw, "__len__") else float(raw)
    probability, decision = postprocess(prob, settings.prediction_threshold)

    resp = ScoreResponse(
        probability=probability,
        decision=decision,
        threshold=settings.prediction_threshold,
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
    )
    logger.bind(event="inference").info(
        {"user_id": req.user_id, "probability": probability, "decision": decision}
    )
    return resp.model_dump()


@app.post("/v1/score-by-id")
def score_by_id(req: ScoreByIdRequest) -> Dict[str, Any]:
    if not settings.feast_enabled:
        raise bentoml.exceptions.BentoMLException(
            "Feast is disabled. Set SCORING_FEAST_ENABLED=true to enable."
        )
    try:
        from feast import FeatureStore
    except Exception as e:  # pragma: no cover
        raise bentoml.exceptions.BentoMLException(f"Feast not available: {e}")

    fs = FeatureStore(repo_path=settings.feast_repo_path)
    feature_refs = (
        [f.strip() for f in (settings.feast_feature_refs or "").split(",") if f.strip()]
    )
    if not feature_refs:
        raise bentoml.exceptions.BentoMLException("No Feast feature refs configured")

    res = fs.get_online_features(features=feature_refs, entity_rows=[{"sk_id_curr": req.sk_id_curr}]).to_dict()
    logger.info(f"Feast lookup for sk_id_curr={req.sk_id_curr}: {res}")
    
    # Validate Feast result against expected features
    validation_issues = FEATURE_REGISTRY.validate_feast_result(res)
    if validation_issues["missing_required"]:
        logger.warning(f"Missing required features: {validation_issues['missing_required']}")
    if validation_issues["unexpected_features"]:
        logger.info(f"Unexpected features received: {validation_issues['unexpected_features']}")
    
    # Check if customer data exists in Redis (data completeness check)
    has_customer_data = False
    for ref in feature_refs:
        vals = res.get(ref) or res.get(ref.split(":")[-1])
        if vals and vals[0] is not None:
            has_customer_data = True
            break
    
    if not has_customer_data and settings.require_customer_data:
        raise bentoml.exceptions.BentoMLException(
            f"No feature data found for sk_id_curr={req.sk_id_curr}. "
            f"Customer data may still be processing in the streaming pipeline or does not exist. "
            f"Set SCORING_REQUIRE_CUSTOMER_DATA=false to allow predictions with missing data."
        )
    
    # Map Feast features to ML model column names
    features = _map_feast_features(res, feature_refs)

    # Build DataFrame with all expected columns (Feast might supply a subset)
    X_df = _as_dataframe_row(features)
    raw = _predict_proba_local(X_df)
    logger.info("Model data transform: " + str(X_df.to_dict(orient="records")))
    prob = float(raw[0]) if hasattr(raw, "__len__") else float(raw)
    probability, decision = postprocess(prob, settings.prediction_threshold)

    resp = ScoreResponse(
        probability=probability,
        decision=decision,
        threshold=settings.prediction_threshold,
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
    )
    logger.bind(event="inference").info(
        {"sk_id_curr": req.sk_id_curr, "probability": probability, "decision": decision}
    )
    return resp.model_dump()


def _run_kafka_consumer():  # pragma: no cover
    if not KafkaConsumer:
        logger.warning("kafka-python not installed; skipping Kafka consumer")
        return
    try:
        consumer = KafkaConsumer(
            settings.loan_application_topic,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=settings.kafka_group_id,
            enable_auto_commit=True,
            auto_offset_reset="latest",
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            key_deserializer=lambda v: v.decode("utf-8") if v else None,
        )
        producer: Optional[KafkaProducer] = None
        if settings.scoring_output_topic:
            producer = KafkaProducer(
                bootstrap_servers=settings.kafka_bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda v: (v.encode("utf-8") if isinstance(v, str) else v),
            )

        logger.info(
            f"Kafka consumer started: topic={settings.loan_application_topic}, group={settings.kafka_group_id}"
        )
        for msg in consumer:
            try:
                payload = msg.value or {}
                # Support both plain and Debezium envelopes
                sk_id = str(payload.get("sk_id_curr") or payload.get("customer_id") or "").strip()
                if not sk_id:
                    sk_id = (_extract_sk_id_curr_from_cdc(payload) or "").strip()
                features: Dict[str, Any] | None = payload.get("features")

                # Fetch features from Feast if configured and sk_id present
                if not features and settings.feast_enabled and sk_id:
                    try:
                        from feast import FeatureStore
                        fs = FeatureStore(repo_path=settings.feast_repo_path)
                        feature_refs = [
                            f.strip() for f in (settings.feast_feature_refs or "").split(",") if f.strip()
                        ]
                        res = fs.get_online_features(features=feature_refs, entity_rows=[{"sk_id_curr": sk_id}]).to_dict()
                        logger.info(f"Kafka Feast lookup for sk_id_curr={sk_id}: {res}")
                        
                        # Check if customer data exists in Redis
                        has_customer_data = False
                        for ref in feature_refs:
                            vals = res.get(ref) or res.get(ref.split(":")[-1])
                            if vals and vals[0] is not None:
                                has_customer_data = True
                                break
                        
                        if not has_customer_data and settings.require_customer_data:
                            logger.warning(f"No feature data found for sk_id_curr={sk_id}. Skipping prediction.")
                            continue
                        
                        # Map Feast features to ML model column names (same as REST endpoint)
                        features = _map_feast_features(res, feature_refs)
                    except Exception as e:
                        logger.warning(f"Feast lookup failed for {sk_id}: {e}")

                if not features:
                    logger.debug("No features found in message; skipping")
                    continue

                # Build DataFrame with all expected columns (consistent with REST endpoint)
                X_df = _as_dataframe_row(features)
                raw = _predict_proba_local(X_df)
                logger.info("Kafka model data transform: " + str(X_df.to_dict(orient="records")))
                prob = float(raw[0]) if hasattr(raw, "__len__") else float(raw)
                probability, decision = postprocess(prob, settings.prediction_threshold)

                result = {
                    "sk_id_curr": sk_id or payload.get("sk_id_curr"),
                    "probability": probability,
                    "decision": decision,
                    "threshold": settings.prediction_threshold,
                    "model": MODEL_NAME,
                    "version": MODEL_VERSION,
                    "ts": datetime.utcnow().isoformat() + "Z",
                }
                logger.bind(event="stream_inference").info(result)
                if producer and settings.scoring_output_topic:
                    producer.send(settings.scoring_output_topic, key=sk_id or None, value=result)
            except Exception as e:
                logger.error(f"Error processing Kafka message: {e}")
    except Exception as e:
        logger.error(f"Kafka consumer failed to start: {e}")


# Optionally start Kafka consumer in background
if settings.enable_kafka:  # pragma: no cover
    threading.Thread(target=_run_kafka_consumer, daemon=True).start()


# Mount FastAPI app into Bento service
svc.mount_asgi_app(app, path="/")
