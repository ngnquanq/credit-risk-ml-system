"""Scoring service configuration, aligned with core settings style."""

import os
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
        env_file="mlflow.env",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=("settings_",),
    )

    # Model loading
    model_source: str = Field(default="mlflow", description="local|mlflow")
    model_path: Optional[str] = Field(
        default=None, description="Local pickle/joblib model path"
    )
    mlflow_model_uri: Optional[str] = Field(
        default=None, description="MLflow model URI e.g. models:/name/Production"
    )
    # Optional explicit metadata overrides (appear in responses/logs)
    model_name: Optional[str] = Field(default=None, description="Override model name for responses")
    model_version: Optional[str] = Field(default=None, description="Override model version for responses")

    # Inference
    prediction_threshold: float = Field(default=0.3, description="Probability that customer will default")
    feature_names: Optional[str] = Field(
        default=None, description="Comma-separated feature order"
    )

    # Feast integration 
    feast_enabled: bool = Field(default=True, description="Enable Feast online retrieval")
    feast_repo_path: str = Field(
        default=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "feast")),
        description="Path to Feast repo for FeatureStore (absolute path to avoid working directory issues)"
    )
    # Optional inline Feast config (use when you don't ship the repo)
    feast_inline_config_enabled: bool = Field(
        default=True,
        description="Allow generating minimal feature_store.yaml from env if repo_path is missing",
    )
    feast_project: str = Field(default="hc", description="Feast project name")
    feast_provider: str = Field(default="local", description="Feast provider")
    feast_registry_uri: Optional[str] = Field(
        default=None,
        description="URI/path to Feast registry (e.g., s3://bucket/feast/registry.db or file path)",
    )
    feast_redis_url: Optional[str] = Field(
        default=None,
        description="Redis connection string for Feast online store (e.g., redis://feast-redis:6379/0)",
    )
    # Feast feature refs - loaded from feast_metadata.yaml at runtime
    feast_feature_refs: Optional[str] = Field(
        default=None,
        description="Comma-separated Feast feature references (set via env var or loaded from model's feast_metadata.yaml)",
    )

    # Kafka integration (optional streaming scoring)
    enable_kafka: bool = Field(default=True, description="Enable Kafka consumer for loan applications")
    kafka_bootstrap_servers: str = Field(
        default="broker:29092", description="Kafka bootstrap servers"
    )
    loan_application_topic: str = Field(
        default="hc.applications.public.loan_applications", description="Kafka topic with loan application events"
    )
    kafka_group_id: str = Field(
        default="bento-scoring", description="Kafka consumer group id for scoring"
    )
    scoring_output_topic: Optional[str] = Field(
        default="hc.scoring", description="Optional Kafka topic to publish scoring results"
    )

    # Data validation
    require_customer_data: bool = Field(
        default=True, description="Require customer data to exist in Redis before prediction"
    )

    # Feast retry configuration (handle race condition with feast-stream materialization)
    feast_retry_enabled: bool = Field(
        default=True, description="Enable retry logic when Feast returns no features"
    )
    feast_retry_max_attempts: int = Field(
        default=15, description="Maximum number of Feast lookup retry attempts (15 × 300ms = 4.5s max wait)"
    )
    feast_retry_delay_ms: int = Field(
        default=300, description="Fixed delay between retries in milliseconds"
    )
    feast_retry_backoff_multiplier: float = Field(
        default=1.0, description="Backoff multiplier (1.0 = fixed delay, >1.0 = exponential backoff)"
    )

    # Observability (default to core app settings when present)
    log_format: str = Field(
        default=(getattr(app_settings, "log_format", "json") or "json")
    )
    log_level: str = Field(
        default=(getattr(app_settings, "log_level", "INFO") or "INFO")
    )


settings = ScoringSettings()
