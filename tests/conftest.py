"""
Shared pytest fixtures for all tests.

This module provides reusable fixtures for:
- Database connections (PostgreSQL, ClickHouse)
- Mock services (Redis, Kafka, MLflow)
- Test data generation
- HTTP clients for API testing
"""

import asyncio
import os
from typing import AsyncGenerator, Generator
from unittest.mock import MagicMock

import pytest
from faker import Faker
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Import application modules
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.config import Settings
from core.database import Base
from db_models.database import LoanApplication


# ============================================================================
# Event Loop Configuration
# ============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# Test Data Generators
# ============================================================================

@pytest.fixture(scope="session")
def faker_instance() -> Faker:
    """Create Faker instance for test data generation."""
    Faker.seed(12345)  # Reproducible test data
    return Faker()


@pytest.fixture
def sample_loan_application(faker_instance: Faker) -> dict:
    """Generate sample loan application data."""
    return {
        "sk_id_curr": faker_instance.random_int(min=100000, max=999999),
        "name_contract_type": "Cash loans",
        "code_gender": "M",
        "flag_own_car": "Y",
        "flag_own_realty": "N",
        "cnt_children": 0,
        "amt_income_total": 150000.0,
        "amt_credit": 500000.0,
        "amt_annuity": 25000.0,
        "amt_goods_price": 450000.0,
        "name_income_type": "Working",
        "name_education_type": "Higher education",
        "name_family_status": "Married",
        "name_housing_type": "House / apartment",
        "days_birth": -12000,
        "days_employed": -1500,
        "cnt_fam_members": 2.0,
    }


# ============================================================================
# Database Fixtures
# ============================================================================

@pytest.fixture(scope="function")
async def async_db_engine():
    """Create in-memory SQLite async engine for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest.fixture(scope="function")
async def async_db_session(
    async_db_engine,
) -> AsyncGenerator[AsyncSession, None]:
    """Create async database session for testing."""
    async_session_maker = sessionmaker(
        async_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        yield session


# ============================================================================
# Mock Service Fixtures
# ============================================================================

@pytest.fixture
def mock_redis():
    """Mock Redis client for unit tests."""
    import fakeredis
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def mock_kafka_producer():
    """Mock Kafka producer."""
    mock_producer = MagicMock()
    mock_producer.send.return_value = MagicMock()
    mock_producer.flush.return_value = None
    return mock_producer


@pytest.fixture
def mock_kafka_consumer():
    """Mock Kafka consumer."""
    mock_consumer = MagicMock()
    mock_consumer.subscribe.return_value = None
    mock_consumer.poll.return_value = None
    return mock_consumer


@pytest.fixture
def mock_mlflow_client():
    """Mock MLflow client for model registry tests."""
    mock_client = MagicMock()
    mock_client.get_latest_versions.return_value = [
        MagicMock(version=1, run_id="test_run_id")
    ]
    return mock_client


# ============================================================================
# HTTP Client Fixtures
# ============================================================================

@pytest.fixture
async def api_client() -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client for API testing."""
    from api.main import app

    async with AsyncClient(
        app=app,
        base_url="http://test",
        follow_redirects=True,
    ) as client:
        yield client


# ============================================================================
# Configuration Fixtures
# ============================================================================

@pytest.fixture
def test_settings() -> Settings:
    """Create test settings with overrides."""
    return Settings(
        # Database settings
        POSTGRES_USER="test_user",
        POSTGRES_PASSWORD="test_password",
        POSTGRES_HOST="localhost",
        POSTGRES_PORT=5432,
        POSTGRES_DB="test_db",

        # MinIO settings
        MINIO_ENDPOINT="localhost:9000",
        MINIO_ACCESS_KEY="test_access",
        MINIO_SECRET_KEY="test_secret",

        # Kafka settings
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",

        # Redis settings
        REDIS_HOST="localhost",
        REDIS_PORT=6379,

        # API settings
        API_V1_PREFIX="/api/v1",
        DEBUG=True,
    )


# ============================================================================
# Cleanup Fixtures
# ============================================================================

@pytest.fixture(autouse=True)
def reset_environment():
    """Reset environment variables after each test."""
    original_env = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original_env)
