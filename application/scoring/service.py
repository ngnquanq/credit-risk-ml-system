"""BentoML service for credit risk scoring with optional Kafka consumer.

- REST endpoints for direct scoring and Feast-backed scoring by ID
- Optional Kafka consumer for streaming scoring from `hc.loan_application`
"""

from __future__ import annotations

from typing import Dict, Any, Optional, List
from datetime import datetime
import json
import threading
import os
import tempfile

import bentoml

# Create service first (bentoml needs this at import time)
svc = bentoml.Service("credit_risk_scoring")

# Declare globals that will be populated inside bentoml.importing() block
app = None  # type: ignore
logger = None  # type: ignore
pd = None  # type: ignore
settings = None  # type: ignore
ScoreRequest = None  # type: ignore
ScoreResponse = None  # type: ignore
ScoreByIdRequest = None  # type: ignore
as_vector = None  # type: ignore
postprocess = None  # type: ignore
configure_logger = None  # type: ignore
KafkaConsumer = None  # type: ignore
KafkaProducer = None  # type: ignore

# Import ALL dependencies that might not be available during `bentoml build`
# These are installed after the build process reads bentofile.yaml
with bentoml.importing():
    from fastapi import FastAPI
    from loguru import logger as _logger
    import pandas as _pd
    from config import settings as _settings
    from schemas import ScoreRequest as _ScoreRequest, ScoreResponse as _ScoreResponse, ScoreByIdRequest as _ScoreByIdRequest
    from pipeline import as_vector as _as_vector, postprocess as _postprocess
    from logger import configure_logger as _configure_logger

    try:
        from kafka import KafkaConsumer as _KafkaConsumer, KafkaProducer as _KafkaProducer
        from opentelemetry import trace as _trace
        from opentelemetry.propagate import inject as _inject
        from tracing import setup_tracing as _setup_tracing, extract_or_create_trace_context as _extract_or_create
    except Exception:  # pragma: no cover
        _KafkaConsumer = None  # type: ignore
        _KafkaProducer = None  # type: ignore
        _trace = None  # type: ignore
        _inject = None  # type: ignore
        _setup_tracing = None  # type: ignore
        _extract_or_create = None  # type: ignore

    # Assign to module globals so they're accessible outside this block
    logger = _logger
    pd = _pd
    settings = _settings
    ScoreRequest = _ScoreRequest
    ScoreResponse = _ScoreResponse
    ScoreByIdRequest = _ScoreByIdRequest
    as_vector = _as_vector
    postprocess = _postprocess
    configure_logger = _configure_logger
    KafkaConsumer = _KafkaConsumer
    KafkaProducer = _KafkaProducer
    trace = _trace
    extract_or_create_trace_context = _extract_or_create
    inject = _inject
    setup_tracing = _setup_tracing

    # Initialize tracing if available
    if setup_tracing:
        tracer = setup_tracing("scoring-service", sampling_rate=0.1)
    else:
        tracer = None

    # Configure logging (defaults from core, overridable via SCORING_*)
    configure_logger(settings.log_level, settings.log_format)

    # Create FastAPI app after imports succeed
    app = FastAPI(title="Credit Risk Scoring")

    # Register all routes and events inside this block to ensure app exists
    # This must be done here because decorators execute at module import time

    @app.on_event("startup")
    def _on_startup() -> None:  # pragma: no cover
        """Ensure model and optional Kafka consumer start when server starts."""
        try:
            logger.info(
                "Initializing scoring service (kafka_enabled=%s, topic=%s, bootstrap=%s)",
                settings.enable_kafka,
                settings.loan_application_topic,
                settings.kafka_bootstrap_servers,
            )
        except Exception as e:
            logger.error(f"Error during startup initialization: {e}")
        ensure_model_loaded()

    @app.get("/healthz")
    def health(_: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "model": MODEL_NAME,
            "version": MODEL_VERSION,
        }

    @app.post("/v1/score")
    def score(req: ScoreRequest) -> Dict[str, Any]:
        ensure_model_loaded()
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
        ensure_model_loaded()
        features = _fetch_features_from_feast(req.sk_id_curr)
        result = _predict_and_create_response(features, req.sk_id_curr)

        logger.bind(event="inference").info({
            "sk_id_curr": req.sk_id_curr,
            "probability": result["probability"],
            "decision": result["decision"]
        })

        # Convert to ScoreResponse for REST API
        resp = ScoreResponse(
            probability=result["probability"],
            decision=result["decision"],
            threshold=result["threshold"],
            model_name=result["model"],
            model_version=result["version"],
        )
        return resp.model_dump()


