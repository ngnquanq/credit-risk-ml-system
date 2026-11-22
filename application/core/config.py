from pydantic import Field, ConfigDict, computed_field, SecretStr
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = ConfigDict(extra="ignore", env_file=".env", env_prefix="APP_", case_sensitive=False)

    # Application
    app_name: str = Field(default="Home Credit Loan API", description="Application name")
    app_version: str = Field(default="1.0.0", description="Application version")
    debug: bool = Field(default=False, description="Debug mode")

    # API Configuration
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8000, description="API port")

    # Database configuration (variable names match .env.example)
    ops_db_host: str = Field(default="ops-postgres", description="PostgreSQL host", alias="OPS_DB_HOST")
    ops_db_port: int = Field(default=5432, description="PostgreSQL port", alias="OPS_DB_PORT")
    ops_db_user: str = Field(default="ops_admin", description="PostgreSQL user", alias="OPS_DB_USER")
    ops_db_password: Optional[SecretStr] = Field(default=None, description="PostgreSQL password", alias="OPS_DB_PASSWORD")
    ops_db_name: str = Field(default="operations", description="PostgreSQL database name", alias="OPS_DB_NAME")

    @computed_field
    @property
    def database_url(self) -> str:
        """Construct database URL from individual components."""
        password = self.ops_db_password.get_secret_value() if self.ops_db_password else ""
        return f"postgresql+asyncpg://{self.ops_db_user}:{password}@{self.ops_db_host}:{self.ops_db_port}/{self.ops_db_name}"
    database_pool_size: int = Field(default=10, description="Database connection pool size")
    database_max_overflow: int = Field(default=20, description="Database max overflow connections")

    # ClickHouse configuration (used for bureau and/or DWH)
    clickhouse_host: str = Field(default="localhost", description="ClickHouse host")
    clickhouse_port: int = Field(default=8123, description="ClickHouse HTTP port")
    clickhouse_user: str = Field(default="default", description="ClickHouse user")
    clickhouse_password: Optional[SecretStr] = Field(default=None, description="ClickHouse password")

    # Logical database for external/bureau data inside ClickHouse
    clickhouse_db_external: str = Field(default="application_external", description="ClickHouse database for external/bureau data")
    # Logical database for internal/company DWH mart inside ClickHouse
    clickhouse_db_dwh: str = Field(default="application_mart", description="ClickHouse database for internal DWH mart")

    # Kafka configuration for streaming pipeline
    kafka_bootstrap_servers: str = Field(
        default="localhost:9092",
        description="Kafka bootstrap servers"
    )

    # Topic for submitting loan applications (Source of Truth for DWH and Scoring)
    kafka_application_topic: str = Field(
        default="hc.applications.public.loan_applications",
        description="Kafka topic for new loan applications"
    )

    # Logging
    log_level: str = Field(default="INFO", description="Log level")
    log_format: str = Field(default="json", description="Log format: json or text")

    # CORS Settings
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        description="CORS allowed origins"
    )

    # Identity (E11): Keycloak realms whose tokens the API accepts
    oidc_issuers: str = Field(
        default="",
        description="Comma-separated issuer URLs, e.g. https://auth.credit.local/realms/staff,https://auth.credit.local/realms/customers",
    )
    oidc_audience: str = Field(default="credit-api", description="Required audience in access tokens")
    oidc_jwks_ttl_seconds: int = Field(default=300, description="How long signing keys are cached")
    oidc_staff_required_acr: str = Field(
        default="mfa", description="acr claim required on staff-realm tokens (empty disables the check)"
    )

    @property
    def oidc_issuer_list(self) -> list[str]:
        return [i.strip().rstrip("/") for i in self.oidc_issuers.split(",") if i.strip()]

    # Audit trail (E13): separate database; empty = structured log only
    audit_database_url: Optional[SecretStr] = Field(
        default=None, description="postgresql+asyncpg://audit_writer:...@host:5432/audit"
    )
    audit_reader_database_url: Optional[SecretStr] = Field(
        default=None, description="postgresql+asyncpg://audit_reader:...@host:5432/audit (auditor trace)"
    )

    # External calls made while serving a request (E15): fail fast instead of hanging
    profile_timeout_seconds: float = Field(default=3.0, description="Timeout for the warehouse customer profile")

    # MinIO / S3-compatible object storage
    minio_endpoint: str = Field(default="minio-server:9000", description="MinIO endpoint host:port", alias="MINIO_ENDPOINT")
    minio_access_key: Optional[SecretStr] = Field(default=None, description="MinIO access key")
    minio_secret_key: Optional[SecretStr] = Field(default=None, description="MinIO secret key")
    minio_secure: bool = Field(default=False, description="Use HTTPS for MinIO")
    minio_bucket: str = Field(default="loan-documents", description="MinIO bucket for documents")
    minio_presigned_expiry_minutes: int = Field(
        default=60, description="Expiry for presigned URLs in minutes"
    )

# Global settings instance
settings = Settings()
