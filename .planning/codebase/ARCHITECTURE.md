# Architecture

**Analysis Date:** 2026-04-15

## Pattern Overview

**Overall:** Event-driven microservices with Clean Architecture application layer. Multi-stage ML pipeline with real-time feature streaming.

**Key Characteristics:**
- Clean Architecture separation: `domain/` (pure logic) → `workflows/` (orchestration) → `infrastructure/` (adapters)
- Kafka-based event streaming: CDC captures → Flink processing → Feast materialization → KServe scoring
- Three parallel feature computation streams converging at Feast coordination point
- Async/await throughout with structured dependency injection

## Layers

**Domain Layer:**
- Purpose: Pure business logic, independent of frameworks
- Location: `application/domain/`
- Contains: 
  - `entities/loan_application.py` - Core entity with decision logic (`evaluate_worthiness()`)
  - `interfaces/*.py` - Abstract protocols: `LoanRepository`, `BureauGateway`, `DwhGateway`, `ScoringGateway`
- Depends on: Nothing (stdlib only)
- Used by: Workflows, infrastructure adapters

**Application/Workflow Layer:**
- Purpose: Use case orchestration - defines how business processes execute
- Location: `application/workflows/`
- Contains:
  - `submit_loan.py` - `SubmitLoanWorkflow` - orchestrates loan submission: create entity → persist → publish for scoring
  - `dtos.py` - Data Transfer Objects (`SubmitLoanInput`, `SubmitLoanOutput`)
- Depends on: `domain/` + interfaces
- Used by: API entrypoints

**Infrastructure/Adapter Layer:**
- Purpose: Implement domain interfaces, connect to external systems
- Location: `application/infrastructure/`
- Subdivisions:
  - `persistence/` - Database adapters
    - `postgres_loan_repo.py` - Repository implementation using SQLAlchemy
    - `models/` - SQLAlchemy ORM + Pydantic schemas
  - `external/` - Third-party service adapters
    - `bureau_adapter.py`, `bureau_client.py` - ClickHouse bureau queries
    - `dwh_adapter.py`, `dwh_client_ch.py` - ClickHouse DWH queries
    - `kafka_scoring.py` - Kafka event publisher

**Entrypoints/Driving Adapters:**
- Purpose: External triggers that invoke the application
- Location: `application/entrypoints/`
- Contains:
  - `api/main.py` - FastAPI REST endpoint (`POST /api/v1/applications`)
  - `bureau_consumer.py` - Kafka consumer (CDC topic → ClickHouse → raw bureau topic)
  - `feature_consumer.py` - Kafka consumer (CDC topic → ClickHouse → DWH topic)
- Depends on: Workflows, infrastructure
- Invokes: Domain via workflows

**Core/Shared Kernel:**
- Purpose: Configuration, database setup, tracing
- Location: `application/core/`
- Contains:
  - `config.py` - Pydantic settings (env vars, connection strings)
  - `database.py` - SQLAlchemy async engine + session setup
  - `tracing/` - OpenTelemetry setup, Kafka context propagation

**Feature Store (Feast):**
- Location: `application/feast_repo/`
- Purpose: Feature definitions, online/offline store configuration, materialization coordination
- Defines: `fv_application_features`, `fv_external`, `fv_dwh` (100+ features total)
- Online store: Redis DB 0 (Feast), DB 1 (coordination Lua script)
- Registry: MinIO S3 bucket

**Stream Processing (Flink):**
- Location: `application/flink/jobs/`
- Jobs:
  - `cdc_application_etl.py` - Consumes Debezium CDC, transforms to 40+ features
  - `bureau_aggregation_etl.py` - Aggregates bureau raw data to 60+ features
- UDFs: Custom functions for decimal parsing, date arithmetic, flag generation

**ML Services:**
- Scoring: `application/scoring/` - BentoML service with `/v1/score` and `/v1/score-by-id` endpoints
- Training: `application/training/` - XGBoost training pipeline, MLflow registration
- Frontend: `application/frontend/` - Streamlit dashboard

**Data Transformation (dbt):**
- Location: `ml_data_mart/` - dbt project (ClickHouse targets)
- Models: `staging/`, `warehouse/`, `mart/` - ETL staging → normalized → mart tables

## Data Flow

**Complete End-to-End:**

1. **Submission**
   - `POST /api/v1/applications` → `SubmitLoanWorkflow.execute()`
   - Domain entity created, saved to PostgreSQL, status=SUBMITTED
   - Workflow publishes sk_id_curr to Kafka (triggering CDC capture)

2. **CDC Capture**
   - PostgreSQL WAL (pgoutput) → Debezium → Kafka topic: `hc.applications.public.loan_applications`
   - Full Debezium envelope per record

