"""Model loading helpers with local or MLflow backends."""

from typing import Any, Optional, Tuple
from loguru import logger
import importlib
import os


def _load_local_model(path: str) -> Any:
    """Load a local pickle/joblib model."""
    if path.endswith((".joblib", ".pkl")):
        try:
            joblib = importlib.import_module("joblib")
            return joblib.load(path)
        except ModuleNotFoundError:
            import pickle
            with open(path, "rb") as f:
                return pickle.load(f)
    raise ValueError(f"Unsupported model file: {path}")


def _load_mlflow_model(uri: str) -> Any:
    """Load a model from MLflow using pyfunc/sklearn/xgboost flavors."""
    mlflow = importlib.import_module("mlflow")  # optional dependency
    try:
        return mlflow.pyfunc.load_model(uri)
    except Exception:
        try:
            return mlflow.sklearn.load_model(uri)
        except Exception:
            return mlflow.xgboost.load_model(uri)


def load_model(
    *, source: str, path: Optional[str], mlflow_uri: Optional[str]
) -> Tuple[Any, str, Optional[str]]:
    """Return (model, model_name, model_version)."""
    if source == "mlflow":
        if not mlflow_uri:
            raise ValueError("mlflow_model_uri is required when model_source=mlflow")
        logger.info(f"Loading model from MLflow: {mlflow_uri}")
        model = _load_mlflow_model(mlflow_uri)
        name = os.environ.get("MODEL_NAME", "credit_risk_model")
        version = os.environ.get("MODEL_VERSION")
        return model, name, version
    if path:
        logger.info(f"Loading local model: {path}")
        model = _load_local_model(path)
        name = os.path.basename(path)
        return model, name, None
    raise ValueError("Provide model_path or use MLflow source")
