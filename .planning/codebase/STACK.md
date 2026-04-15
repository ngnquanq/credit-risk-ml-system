# Technology Stack

**Analysis Date:** 2026-04-15

## Languages

**Primary:**
- Python 3.10+ - Core application, ML/data pipeline, API, scoring service, ETL jobs, feature engineering
- SQL - dbt models, ClickHouse transforms, PostgreSQL schemas
- YAML - Kubernetes manifests, Helm charts, Kafka topic config, dbt profiles

**Secondary:**
- Bash - Makefile targets, deployment scripts, infrastructure tooling

## Runtime

**Environment:**
- Python 3.10 (primary), supports 3.9+
- Language requirement: `requires-python = ">=3.9"` in `pyproject.toml`

**Package Manager:**
- pip (system package management)
- Lockfile: Manual `requirements.txt` files (no poetry.lock or Pipfile.lock detected)
- Installation targets:
  - Root: `requirements.txt` (112 packages, primary dependencies)
  - API service: `application/entrypoints/requirements.txt` (13 packages, subset for entrypoints)
  - API service: `application/requirements-api.txt` (referenced in Dockerfile)

## Frameworks

**Core Application:**
- FastAPI 0.112.2 - REST API framework, ASGI server, CORS middleware
  - Entry point: `application/entrypoints/api/main.py`
  - Tracing instrumented via OpenTelemetry FastAPIInstrumentor
- Pydantic 2.8.2 / pydantic-settings 2.4.0 - Data validation, configuration management via env vars
  - Config: `application/core/config.py` (APP_* prefix), `application/scoring/config.py` (SCORING_* prefix)
- SQLAlchemy 1.4.53 (with 2.0.43 in entrypoints) - ORM for PostgreSQL operations
  - Models: `application/infrastructure/persistence/models/sqlalchemy_models.py`

**ML & Modeling:**
- XGBoost 3.0.5 - Credit risk classification model (binary: approve/reject)
  - Training: `application/training/train_register.py` (sklearn pipeline wrapper)
  - Inference: BentoML service wraps XGBoost model
  - Config: Threshold 0.3, trained on 24 features, AUC ~0.77

**Serving & Model Management:**
- BentoML 1.4.23 - ML model serving framework
  - Service: `application/scoring/service.py` (REST endpoints /v1/score, /v1/score-by-id)
  - Outputs: CloudEvent-wrapped predictions for Knative compatibility
  - Model loading: MLflow registry or local joblib
- MLflow 3.3.2 - Model tracking, versioning, registry (Production stage promotion)
  - Tracking URI: `MLFLOW_TRACKING_URI` env var
  - Model URI: `models:/credit_risk_model/Production`
  - Storage: S3 via MinIO (configured with AWS_* env vars)
  - Metadata: `feast_metadata.yaml` for feature mapping

**Feature Engineering & Store:**
- Feast 0.31.1+ - Feature store with Redis online store
  - Config: `application/feast_repo/feature_store.yaml`
  - Registry: S3 (MinIO) - `s3://feast-registry/feature_repo/registry.db`
  - Online store: Redis 4.6.0 at `feast-redis.feature-registry:6379`
  - Feature views: `fv_application_features`, `fv_external`, `fv_dwh` (100+ features combined)
  - Stream processor: `application/feast_repo/stream_processor.py` (micro-batching, 200 records or 300ms timeout)
  - Python client: Used in scoring service for online feature retrieval

**Stream Processing & ETL:**
- PyFlink 1.17 - Distributed CDC and bureau aggregation jobs
  - CDC ETL: `application/flink/jobs/cdc_application_etl.py` (40+ application features)
  - Bureau aggregation: `application/flink/jobs/bureau_aggregation_etl.py` (60+ external features)
  - Custom UDFs: `cdc_udfs.py`, `bureau_aggregation_udfs.py` for transformations
  - Deployment: Flink JobManager + TaskManager (4 task slots)
  - Language: Python via PyFlink (py4j 0.10.9.7 for JVM bridge)

**Data Transformation & Warehousing:**
- dbt 1.0+ (implied by dbt_project.yml) - ClickHouse data mart orchestration
  - Project: `ml_data_mart/` (staging views, warehouse tables, marts)
  - Target: ClickHouse (application_mart database for gold/analytical layer)
  - Models: marts for previous_application, pos_cash_balance, credit_card_balance