3. **Three Parallel Feature Streams** (all consume CDC topic simultaneously)

   **Stream A — Application Features:**
   - Flink job `cdc_application_etl.py`:
     - Decodes Debezium base64 decimals via `decode_decimal_base64()` UDF
     - Calculates days_birth, days_employed via date math UDFs
     - Generates document flags (document_id_X → flag_document_X)
     - Output: 40+ numeric/categorical features to Kafka: `hc.application_features` (keyed by sk_id_curr)

   **Stream B — Bureau Features (two-stage):**
   - Bureau Consumer `bureau_consumer.py`:
     - Extracts sk_id_curr from CDC message
     - Async queries ClickHouse: bureau table, bureau_balance, external_scores
     - Publishes raw JSON arrays → Kafka: `hc.application_ext_raw` (keyed by sk_id_curr)
   - Flink job `bureau_aggregation_etl.py`:
     - Consumes raw bureau arrays
     - Aggregates via `aggregate_bureau_features()` UDF:
       - Account counts (BUREAU_TOTAL/ACTIVE/CLOSED/BAD_DEBT_COUNT)
       - Credit utilization (CREDIT_UTILIZATION_RATIO)
       - DPD metrics (OVERDUE_DAYS max/mean, DPD_RATIO)
       - Payment performance (ON_TIME_RATIO)
       - Risk flags
     - Output: 60+ aggregated features → Kafka: `hc.application_ext`

   **Stream C — DWH Features:**
   - Feature Consumer `feature_consumer.py`:
     - Extracts sk_id_curr from CDC message
     - Async queries ClickHouse mart database: mart_previous_application, mart_pos_cash_balance, mart_credit_card_balance
     - Flattens first row of each table (or null if empty)
     - Output: flattened mart features → Kafka: `hc.application_dwh`

4. **Feature Materialization (Feast Stream Processor):**
   - `feast_repo/stream_processor.py` spawns 3 concurrent consumer threads
   - Each thread consumes from its topic (application_features, application_ext, application_dwh)
   - Micro-batches: 200 records or 300ms timeout
   - Per batch: `fs.write_to_online_store()` materializes to Redis DB 0 (Feast standard)
   - **Coordination via Redis DB 1 Lua script:**
     - Tracks when all 3 sources written for a given sk_id_curr
     - When 3/3 ready → publishes `hc.feature_ready` event to Kafka
     - TTL 3600s

5. **ML Scoring (Knative Sequence → KServe):**
   - `hc.feature_ready` event → Knative broker (eventing)
   - Knative Sequence: routes to `credit-risk-v3` InferenceService (KServe)
   - BentoML scoring service `/v1/score-by-id` handler:
     - Fetches 100+ features from Feast Redis (online store, DB 0)
     - Maps Feast feature names (lowercase) → model columns (uppercase) via `feast_metadata.yaml`
     - Runs XGBoost predict_proba
     - Applies business logic: `probability >= threshold` → REJECT, else APPROVE
     - Returns CloudEvent-wrapped response
   - KafkaSink forwards response → Kafka: `hc.scoring`
   - Dead letters on error → Kafka: `hc.scoring.dlq`

**State Transitions:**
- PostgreSQL: SUBMITTED → (async processing) → APPROVED/REJECTED (updated by scoring event)
- Feast coordination: tracks 3-way join readiness per customer

## Key Abstractions

**LoanApplication Entity:**
- Purpose: Core domain model, immutable business logic
- File: `application/domain/entities/loan_application.py`
- Pattern: Pure dataclass with decision logic
- Key method: `evaluate_worthiness(risk_score, threshold) → bool`
- Status enum: SUBMITTED, EVALUATING, APPROVED, REJECTED

**Repository Pattern:**
- Purpose: Abstract persistence, enable swapping implementations
- Interface: `application/domain/interfaces/loan_repository.py` (Protocol ABC)
- Implementation: `application/infrastructure/persistence/postgres_loan_repo.py`
- Usage: Injected into workflows, used in entrypoints

**Gateway Pattern:**
- Purpose: Abstract external service calls
- Interfaces:
  - `BureauGateway` → bureau_adapter.py (queries ClickHouse bureau data)
  - `DwhGateway` → dwh_adapter.py (queries ClickHouse mart tables)
  - `ScoringGateway` → kafka_scoring.py (publishes for async scoring)
- Adapters translate domain requests to infrastructure calls

**Kafka Event Model:**
- Topics are keyed by sk_id_curr (partition key)
- Schemas defined in `application/feast_repo/feature_schema/` (JSON)
- Debezium envelope format: `{ before, after, source, op, ts_ms }`
- Custom headers: trace context (OpenTelemetry propagation)

## Entry Points

**API Endpoint:**
- Location: `application/entrypoints/api/main.py`
- Triggers: `POST /api/v1/applications`
- Responsibilities:
  - Validate input (Pydantic schema)
  - Instantiate dependencies (workflow, repo, gateways)
  - Call `SubmitLoanWorkflow.execute()`
  - Return immediately with SUBMITTED status (async processing)
- Tracing: FastAPI auto-instrumentation, custom trace context

**Bureau Consumer:**
- Location: `application/entrypoints/bureau_consumer.py`
- Triggers: Kafka topic `hc.applications.public.loan_applications` (CDC)
- Responsibilities:
  - Deserialize Debezium message
  - Extract sk_id_curr
  - Async query ClickHouse bureau data
  - Publish to `hc.application_ext_raw`
  - Handle partition assignment, offset management
