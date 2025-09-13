"""Model loading helpers with local or MLflow backends."""

from typing import Any, Optional, Tuple
from loguru import logger
import importlib
import os
import re


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
    """Load a model from MLflow.

    Prefer native flavors (sklearn/xgboost) for access to predict_proba.
    Fallback to generic pyfunc if native loaders are unavailable.
    """
    mlflow = importlib.import_module("mlflow")  # optional dependency
    # Try native sklearn first
    try:
        return mlflow.sklearn.load_model(uri)  # type: ignore[attr-defined]
    except Exception:
        pass
    # Then try native xgboost
    try:
        return mlflow.xgboost.load_model(uri)  # type: ignore[attr-defined]
    except Exception:
        pass
    # Fallback to pyfunc
    return mlflow.pyfunc.load_model(uri)


def load_model(
    *, source: str, path: Optional[str], mlflow_uri: Optional[str]
) -> Tuple[Any, str, Optional[str]]:
    """Return (model, model_name, model_version).

    For MLflow URIs of the form models:/<name>/<stage|version>, this attempts to
    resolve the exact registered model version via MlflowClient. Falls back to
    MODEL_NAME / MODEL_VERSION env vars when resolution is not possible.
    """
    if source == "mlflow":
        if not mlflow_uri:
            raise ValueError("mlflow_model_uri is required when model_source=mlflow")
        logger.info(f"Loading model from MLflow: {mlflow_uri}")
        model = _load_mlflow_model(mlflow_uri)

        # Defaults from env (optional override)
        name_env = os.environ.get("MODEL_NAME")
        version_env = os.environ.get("MODEL_VERSION")

        name: Optional[str] = name_env or None
        version: Optional[str] = version_env or None

        # Try to resolve from the MLflow registry if possible
        try:
            mlflow = importlib.import_module("mlflow")
            client = mlflow.tracking.MlflowClient()  # type: ignore[attr-defined]
            m = re.match(r"models:/([^/]+)/([^/]+)$", mlflow_uri.strip())
            if m:
                parsed_name, stage_or_version = m.group(1), m.group(2)
                name = name or parsed_name
                # If it looks like a stage name, resolve latest version at that stage
                if stage_or_version.isalpha():
                    vers = client.get_latest_versions(parsed_name, [stage_or_version])
                    if vers:
                        version = vers[0].version
                else:
                    # numeric or tagged version
                    version = stage_or_version
        except Exception as e:
            logger.debug(f"Could not resolve MLflow model version: {e}")

        # Final fallbacks
        name = name or "credit_risk_model"
        return model, name, version
    if path:
        logger.info(f"Loading local model: {path}")
        model = _load_local_model(path)
        name = os.path.basename(path)
        return model, name, None
    raise ValueError("Provide model_path or use MLflow source")