# Defer model loading to runtime to avoid failures during `bentoml build`
# These globals are populated in the @svc.on_startup hook below.
model = None  # type: ignore[var-annotated]
MODEL_NAME: str = "unknown"
MODEL_VERSION: Optional[str] = None
MODEL_FEAST_METADATA: Optional[Dict[str, Any]] = None  # Feature selection from training


def _map_feast_features(feast_result: Dict[str, Any], feature_refs: List[str]) -> Dict[str, Any]:
    """Map Feast features to ML model column names.

    Uses feast_metadata.yaml feature_mapping if available, otherwise applies
    simple snake_case -> UPPER_CASE transformation.
    """
    # Get feature mapping from model metadata if available
    feature_mapping = {}
    if MODEL_FEAST_METADATA and MODEL_FEAST_METADATA.get("feature_mapping"):
        feature_mapping = MODEL_FEAST_METADATA["feature_mapping"]
    else:
        logger.warning("⚠️ MODEL_FEAST_METADATA or feature_mapping not available, using uppercase fallback")

    features = {}
    unmapped_refs = []

    for ref in feature_refs:
        fname = ref.split(":", 1)[-1]  # Strip view prefix
        vals = feast_result.get(ref) or feast_result.get(fname)
        if vals:
            val = vals[0]
            if val is not None:
                # Map to ML model column name (use metadata mapping or uppercase)
                # IMPORTANT: If using metadata mapping, ensure it's uppercased
                if fname in feature_mapping:
                    model_col = feature_mapping[fname].upper()
                else:
                    model_col = fname.upper()

                try:
                    # Keep strings as strings for categorical features
                    if isinstance(val, str):
                        features[model_col] = val
                    else:
                        features[model_col] = float(val)
                except Exception:
                    features[model_col] = val
        else:
            unmapped_refs.append(fname)

    if len(features) < len(feature_refs):
        logger.warning(f"⚠️ Missing {len(feature_refs) - len(features)} features: {unmapped_refs[:5]}")

    return features


def _predict_proba_local(X):
    """Return positive-class probability if available, else prediction.

    Supports sklearn estimators and MLflow pyfunc models (via params method).
    """
    if model is None:
        ensure_model_loaded()
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


# Model input schema loaded from feast_metadata.yaml (single source of truth)
# Lazy-loaded to avoid import errors during build
_EXPECTED_COLUMNS: Optional[List[str]] = None

def _get_expected_columns() -> List[str]:
    """Get expected columns from model's feast metadata.

    Uses model_signature.inputs (uppercase) for column names to match model expectations.
    Falls back to selected_features (lowercase) if model_signature is not available.
    Raises RuntimeError if metadata is missing.
    """
    global _EXPECTED_COLUMNS
    if _EXPECTED_COLUMNS is None:
        if MODEL_FEAST_METADATA:
            # Prefer uppercase model_signature.inputs to match sklearn model expectations
            if MODEL_FEAST_METADATA.get("model_signature", {}).get("inputs"):
                _EXPECTED_COLUMNS = MODEL_FEAST_METADATA["model_signature"]["inputs"]
                logger.info(f"✓ Using {len(_EXPECTED_COLUMNS)} UPPERCASE features from model_signature.inputs")
            elif MODEL_FEAST_METADATA.get("selected_features"):
                # Fallback: uppercase the selected_features
                _EXPECTED_COLUMNS = [f.upper() for f in MODEL_FEAST_METADATA["selected_features"]]
                logger.info(f"✓ Using {len(_EXPECTED_COLUMNS)} uppercased features from selected_features")
            else:
                raise RuntimeError(
                    "Model must include feast_metadata.yaml with 'model_signature.inputs' or 'selected_features' field. "
                    "This file should be generated during training and uploaded to MLflow as an artifact."
                )
        else:
            raise RuntimeError(
                "Model must include feast_metadata.yaml with 'model_signature.inputs' or 'selected_features' field. "
                "This file should be generated during training and uploaded to MLflow as an artifact."
            )
    return _EXPECTED_COLUMNS