**Testing:**
- pytest 7.0+ - Test runner for 194 unit/integration tests
- pytest-asyncio 0.23+ - Async test support
- pytest-mock 3.12+ - Mocking for isolation
- httpx 0.27+ - Async HTTP client for API testing
- aiosqlite 0.20+ - In-memory SQLite for integration tests

**Build & Deployment:**
- Docker - Containerization for application, consumers, Flink, dbt, frontend
  - `application/Dockerfile` - Python 3.10-slim base
  - `ml_data_mart/Dockerfile` - dbt image
- Kubernetes (Minikube for local dev, production on managed K8s)
  - Helm charts for packaging (KServe CRD includes Chart.yaml)
- Makefile - Build orchestration (make k8s-up, make build-api, etc.)

**Development Tools:**
- Black 22.x - Code formatting (88 char line length)
- isort 5.x - Import organization (black profile)
- mypy 1.11.2 - Static type checking (Python 3.10 mode, ignore_missing_imports=True)
- loguru 0.7.2 - Structured logging across all services (JSON output configurable)

## Key Dependencies

**Critical (Core Application):**
- fastapi 0.112.2 - HTTP framework
- xgboost 3.0.5 - ML model inference
- bentoml 1.4.23 - Model serving
- mlflow 3.3.2 - Model registry
- feast[redis,kafka] 0.31.1+ - Feature store
- pydantic 2.8.2 - Data validation
- sqlalchemy 1.4.53 - Database ORM
- confluent-kafka 2.4.0 / 2.5.3 - Kafka producer/consumer (event streaming)
  - Used in multiple service replicas (bureau consumer, feature consumer, Feast processor)
- kafka-python 2.2.15 - High-level Kafka API (Feast stream processor)

**Data & Database:**
- psycopg 2.9.10 / psycopg2-binary - PostgreSQL adapter for asyncpg and standard DB access
- asyncpg 0.30.0 - Async PostgreSQL driver (in entrypoints)
- clickhouse-connect 0.7.17 - ClickHouse HTTP client (bureau queries, DWH data)
- sqlalchemy2-stubs 0.0.2a38 - Type hints for SQLAlchemy 2.0
- redis 4.6.0 - Redis client for Feast online store

**ML & Data Science:**
- scikit-learn 1.7.2 - Preprocessing (ColumnTransformer, imputation, encoding)
- pandas 2.2.2 - Data manipulation in training and feature engineering
- numpy 1.24.4 - Numeric operations
- polars 1.33.1 - Fast DataFrame library (alternative to pandas in some pipelines)
- pyarrow 11.0.0 - Columnar format for Feast/Parquet
- dask 2024.8.0 - Distributed computing (optional, for large-scale training)

**Infrastructure & Utilities:**
- uvicorn 0.30.6 - ASGI server (FastAPI runtime)
- gunicorn 23.0.0 - Production WSGI server (alternative to uvicorn)
- httptools 0.6.1 - C speedups for uvicorn
- uvloop 0.20.0 - Libuv-based event loop (faster than asyncio)
- pydantic-settings 2.4.0 - Environment variable support
- python-dotenv 1.0.1 - .env file loading
- tenacity 8.5.0 - Retry logic for resilient operations
- requests 2.32.3 - Synchronous HTTP client (bureau/external APIs)
- minio 9000 (via SDK) - S3-compatible object storage (MinIO)

**Observability & Tracing:**
- opentelemetry-api 1.22.0 - Observability instrumentation
- opentelemetry-sdk 1.22.0 - SDK implementation
- opentelemetry-exporter-otlp-proto-grpc 1.22.0 - OTLP exporter (traces to backend)
  - Tracing setup: `application/core/tracing/setup.py`
  - Sampling rate: 10% (0.1) for API and scoring service

**Serialization & Formats:**
- protobuf 4.25.4 - Protocol Buffers (gRPC, schema definition)
- fastavro 1.9.5 - Apache Avro serialization for Kafka (faster than avro)
- pandavro 1.5.2 - Arrow + Avro bridge
- jsonschema 4.23.0 - JSON Schema validation

