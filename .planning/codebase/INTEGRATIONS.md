# External Integrations

**Analysis Date:** 2026-04-15

## APIs & External Services

**Bureau Data Service:**
- Service: External credit bureau (read-only data source)
- What it's used for: Bureau history, account info, credit utilization, payment performance, DPD metrics
- Integration approach: Two-stage pipeline
  - Stage 1: `application/entrypoints/bureau_consumer.py` - Listens to CDC events, queries ClickHouse bureau tables, publishes raw bureau data to Kafka
  - Stage 2: `application/flink/jobs/bureau_aggregation_etl.py` - Aggregates 60+ features (counts, ratios, DPD) from raw arrays
- Code location: `application/infrastructure/external/bureau_adapter.py`, `application/infrastructure/external/bureau_client.py`

**DWH Mart Service:**
- Service: Internal data warehouse (application mart tables in ClickHouse)
- What it's used for: Previous applications, point-of-sale cash balance, credit card balance history
- Integration approach: `application/entrypoints/feature_consumer.py` - Listens to CDC events, queries 3 ClickHouse marts, publishes denormalized rows to Kafka topic `hc.application_dwh`
- Code location: `application/infrastructure/external/dwh_adapter.py`, `application/infrastructure/external/dwh_client_ch.py`

**Model Registry / Tracking:**
- Service: MLflow (model versioning, lifecycle, artifact storage)
  - URI: Environment variable `MLFLOW_TRACKING_URI` (e.g., http://localhost:5000)
- What it's used for: Training, registering, promoting models to Production stage
- Training: `application/training/train_register.py` - Logs metrics (ROC-AUC, precision, recall, F1), parameters, and registers model with MLflow
- Serving: `application/scoring/config.py` reads `SCORING_MLFLOW_MODEL_URI=models:/credit_risk_model/Production` for lazy loading in BentoML
- Artifact backend: MinIO (S3-compatible storage via `MLFLOW_S3_ENDPOINT_URL`)
- Code location: `application/training/train_register.py` (MLflow client integration)

## Data Storage

**Operational Database:**
- Type: PostgreSQL 15+
- Provider: In-cluster (Kubernetes managed)
- Host: `ops-postgres.data-services.svc.cluster.local` (K8s), localhost:5432 (local dev)
- Credentials: Environment `OPS_DB_*` vars (user, password, database name)
- Purpose: Loan applications (status, metadata), application status logs, transactional data
- Connection pooling: PgBouncer on port 6432 (transaction mode, pool_size=200)
- CDC: Debezium 2.7.3 listens to logical replication WAL (pgoutput plugin)
- ORM: SQLAlchemy 1.4.53 (async via asyncpg)
- Schema: `application/infrastructure/persistence/models/sqlalchemy_models.py` defines LoanApplication, ApplicationStatusLog tables

**Data Warehouse:**
- Type: ClickHouse 25.6+ (OLAP)
- Provider: In-cluster (Kubernetes managed)
- Host: `clickhouse-server.data-services.svc.cluster.local:9000` (Native), :8123 (HTTP)
- Credentials: `APP_CLICKHOUSE_*` env vars (user, password)
- Databases:
  - `application_external`: Bureau + external credit data (raw arrays, aggregated features)
  - `application_dwh` / `application_mart`: DWH data (previous apps, POS, credit card; staging/mart layers from dbt)
- Clients:
  - Python: `clickhouse-connect 0.7.17` (HTTP client) in `bureau_client.py`, `dwh_client_ch.py`
  - dbt: ClickHouse dialect (dbt-clickhouse plugin) for `ml_data_mart/` models
- Jupyter access: `notebook/10_clickhouse_test.ipynb` for interactive exploration

**Cache & Feature Store Online Backend:**
- Type: Redis 7+
- Provider: In-cluster (Kubernetes managed)
- Host: `feast-redis.feature-registry.svc.cluster.local:6379` (K8s), localhost:6379 (local dev)
- Credentials: None (default, no authentication)
- Databases:
  - DB 0: Feast online store (100+ features for each sk_id_curr)
  - DB 1: Feast feature readiness coordination (Lua script tracks 3/3 sources per customer)
- Feast integration: `feast[redis,kafka]` client in `application/feast_repo/stream_processor.py`
- Micro-batching: 200 records or 300ms timeout before Redis writes
- TTL: Per-feature-view (1 day for application features, 7 days for external/DWH)

**Registry (Feature Catalog):**
- Type: S3-compatible (MinIO)
- Provider: In-cluster (Kubernetes managed)
- Host: `serving-minio.model-serving.svc.cluster.local:9000` (K8s), localhost:9000 (local dev)
- Credentials: `MINIO_*` env vars (access key, secret key)
- Bucket: `feast-registry`
- Path: `s3://feast-registry/feature_repo/registry.db` (Feast registry database)
- Feast config: `SCORING_FEAST_REGISTRY_URI` (SQLite DB serialized to S3)

**File/Document Storage:**
- Type: S3-compatible (MinIO)
- Provider: In-cluster (Kubernetes managed)
- Host: `serving-minio.model-serving.svc.cluster.local:9000` (K8s), localhost:9000 (local dev)
- Credentials: `APP_MINIO_*` env vars (from core/config.py)
- Buckets:
  - `loan-documents` - Loan application documents (KYC, ID, proofs)
  - Bento bundle storage (model serving binaries)
  - MLflow artifacts (model artifacts, logs)
- Client: Minio SDK (Python) in `application/entrypoints/api/main.py` for document upload/download
- Presigned URLs: 60-minute expiry (configurable via `APP_MINIO_PRESIGNED_EXPIRY_MINUTES`)

## Authentication & Identity

**Auth Provider:**
- Type: Custom (none detected)
- Current approach: API calls are open (CORS configured for localhost:3000, localhost:8080)
- Implementation location: `application/entrypoints/api/main.py` (FastAPI CORS middleware)
- Future: No OAuth/JWT detected; would integrate in middleware if added

**Service-to-Service Auth:**
- Kubernetes DNS: All services resolve via `.svc.cluster.local` (in-cluster only)
- Kafka: No SASL/mTLS (default plaintext in Kubernetes manifests)
- PostgreSQL: Credentials from env vars (OPS_DB_*)
- ClickHouse: User/password from env vars (APP_CLICKHOUSE_*)
- MinIO: Credentials from env vars (MINIO_*, APP_MINIO_*)
- Redis: No authentication (default Redis 7)

## Monitoring & Observability

**Error Tracking:**
- Type: Not detected (no Sentry, DataDog, etc.)
- Fallback: Application logs via loguru with JSON output
- Tracing: OpenTelemetry (OTLP gRPC exporter, 10% sampling)
  - Setup: `application/core/tracing/setup.py`
  - Instrumentation: FastAPI, scoring service, Kafka consumers

**Logs:**
- Approach: Structured JSON logging via loguru
  - Configuration: `APP_LOG_FORMAT=json` (env var in `.env.example`)
  - Log level: `APP_LOG_LEVEL=INFO` (default)
- Storage: Kubernetes logs → ECK (Elasticsearch + Kibana)
  - Manifests: `platform/ops/k8s/` (ECK operator, Elasticsearch, Kibana)
- Consumption: `kubectl logs` for container logs, Kibana dashboard for aggregated search

**Metrics & Monitoring:**
- Prometheus: Scrapes metrics endpoints
  - Deployment: `platform/ops/k8s/prometheus-deployment.yaml`
  - Targets: API service `/metrics`, Kafka broker, Flink TaskManager
- Grafana: Visualization and alerting
  - Deployment: `platform/ops/k8s/grafana-deployment.yaml`
  - Dashboards: Loan application flow, model performance, system resources
- Application instrumentation: OpenTelemetry (traces), Prometheus client (metrics, future)

## CI/CD & Deployment

**Hosting:**
- Platform: Kubernetes 1.28+ (Minikube for local, managed K8s for production)
- Namespace isolation: 8 namespaces (api-gateway, data-services, feature-registry, kserve, model-registry, model-serving, training-data, ops-*)
- Container runtime: Docker (built into Minikube)
- Image registry: Minikube Docker daemon (local dev), ECR/DockerHub (production)

**CI Pipeline:**
- Service: GitHub Actions
- Config: `.github/workflows/test.yml`
- Gates: 6 mandatory coverage thresholds
  - domain: 90%
  - schemas: 90%
  - scoring: 60%
  - infra adapters: 80%
  - consumers: 45%
  - integration: 60%
- No automated deployment detected; manual `make` targets

**Local Development:**
- Orchestration: GNU Makefile
- Commands:
  - `make k8s-up` - Start Minikube (mlops profile, 20 CPU, 24GB RAM)
  - `make k8s-core` - Deploy API, PostgreSQL, Kafka, ClickHouse, MinIO
  - `make build-api` - Build application image (into Minikube Docker)
  - `make pf-*` - Port-forward targets (ClickHouse, MLflow, Kafka UI, PostgreSQL)
- Testing: `pytest tests/` (unit + integration, 194 tests)

## Environment Configuration

**Required env vars (from `.env.example`):**
- **PostgreSQL:** OPS_DB_HOST, OPS_DB_PORT, OPS_DB_USER, OPS_DB_PASSWORD, OPS_DB_NAME
- **ClickHouse:** APP_CLICKHOUSE_HOST, APP_CLICKHOUSE_PORT, APP_CLICKHOUSE_USER, APP_CLICKHOUSE_PASSWORD
- **Kafka:** APP_KAFKA_BOOTSTRAP_SERVERS
- **MinIO:** MINIO_ENDPOINT, APP_MINIO_ACCESS_KEY, APP_MINIO_SECRET_KEY, APP_MINIO_BUCKET
- **MLflow:** MLFLOW_TRACKING_URI, MLFLOW_S3_ENDPOINT_URL, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
- **Scoring:** SCORING_MODEL_SOURCE, SCORING_MLFLOW_MODEL_URI, SCORING_PREDICTION_THRESHOLD, SCORING_FEAST_*
- **Logging:** APP_DEBUG, APP_LOG_LEVEL, APP_LOG_FORMAT

**Secrets location:**
- Kubernetes: `secret/db-secrets` in data-services namespace (referenced in CDC, database deployments)
- Local dev: `.env` file (not committed, use `.env.example` as template)
- Git ignore: `.env*` patterns prevent accidental secret commits

## Webhooks & Callbacks

**Incoming (Knative Event Sourcing):**
- Kafka topic `hc.feature_ready`: Knative EventSource polls this topic
  - Trigger: When all 3 feature sources ready for a customer
  - Handler: Knative Sequence routes to `/v1/score-by-id` on KServe InferenceService
  - No HTTP webhooks; event-driven via Kafka + Knative Eventing

**Outgoing (Results Propagation):**
- Kafka topic `hc.scoring`: KServe inference results published here
  - Payload: {sk_id_curr, probability, decision, threshold, model_name, version, timestamp}
  - Sink: KafkaSink in kserve namespace (Knative integration)
- Kafka topic `hc.scoring.dlq`: Failed predictions (dead letter queue)

## Kafka Topics (Event Streaming)

| Topic | Producer | Consumer | Payload Schema |
|-------|----------|----------|--------|
| `hc.applications.public.loan_applications` | Debezium CDC (pgoutput plugin) | Flink CDC ETL, Bureau Consumer, Feature Consumer | Debezium envelope (after/before/op/ts) with full LoanApplication record |
| `hc.application_features` | Flink CDC ETL job | Feast Stream Processor | 40+ application features (amounts, dates, flags) keyed by sk_id_curr |
| `hc.application_ext_raw` | Bureau Consumer | Flink Bureau Aggregation ETL | Raw bureau arrays, external source scores |
| `hc.application_ext` | Flink Bureau Aggregation ETL | Feast Stream Processor | 60+ aggregated bureau features (counts, ratios, DPD) keyed by sk_id_curr |
| `hc.application_dwh` | Feature Consumer | Feast Stream Processor | DWH mart features (previous apps, POS, credit card flattened) |
| `hc.feature_ready` | Feast Stream Processor | Knative EventSource → scoring-pipeline Sequence | Signal: {sk_id_curr, ts} - all 3 sources materialized |
| `hc.scoring` | KServe via KafkaSink | API, monitoring, downstream systems | Prediction: {sk_id_curr, probability, decision, threshold, model_name, version, ts} |
| `hc.scoring.dlq` | KServe (failed predictions) | — | Error details + original request |

**Kafka Broker:**
- Provider: Confluent 7.7.1
- Mode: KRaft (no ZooKeeper)
- Host: `kafka-broker.data-services.svc.cluster.local:9092` (K8s), localhost:9092 (local dev)
- Schema Registry: Confluent Schema Registry on port 8081 (for Avro/Protobuf schemas)
- Replication: 1 (local dev), configurable for production
- Partitions: Not specified in manifests; defaults apply

## Kubernetes Services (Cross-Service DNS)

| Service | Namespace | Port | Protocol | Purpose |
|---------|-----------|------|----------|---------|
| `ops-postgres` | data-services | 5432 | TCP | Operational database |
| `ops-pgbouncer` | data-services | 6432 | TCP | Connection pooling proxy |
| `kafka-broker` | data-services | 9092 | TCP | Kafka broker |
| `schema-registry` | data-services | 8081 | HTTP | Kafka schema management |
| `clickhouse-server` | data-services | 8123/9000 | HTTP/Native | Data warehouse |
| `debezium-connect` | data-services | 8083 | HTTP | CDC connector management |
| `flink-jobmanager` | data-services | 6123/8081 | TCP/HTTP | Stream processing coordinator |
| `flink-taskmanager` | data-services | — | — | 4 task slots for ETL jobs |
| `bureau-consumer` | data-services | — | — | Python app (4 replicas) |
| `feature-consumer` | data-services | — | — | Python app (4 replicas) |
| `feast-redis` | feature-registry | 6379 | TCP | Feast online feature store |
| `feast-stream` | feature-registry | — | — | Python app (4 replicas) |
| `credit-risk-v3` | kserve | 3000 | HTTP | ML inference (serverless) |
| `api-service` | api-gateway | 8000 | HTTP | Loan application API |
| `frontend` | api-gateway | 8501 | HTTP | Streamlit dashboard |
| `mlflow` | model-registry | 5000 | HTTP | Model registry UI/API |
| `serving-minio` | model-serving | 9000 | HTTP | Object storage (Bento + Feast) |

## Feature Store Configuration (Feast)

**Project:** hc

**Entity:** customer (join_key: sk_id_curr)

**Feature Views:**
- `fv_application_features` (TTL: 1 day) - 40+ application-level features from Flink CDC ETL
- `fv_external` (TTL: 7 days) - 60+ bureau aggregated features from bureau ETL
- `fv_dwh` (TTL: 7 days) - Previous apps, POS, credit card features from DWH consumer

**Feature Service:** realtime_scoring_v1 (combines all 3 views for scoring)

**Online Store:** Redis
- Connection: `redis://feast-redis.feature-registry.svc.cluster.local:6379/0` (K8s)
- DB 0: Feature values
- DB 1: Coordination (Lua script for 3/3 source tracking)

**Registry:** S3 (MinIO)
- Path: `s3://feast-registry/feature_repo/registry.db`
- Format: SQLite database serialized to S3

**Stream Processor:**
- Code: `application/feast_repo/stream_processor.py`
- Batching: 200 records or 300ms timeout
- Input topics: `hc.application_features`, `hc.application_ext`, `hc.application_dwh`
- Output topics: `hc.feature_ready` (when all 3 sources ready)
- Coordination: Redis Lua script (DB 1) tracks readiness per sk_id_curr

---

*Integration audit: 2026-04-15*
