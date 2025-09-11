from pydantic import Field, ConfigDict
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
    api_prefix: str = Field(default="/api/v1", description="API prefix")
    
    # Database Configuration
    database_url: str = Field(
        default="postgresql+asyncpg://ops_admin:ops_password@localhost:5434/operations",
        description="Database connection URL"
    )
    database_pool_size: int = Field(default=10, description="Database connection pool size")
    database_max_overflow: int = Field(default=20, description="Database max overflow connections")

    # External Bureau Database (read-only) Configuration
    bureau_database_url: str = Field(
        default="postgresql+asyncpg://bureau_admin:bureau_secure_password@localhost:5435/bureau_db",
        description="External bureau database connection URL"
    )
    bureau_db_pool_size: int = Field(default=10, description="Bureau DB connection pool size")
    bureau_db_max_overflow: int = Field(default=20, description="Bureau DB max overflow connections")

    # Data Warehouse Database Configuration
    dwh_database_url: str = Field(
        default="postgresql+asyncpg://dwh_admin:dwh_password@localhost:5432/warehouse",
        description="Data warehouse database connection URL"
    )
    dwh_db_pool_size: int = Field(default=10, description="DWH DB connection pool size")
    dwh_db_max_overflow: int = Field(default=20, description="DWH DB max overflow connections")

    # ClickHouse configuration (used for bureau and/or DWH)
    clickhouse_host: str = Field(default="localhost", description="ClickHouse host")
    clickhouse_port: int = Field(default=8123, description="ClickHouse HTTP port")
    clickhouse_user: str = Field(default="default", description="ClickHouse user")
    clickhouse_password: str = Field(default="", description="ClickHouse password")

    # Logical database for external/bureau data inside ClickHouse
    clickhouse_db_external: str = Field(default="application_external", description="ClickHouse database for external/bureau data")
    # Logical database for internal/company DWH mart inside ClickHouse
    clickhouse_db_dwh: str = Field(default="application_mart", description="ClickHouse database for internal DWH mart")

    # Kafka configuration for streaming pipeline
    kafka_bootstrap_servers: str = Field(
        default="localhost:9092",
        description="Kafka bootstrap servers"
    )
    
    # Logging
    log_level: str = Field(default="INFO", description="Log level")
    log_format: str = Field(default="json", description="Log format: json or text")
    
    # CORS Settings
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        description="CORS allowed origins"
    )
    
    # Application Limits
    max_application_amount: float = Field(default=1000000.0, description="Maximum loan amount")
    min_application_amount: float = Field(default=1000.0, description="Minimum loan amount")

    # MinIO / S3-compatible object storage
    minio_endpoint: str = Field(default="localhost:9000", description="MinIO endpoint host:port")
    minio_access_key: str = Field(default="minioadmin", description="MinIO access key")
    minio_secret_key: str = Field(default="minioadmin", description="MinIO secret key")
    minio_secure: bool = Field(default=False, description="Use HTTPS for MinIO")
    minio_bucket: str = Field(default="loan-documents", description="MinIO bucket for documents")
    minio_presigned_expiry_minutes: int = Field(
        default=60, description="Expiry for presigned URLs in minutes"
    )
    


# Global settings instance
settings = Settings()