**Frontend:**
- Streamlit 1.49.1 - Dashboard UI (`application/frontend/`)
- matplotlib 3.10.6 - Plotting library
- seaborn 0.13.2 - Statistical visualization

**Distributed Computing & Networking:**
- py4j 0.10.9.7 - Java interop for PyFlink
- pyspark 3.5.2 - Spark support (optional, for alternative ETL)
- grpcio 1.66.0 - gRPC framework (KServe communication)
- grpcio-tools 1.62.3 - Protocol compiler for gRPC
- websockets 13.0 - WebSocket support

**Utilities & Helpers:**
- click 8.1.7 - CLI utilities
- joblib 1.5.2 - Serialization (model pickling)
- cloudpickle 3.0.0 - Extended pickle (closure serialization)
- tqdm 4.66.5 - Progress bars
- tabulate 0.9.0 - ASCII table formatting
- typeguard 4.3.0 - Runtime type checking
- typing_extensions 4.12.2 - Type hints backport

**Optional Integrations:**
- acryl-datahub 0.15.0.1 - Data lineage/cataloging (optional, listed in requirements.txt)

## Configuration

**Environment Setup:**
- `.env` file (not committed) - Local development secrets and service endpoints
- `.env.example` - Template with all required variables
  - Database: `OPS_DB_*` (PostgreSQL operational DB)
  - ClickHouse: `APP_CLICKHOUSE_*`
  - Kafka: `APP_KAFKA_BOOTSTRAP_SERVERS`
  - MinIO: `MINIO_*`, `APP_MINIO_*`
  - MLflow: `MLFLOW_TRACKING_URI`, `MLFLOW_S3_ENDPOINT_URL`, AWS credentials
  - Feast: `SCORING_FEAST_*`
  - Scoring: `SCORING_*` (threshold, model source, etc.)
  - Logging: `APP_LOG_*`

**Application Configuration:**
- Pydantic BaseSettings pattern with env_prefix:
  - `application/core/config.py` - APP_* prefix for main application
  - `application/scoring/config.py` - SCORING_* prefix for BentoML service
  - `application/frontend/config.py` - Frontend-specific config

**Build & Runtime Configuration:**
- `pyproject.toml` - Project metadata, dependencies, tool config
  - Black: line_length=88
  - isort: black profile, line_length=88
  - mypy: python_version=3.10, ignore_missing_imports=True
  - pytest: testpaths=["tests"], asyncio_mode=auto, markers for unit/integration/kafka/db/slow
- `Makefile` - Service build and deployment orchestration
  - Minikube profile: mlops (20 CPU, 24GB RAM, 80GB disk, v1.28.3)
  - K8s context: mlops
- Docker compose (legacy, pre-K8s):
  - `platform/docker-compose.yml` and layered composites (storage, warehouse, streaming, CDC, batch, feature-store, registry, serving)
- Kubernetes manifests: Kustomize-based in `platform/*/k8s/`

## Platform Requirements

**Development:**
- Python 3.10 (primary), 3.9+ supported
- Docker & Docker Desktop / Minikube
- GNU Make
- kubectl (for K8s interaction)
- Minikube (local K8s cluster):
  - Driver: docker (configurable)
  - K8s version: v1.28.3
  - Resources: 20 CPU, 24GB RAM, 80GB disk

**Production:**
- Kubernetes 1.28+ cluster
- Namespaces: api-gateway, data-services, feature-registry, kserve, model-registry, model-serving, training-data, ops-prometheus, ops-grafana, ops-logging
- Node resources: CPU and memory as specified in K8s resource requests/limits

**Services Deployed:**
- PostgreSQL 15+ (ops-postgres, ops-pgbouncer for connection pooling)
- Kafka 7.7.1 (Confluent, KRaft mode, no ZooKeeper)
- ClickHouse 25.6+ (OLAP warehouse)
- Debezium 2.7.3 (CDC connector)
- Flink 1.17 (JobManager + TaskManager)
- Redis 7+ (Feast online store)
- MinIO (S3-compatible object storage)
- Knative Serving 1.13.0 (serverless container orchestration)
- Knative Eventing 1.13.7 (event delivery)
- KServe (ML model serving)
- MLflow (model registry)
- Prometheus + Grafana (monitoring)
- ECK / Elasticsearch + Kibana (logging)

---

*Stack analysis: 2026-04-15*