def _fetch_features_from_feast(sk_id_curr: str) -> Dict[str, Any]:
    """Fetch features from Feast online store for a given customer ID.

    Returns mapped features ready for prediction.
    Raises BentoMLException if features not found.
    """
    if not settings.feast_enabled:
        raise bentoml.exceptions.BentoMLException("Feast is disabled")

    from feast import FeatureStore
    fs = FeatureStore(repo_path=_resolve_feast_repo_path())
    feature_refs = [f.strip() for f in (settings.feast_feature_refs or "").split(",") if f.strip()]

    if not feature_refs:
        raise bentoml.exceptions.BentoMLException("No Feast feature refs configured")

    res = fs.get_online_features(features=feature_refs, entity_rows=[{"sk_id_curr": sk_id_curr}]).to_dict()

    # Check if customer data exists
    has_customer_data = any(
        (res.get(ref) or res.get(ref.split(":")[-1], [None]))[0] is not None
        for ref in feature_refs
    )

    if not has_customer_data and settings.require_customer_data:
        raise bentoml.exceptions.BentoMLException(
            f"No feature data found for sk_id_curr={sk_id_curr}"
        )

    return _map_feast_features(res, feature_refs)


def _predict_and_create_response(features: Dict[str, Any], sk_id_curr: str) -> Dict[str, Any]:
    """Shared prediction logic - creates response dict (not ScoreResponse object)."""
    X_df = _as_dataframe_row(features)
    raw = _predict_proba_local(X_df)
    prob = float(raw[0]) if hasattr(raw, "__len__") else float(raw)
    probability, decision = postprocess(prob, settings.prediction_threshold)

    return {
        "sk_id_curr": sk_id_curr,
        "probability": probability,
        "decision": decision,
        "threshold": settings.prediction_threshold,
        "model": MODEL_NAME,
        "version": MODEL_VERSION,
        "ts": datetime.utcnow().isoformat() + "Z",
    }


def _as_dataframe_row(features: Dict[str, Any]) -> pd.DataFrame:
    """Return a single-row DataFrame with all expected columns present.

    Categorical fields should be strings; numeric as numbers. Missing
    columns are included with None to satisfy schema column presence.
    """
    cols = _get_expected_columns()
    row = {col: features.get(col, None) for col in cols}

    return pd.DataFrame([row], columns=cols)


