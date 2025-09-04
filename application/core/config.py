from pydantic import Field
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
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
        default="postgresql+asyncpg://ops_admin:ops_password@ops-postgres:5432/operations",
        description="Database connection URL"
    )
    database_pool_size: int = Field(default=10, description="Database connection pool size")
    database_max_overflow: int = Field(default=20, description="Database max overflow connections")
    
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
    
    class Config:
        env_file = ".env"
        env_prefix = "APP_"
        case_sensitive = False


# Global settings instance
settings = Settings()