- Concurrency: 4 instances (Deployment replicas)

**Feature Consumer:**
- Location: `application/entrypoints/feature_consumer.py`
- Triggers: Kafka topic `hc.applications.public.loan_applications` (CDC)
- Responsibilities:
  - Deserialize Debezium message
  - Extract sk_id_curr
  - Query ClickHouse mart tables (first row per table)
  - Flatten and publish to `hc.application_dwh`
- Concurrency: 4 instances

**Feast Stream Processor:**
- Location: `application/feast_repo/stream_processor.py`
- Triggers: Kafka topics (hc.application_features, hc.application_ext, hc.application_dwh)
- Responsibilities:
  - Consume from 3 topics in parallel (threading)
  - Micro-batch and materialize to Redis Feast online store
  - Coordinate 3-way readiness via Redis Lua script
  - Publish `hc.feature_ready` when all 3 sources present
- Concurrency: 4 task threads + producer thread

**Flink CDC ETL:**
- Location: `application/flink/jobs/cdc_application_etl.py`
- Triggers: Kafka CDC topic
- Responsibilities:
  - Decode CDC Debezium format
  - Apply UDFs for decimal parsing, date math, flag generation
  - Produce transformed features to Kafka
- Deployment: Flink JobManager + 1 TaskManager (4 task slots)

**Flink Bureau Aggregation:**
- Location: `application/flink/jobs/bureau_aggregation_etl.py`
- Triggers: Kafka topic `hc.application_ext_raw`
- Responsibilities:
  - Aggregate bureau arrays (counts, ratios, DPD metrics)
  - Produce aggregated features to Kafka
- Deployment: Same Flink cluster

**Scoring Service:**
- Location: `application/scoring/service.py`
- Triggers: Knative Sequence (from `hc.feature_ready` event)
- Responsibilities:
  - Load model from MLflow registry or local joblib
  - Fetch features from Feast online store
  - Apply feature mapping (Feast → model columns)
  - Run XGBoost predict_proba
  - Apply postprocessing (probability → decision)
  - Return CloudEvent response
- Deployment: KServe InferenceService (0-4 autoscaling replicas)

## Error Handling

**Strategy:** Graceful degradation with structured logging and dead letter queues

**Patterns:**

**Kafka Consumers (bureau_consumer, feature_consumer):**
- Wrapped in try/except at message level
- Failed messages logged with context (sk_id_curr, error)
- Offset committed after processing (auto.offset.reset=latest keeps moving forward)
- No DLQ (message drops after log); alternative: publish failed messages to dedicated error topic

**Flink Jobs:**
- UDFs use try/except for data transformations
- `safe_parse_decimal()` returns null on parse failure (Flink SQL propagates nulls downstream)
- Failed records appear as null fields in output, propagate to Kafka
- Kafka sink handles null gracefully (skips or marks missing)

**Feast Stream Processor:**
- Catches exceptions per message: logs and continues
- Redis write failures: retries within batch timeout
- Coordination script failures: skips feature_ready publish (scoring waits for manual intervention or timeout)

**Scoring Service (KServe):**
- Missing features → returns `decision="under-review"` (downstream user action required)
- Model load failure → service startup fails (Kubernetes CrashLoopBackOff until fixed)
- Prediction errors → logged, dead letter to `hc.scoring.dlq` via Knative error handler

**Workflow/API:**
- Input validation via Pydantic (HTTPException 422 if invalid)
- Database save failure → HTTPException 500 with correlation ID for tracing
- Kafka publish failure → HTTPException 503 (dependency unavailable)

**Logging:**
- Structured via `loguru`: JSON output with context (sk_id_curr, trace_id)
- Levels: INFO (state changes), WARNING (retries/degradation), ERROR (failures)
- Centralized via ECK (Elasticsearch + Kibana)

## Cross-Cutting Concerns

**Logging:** 
- Loguru with JSON formatting
- Trace context propagated via OpenTelemetry headers
- Services log: sk_id_curr, action, timestamp, error details

**Validation:**
- Input: Pydantic models (`LoanApplicationCreate`, `DocumentUploadRequest`)
- Business rules: `LoanApplication.evaluate_worthiness()` in domain
- Feature schemas: JSON files (`application_schema.json`, `external_schema.json`, `dwh_schema.json`)

**Authentication:**
- API: Optional (no auth layer shown; can add via FastAPI dependency)
- Internal services: mTLS/service account (K8s network policies)

**Tracing:**
- OpenTelemetry with OTLP exporter (grpc endpoint configurable)
- Sampling: 10% (configurable per service)
- Propagation: W3C Trace Context headers + Kafka headers
- Instrument: FastAPI auto, Kafka via custom headers, SQLAlchemy via ORM tracing

**Configuration:**
- Pydantic BaseSettings: reads from environment + .env file
- Runtime: `application/core/config.py`
- K8s: ConfigMaps (non-secret) + Secrets (credentials)

---

*Architecture analysis: 2026-04-15*