def _resolve_feast_repo_path() -> str:
    """Resolve a usable Feast repo path for FeatureStore.

    Priority:
    1) If settings.feast_repo_path exists and contains feature_store.yaml, use it.
    2) If inline config is enabled and registry/redis envs are present, generate a
       minimal feature_store.yaml in a temp dir and use that.
    3) Otherwise, raise a clear configuration error.

    Also ensures the feast repo is in sys.path so Python modules can be imported.
    """
    try:
        repo = settings.feast_repo_path

        if repo:
            feature_store_path = os.path.join(repo, "feature_store.yaml")

            if os.path.exists(feature_store_path):
                # Add feast repo to sys.path so Feast can import feature_views.py, entities.py, etc.
                import sys

                abs_repo = os.path.abspath(repo)

                if abs_repo not in sys.path:
                    sys.path.insert(0, abs_repo)

                return repo

    except Exception as e:
        logger.error(f"Error resolving Feast repo path: {e}", exc_info=True)

    if settings.feast_inline_config_enabled and settings.feast_registry_uri and settings.feast_redis_url:
        tmpdir = tempfile.mkdtemp(prefix="feast-config-")
        yaml_text = (
            f"project: {settings.feast_project}\n"
            f"registry: {settings.feast_registry_uri}\n"
            f"provider: {settings.feast_provider}\n"
            f"online_store:\n"
            f"  type: redis\n"
            f"  connection_string: {settings.feast_redis_url}\n"
            f"entity_key_serialization_version: 2\n"
        )
        path = os.path.join(tmpdir, "feature_store.yaml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(yaml_text)
        logger.info(f"Generated inline Feast config at {path}")
        return tmpdir

    raise bentoml.exceptions.BentoMLException(
        "Feast config not found. Provide SCORING_FEAST_REPO_PATH with feature_store.yaml, "
        "or set SCORING_FEAST_REGISTRY_URI and SCORING_FEAST_REDIS_URL to generate inline config."
    )


# Lazy, thread-safe model initializer to avoid loading at import/build time
_init_lock = threading.Lock()
_initialized = False
_kafka_started = False

def ensure_model_loaded() -> None:
    global model, MODEL_NAME, MODEL_VERSION, MODEL_FEAST_METADATA, _initialized, _kafka_started
    if _initialized and model is not None:
        return
    with _init_lock:
        if _initialized and model is not None:
            return
        from model_registry import load_model  # runtime import
        with bentoml.importing():
            loaded_model, name, version, feast_metadata = load_model(
                source=settings.model_source,
                path=settings.model_path,
                mlflow_uri=(settings.mlflow_model_uri or "models:/credit_risk_model/Production"),
            )
        if settings.model_name:
            name = settings.model_name
        if settings.model_version:
            version = settings.model_version
        model = loaded_model
        MODEL_NAME = name
        MODEL_VERSION = version
        MODEL_FEAST_METADATA = feast_metadata

        # Validate and log feature selection info
        if not feast_metadata:
            raise RuntimeError(
                f"Model '{name}' is missing feast_metadata.yaml. "
                "This file must be generated during training with fields: "
                "'selected_features', 'feast_feature_refs', 'feature_mapping', 'num_features', 'training_date'. "
                "See download_model_with_metadata.py for details."
            )

        if not feast_metadata.get("selected_features"):
            raise RuntimeError(
                f"Model '{name}' feast_metadata.yaml is missing 'selected_features' field. "
                "Update your training pipeline to include this field."
            )

        logger.info(f"✓ Model trained with {feast_metadata.get('num_features', 0)} features")
        logger.info(f"  Selected features: {feast_metadata.get('selected_features', [])[:5]}...")

        # Dynamic Feast feature discovery and validation
        if not settings.feast_feature_refs and settings.feast_enabled:
            try:
                from feast import FeatureStore

                logger.info("🔍 Discovering Feast features dynamically from registry...")
                resolved_path = _resolve_feast_repo_path()

                fs = FeatureStore(repo_path=resolved_path)

                # Build mapping: feature_name (lowercase) -> (view_name, feast_name)
                feast_available = {}
                stream_views = list(fs.list_stream_feature_views())

                for sfv in stream_views:
                    view_name = sfv.name
                    for field in sfv.schema:
                        # Include ALL fields (including entity key) in feature discovery
                        # The entity key is a valid feature that models may use for prediction
                        field_name_lower = field.name.lower()
                        feast_available[field_name_lower] = (view_name, field.name)

                logger.info(f"✓ Found {len(feast_available)} features across {len(stream_views)} StreamFeatureViews")
                logger.info(f"  Views: {[sfv.name for sfv in stream_views]}")

                # VALIDATION: Check all model features exist in Feast
                required_features = feast_metadata["selected_features"]

                missing_features = []
                feast_feature_refs = []
                feature_mapping = {}

                for feat in required_features:
                    feat_lower = feat.lower()
                    if feat_lower in feast_available:
                        view_name, feast_name = feast_available[feat_lower]
                        feast_feature_refs.append(f"{view_name}:{feast_name}")
                        feature_mapping[feast_name] = feat  # Map Feast name -> model column
                    else:
                        missing_features.append(feat)

                if missing_features:
                    error_msg = (
                        f"\n{'='*70}\n"
                        f"❌ STARTUP VALIDATION FAILED\n"
                        f"{'='*70}\n"
                        f"Model requires {len(missing_features)} features NOT in Feast registry:\n\n"
                        f"Missing features:\n"
                    )
                    for feat in missing_features[:20]:  # Show first 20
                        error_msg += f"  • {feat}\n"
                    if len(missing_features) > 20:
                        error_msg += f"  ... and {len(missing_features) - 20} more\n"

                    error_msg += (
                        f"\nModel info:\n"
                        f"  • Trained on: {feast_metadata.get('training_date', 'unknown')}\n"
                        f"  • Requires: {len(required_features)} features\n"
                        f"  • Missing: {len(missing_features)} features\n\n"
                        f"Feast info:\n"
                        f"  • Available views: {[sfv.name for sfv in stream_views]}\n"
                        f"  • Available features: {len(feast_available)}\n\n"
                        f"ACTION REQUIRED:\n"
                        f"  1. Update Feast StreamFeatureViews to include missing features\n"
                        f"  2. Sample Kafka topics to generate schemas:\n"
                        f"     python application/feast/generate_schemas_from_kafka.py\n"
                        f"  3. Update feature_views.py to use generated schemas\n"
                        f"  4. Rebuild Docker image and redeploy Feast:\n"
                        f"     kubectl apply -k services/ml/k8s/feature-store/\n"
                        f"  5. Redeploy this service\n"
                        f"{'='*70}\n"
                    )
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)

                # All features found! Cache the mapping
                settings.feast_feature_refs = ",".join(feast_feature_refs)

                # Store feature mapping in metadata for later use (don't overwrite if exists)
                if "feature_mapping" not in MODEL_FEAST_METADATA:
                    MODEL_FEAST_METADATA["feature_mapping"] = feature_mapping
                    logger.info(f"   Stored dynamically generated feature_mapping ({len(feature_mapping)} entries)")
                else:
                    logger.info(f"   Preserving existing feature_mapping from feast_metadata.yaml")
                MODEL_FEAST_METADATA["feast_feature_refs"] = settings.feast_feature_refs

                logger.info(f"✅ Startup validation passed: All {len(required_features)} features found in Feast")
                logger.info(f"   Views used: {set(v for v, _ in feast_available.values() if any(f.lower() in feast_available for f in required_features))}")
                logger.info(f"   Cached {len(feast_feature_refs)} Feast feature refs")

            except RuntimeError:
                # Re-raise validation errors
                raise
            except Exception as e:
                logger.error(f"❌ Failed to discover Feast features: {e}")
                logger.error("   Serving will not work properly without Feast feature refs")
                raise RuntimeError(f"Feast discovery failed: {e}")
        elif settings.feast_feature_refs:
            logger.info(f"✓ Using pre-configured feast_feature_refs from env var ({len(settings.feast_feature_refs.split(','))} features)")
        else:
            logger.warning("⚠ Feast disabled or no feature refs configured")

        _initialized = True

        # Optionally start Kafka consumer once
        if settings.enable_kafka and not _kafka_started:  # pragma: no cover
            threading.Thread(target=_run_kafka_consumer, daemon=True).start()
            _kafka_started = True


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


