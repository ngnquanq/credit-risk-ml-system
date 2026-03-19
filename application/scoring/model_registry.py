"""Model loading helpers with local or MLflow backends."""

from typing import Any, Optional, Tuple, Dict, List
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


def _load_feast_metadata(mlflow_uri: str) -> Optional[Dict[str, Any]]:
    """Load feast_metadata.yaml from MLflow model artifacts if available.

    Returns feast metadata dict or None if not found.
    """
    try:
        import tempfile
        import yaml
        mlflow = importlib.import_module("mlflow")
        client = mlflow.tracking.MlflowClient()  # type: ignore[attr-defined]

        # Parse model URI to get run_id
        m = re.match(r"models:/([^/]+)/([^/]+)$", mlflow_uri.strip())
        if not m:
            logger.debug("MLflow URI not in models:/ format, cannot load feast metadata")
            return None

        model_name, stage_or_version = m.group(1), m.group(2)

        # Resolve to specific version
        if stage_or_version.isalpha():
            # It's a stage name
            versions = client.get_latest_versions(model_name, [stage_or_version])
            if not versions:
                logger.warning(f"No model versions found for {model_name}/{stage_or_version}")
                return None
            model_version = versions[0]
        else:
            # It's a version number
            model_version = client.get_model_version(model_name, stage_or_version)

        run_id = model_version.run_id
        logger.info(f"Loading feast metadata from run {run_id}")

        # Download feast_metadata.yaml artifact
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                artifact_path = client.download_artifacts(run_id, "feast_metadata.yaml", tmpdir)
                with open(artifact_path, "r") as f:
                    metadata = yaml.safe_load(f)
                logger.info(f"✓ Loaded feast metadata: {metadata.get('num_features', 0)} features")
                return metadata
            except Exception as e:
                logger.warning(f"feast_metadata.yaml not found in model artifacts: {e}")
                return None

    except Exception as e:
        logger.warning(f"Failed to load feast metadata: {e}")
        return None


def load_model(
    *, source: str, path: Optional[str], mlflow_uri: Optional[str]
) -> Tuple[Any, str, Optional[str], Optional[Dict[str, Any]]]:
    """Return (model, model_name, model_version, feast_metadata).

    For MLflow URIs of the form models:/<name>/<stage|version>, this attempts to
    resolve the exact registered model version via MlflowClient. Falls back to
    MODEL_NAME / MODEL_VERSION env vars when resolution is not possible.

    feast_metadata contains feature selection info from training if available.
    """
    if source == "mlflow":
        if not mlflow_uri:
            raise ValueError("mlflow_model_uri is required when model_source=mlflow")
        logger.info(f"Loading model from MLflow: {mlflow_uri}")
        model = _load_mlflow_model(mlflow_uri)

        # Load feast metadata (feature selection from training)
        feast_metadata = _load_feast_metadata(mlflow_uri)

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
        return model, name, version, feast_metadata
    if path:
        logger.info(f"Loading local model: {path}")
        model = _load_local_model(path)
        name = os.path.basename(path)

        # Try to load feast_metadata.yaml from same directory as model
        feast_metadata = None
        model_dir = os.path.dirname(os.path.abspath(path))
        metadata_path = os.path.join(model_dir, "feast_metadata.yaml")

        logger.debug(f"Looking for feast_metadata.yaml: model_dir={model_dir}, metadata_path={metadata_path}, exists={os.path.exists(metadata_path)}")

        if os.path.exists(metadata_path):
            try:
                import yaml
                with open(metadata_path, "r") as f:
                    feast_metadata = yaml.safe_load(f)
                logger.info(f"✓ Loaded feast metadata from {metadata_path}: {feast_metadata.get('num_features', 0)} features")
            except Exception as e:
                logger.warning(f"Failed to load feast_metadata.yaml from {metadata_path}: {e}")
        else:
            logger.warning(f"⚠ No feast_metadata.yaml found at {metadata_path} - model will fail to load in service.py")

        return model, name, None, feast_metadata
    raise ValueError("Provide model_path or use MLflow source")
