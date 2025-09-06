"""Scoring service configuration, aligned with core settings style."""

from typing import Optional
from pydantic import Field, ConfigDict
from pydantic_settings import BaseSettings

try:  # Prefer app-wide defaults when available
    from application.core.config import settings as app_settings  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    app_settings = None


class ScoringSettings(BaseSettings):
    """Environment-driven settings for the Bento scoring service."""

    model_config = ConfigDict(
        env_prefix="SCORING_",
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    # Model loading
    model_source: str = Field(default="local", description="local|mlflow")
    model_path: Optional[str] = Field(
        default=None, description="Local pickle/joblib model path"
    )
    mlflow_model_uri: Optional[str] = Field(
        default=None, description="MLflow model URI e.g. models:/name/Production"
    )

    # Inference
    prediction_threshold: float = Field(default=0.5)
    feature_names: Optional[str] = Field(
        default=None, description="Comma-separated feature order"
    )

    # Observability (default to core app settings when present)
    log_format: str = Field(
        default=(getattr(app_settings, "log_format", "json") or "json")
    )
    log_level: str = Field(
        default=(getattr(app_settings, "log_level", "INFO") or "INFO")
    )


settings = ScoringSettings()