def _run_kafka_consumer():  # pragma: no cover
    if not KafkaConsumer:
        logger.warning("kafka-python not installed; skipping Kafka consumer")
        return
    try:
        # Subscribe to BOTH loan applications and feature readiness topics
        consumer = KafkaConsumer(
            settings.loan_application_topic,
            settings.feature_ready_topic,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=settings.kafka_group_id,
            enable_auto_commit=True,
            auto_offset_reset="latest",
            value_deserializer=lambda v: json.loads(v.decode("utf-8")) if v else {},
            key_deserializer=lambda v: v.decode("utf-8") if v else None,
        )
        producer: Optional[KafkaProducer] = None
        if settings.scoring_output_topic:
            producer = KafkaProducer(
                bootstrap_servers=settings.kafka_bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda v: (v.encode("utf-8") if isinstance(v, str) else v),
            )

        # Store pending loan applications waiting for features
        pending_requests: Dict[str, Dict[str, Any]] = {}

        logger.info(
            f"Kafka consumer started: topics=[{settings.loan_application_topic}, {settings.feature_ready_topic}], group={settings.kafka_group_id}"
        )
        for msg in consumer:
            try:
                # Route based on topic
                if msg.topic == settings.feature_ready_topic:
                    # Feature ready notification - process pending request
                    sk_id = msg.key or str(msg.value.get("sk_id_curr", "")).strip()
                    if not sk_id or sk_id not in pending_requests:
                        logger.debug(f"No pending request for sk_id_curr={sk_id}, skipping")
                        continue

                    # Retrieve pending request details
                    req = pending_requests.pop(sk_id)
                    payload = req["payload"]
                    parent_context = req.get("parent_context")

                    # Start span with trace context
                    span_context = tracer.start_as_current_span("scoring_inference", context=parent_context) if tracer and parent_context else None
                    if span_context:
                        span_context.__enter__()
                        trace.get_current_span().set_attribute("sk_id_curr", sk_id)

                    # Fetch features and predict using shared helper functions
                    try:
                        features = _fetch_features_from_feast(sk_id)
                        result = _predict_and_create_response(features, sk_id)
                        logger.bind(event="stream_inference").info(result)

                        if producer and settings.scoring_output_topic:
                            producer.send(settings.scoring_output_topic, key=sk_id, value=result)

                    except bentoml.exceptions.BentoMLException as e:
                        logger.warning(f"Feature fetch failed for sk_id_curr={sk_id}: {e}")
                        if producer and settings.scoring_output_topic:
                            result = {
                                "sk_id_curr": sk_id,
                                "probability": None,
                                "decision": "under-review",
                                "threshold": settings.prediction_threshold,
                                "model": MODEL_NAME,
                                "version": MODEL_VERSION,
                                "ts": datetime.utcnow().isoformat() + "Z",
                                "reason": "feature_data_unavailable"
                            }
                            producer.send(settings.scoring_output_topic, key=sk_id, value=result)
                    except Exception as e:
                        logger.error(f"Prediction failed for sk_id_curr={sk_id}: {e}")


                    if span_context:
                        span_context.__exit__(None, None, None)
                    continue

                # Loan application event - store as pending
                payload = msg.value or {}
                sk_id = str(payload.get("sk_id_curr") or payload.get("customer_id") or "").strip()
                if not sk_id:
                    sk_id = (_extract_sk_id_curr_from_cdc(payload) or "").strip()
                if not sk_id and msg.key:
                    try:
                        key_obj = json.loads(msg.key)
                        if isinstance(key_obj, dict):
                            key_payload = key_obj.get("payload") or key_obj
                            if isinstance(key_payload, dict) and key_payload.get("sk_id_curr"):
                                sk_id = str(key_payload.get("sk_id_curr"))
                    except Exception:
                        pass

                if not sk_id:
                    logger.debug("No sk_id_curr found in loan application message, skipping")
                    continue

                # Extract trace context for later use
                parent_context = None
                if extract_or_create_trace_context and sk_id and msg.headers:
                    headers_dict = {k: v.decode('utf-8') if isinstance(v, bytes) else v
                                   for k, v in (msg.headers or [])}
                    parent_context = extract_or_create_trace_context(headers_dict, sk_id)

                # Store pending request (will be processed when feature_ready arrives)
                pending_requests[sk_id] = {
                    "payload": payload,
                    "parent_context": parent_context,
                    "received_at": datetime.utcnow().isoformat()
                }
                logger.info(f"Stored pending loan application for sk_id_curr={sk_id}, waiting for feature_ready notification")

            except Exception as e:
                logger.error(f"Error processing Kafka message: {e}")
    except Exception as e:
        logger.error(f"Kafka consumer failed to start: {e}")


# Mount FastAPI app into Bento service
svc.mount_asgi_app(app, path="/")
