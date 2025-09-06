"""BentoML service for credit risk scoring.

Aligned with application's coding style: env settings, Pydantic schemas,
structured logging, and small, focused modules.
"""

from typing import Dict, Any, Optional
from datetime import datetime
import bentoml
from loguru import logger
from fastapi import FastAPI

from config import settings
from schemas import ScoreRequest, ScoreResponse
from model_registry import load_model
from pipeline import as_vector, postprocess
from logger import configure_logger


# Configure logging (defaults from core, overridable via SCORING_*)
configure_logger(settings.log_level, settings.log_format)


# Load model and metadata once per worker
model, MODEL_NAME, MODEL_VERSION = load_model(
    source=settings.model_source, path=settings.model_path, mlflow_uri=settings.mlflow_model_uri
)


def _predict_proba_local(X):
    """Predict probability using the loaded model without Runner.

    Keeps compatibility across sklearn/xgboost/mlflow.pyfunc models.
    """
    if hasattr(model, "predict_proba"):
        return model.predict_proba(X)[:, 1]
    if hasattr(model, "predict"):
        return model.predict(X)
    raise RuntimeError("Model does not support prediction")


svc = bentoml.Service("credit_risk_scoring")


app = FastAPI(title="Credit Risk Scoring")


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
    feature_order: Optional[list[str]] = (
        [c.strip() for c in settings.feature_names.split(",")]
        if settings.feature_names
        else None
    )
    X = as_vector(req.features, feature_order)
    raw = _predict_proba_local(X)
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
        {
            "user_id": req.user_id,
            "probability": probability,
            "decision": decision,
            "model": MODEL_NAME,
            "version": MODEL_VERSION,
        }
    )
    return resp.model_dump()


# Mount FastAPI app into Bento service for maximum compatibility across versions
svc.mount_asgi_app(app, path="/")
