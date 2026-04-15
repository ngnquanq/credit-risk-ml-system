# Codebase Structure

**Analysis Date:** 2026-04-15

## Directory Layout

```
home-credit-credit-risk-model-stability/
├── application/                     # Main application code (Clean Architecture)
│   ├── core/                        # Configuration, database, tracing
│   ├── domain/                      # Pure business logic, domain entities
│   ├── workflows/                   # Use case orchestration
│   ├── infrastructure/              # Adapters for external systems
│   ├── entrypoints/                 # API, Kafka consumers, external triggers
│   ├── feast_repo/                  # Feast feature store definitions
│   ├── flink/                       # PyFlink CDC and aggregation ETL jobs
│   ├── scoring/                     # BentoML scoring service
│   ├── training/                    # XGBoost training + MLflow registration
│   ├── frontend/                    # Streamlit dashboard
│   ├── run.py                       # FastAPI uvicorn entry point
│   └── __init__.py
├── platform/                        # Infrastructure-as-Code (Kubernetes)
│   ├── core/k8s/                    # API, PostgreSQL, PgBouncer, Ingress
│   ├── data/k8s/                    # Kafka, ClickHouse, Flink, Debezium, MinIO
│   ├── ml/k8s/                      # KServe, Knative, Feast, MLflow, BentoML
│   └── ops/k8s/                     # Prometheus, Grafana, ECK, monitoring
├── ml_data_mart/                    # dbt data warehouse project (ClickHouse)
│   ├── models/
│   │   ├── staging/                 # Raw source transformations
│   │   ├── warehouse/               # Normalized dimension/fact tables
│   │   └── mart/                    # Business-ready aggregates
│   ├── macros/                      # dbt custom macros
│   ├── tests/                       # dbt model tests
│   ├── seeds/                       # Static data loads
│   ├── snapshots/                   # SCD (Slowly Changing Dimensions)
│   ├── dbt_project.yml              # dbt configuration
│   └── dbt_packages/                # Dependencies
├── notebook/                        # Jupyter notebooks (EDA, modeling)
│   ├── 01_baseline_modeling.ipynb
│   ├── 02_aggregated_modeling.ipynb
│   ├── 03_full_feature_modeling.ipynb
│   ├── 04-07_eda_*.ipynb            # Exploratory analysis by table
│   ├── feature_elimination_analysis.py
│   └── model_evaluation.ipynb
├── tests/                           # Automated tests
│   ├── unit/                        # Unit tests (domain, schemas, infrastructure)
│   │   ├── domain/
│   │   ├── workflows/
│   │   ├── infrastructure/
│   │   ├── schemas/
│   │   ├── scoring/
│   │   ├── consumers/
│   │   └── conftest.py              # Unit test fixtures + patches
│   ├── integration/                 # Integration tests (API, repository)
│   │   ├── api/
│   │   └── repository/
│   ├── test_load/                   # Load/performance tests (Locust)
│   │   ├── locustfile.py
│   │   ├── locustfile_e2e_prediction.py
│   │   └── reports/
│   ├── conftest.py                  # Root test session config
│   └── README.md
├── data/                            # Raw datasets
│   └── *.csv                        # Training data, reference tables
├── docs/                            # Documentation
│   ├── adr/                         # Architecture Decision Records
│   │   ├── 0001-*.md                # ADRs for each major decision
│   │   └── README.md
│   ├── architecture/
│   │   ├── system-overview.md
│   │   └── model-bundling-pipeline.md
│   └── README.md
├── infrastructure/                  # Terraform + Jenkins
│   ├── terraform/                   # Cloud infrastructure setup
│   └── jenkins/                     # CI/CD pipeline definitions
├── .claude/                         # Claude agent configuration
│   ├── commands/                    # Custom GSD commands
│   ├── skills/                      # Agent skills
│   └── get-shit-done/               # GSD workflow templates
├── .planning/                       # GSD codebase analysis output
│   └── codebase/                    # ARCHITECTURE.md, STRUCTURE.md, etc.
├── .github/workflows/               # GitHub Actions CI/CD
│   └── test.yml                     # Test gate pipeline
├── assets/                          # Documentation images
├── Makefile                         # Build + deploy automation
├── requirements.txt                 # Python dependencies
├── bentofile.yaml                   # BentoML build config
└── CLAUDE.md                        # Project instructions (this file context)
```

## Directory Purposes

**application/**
- Purpose: Main source code following Clean Architecture
- Contains: Domain logic, workflows, adapters, entrypoints, ML services
- Key files: `run.py` (FastAPI entry point)

**application/core/**
- Purpose: Shared configuration and infrastructure setup
- Contains: 
  - `config.py` - Pydantic settings (environment variables)
  - `database.py` - SQLAlchemy async engine, session factory, migrations
  - `tracing/` - OpenTelemetry setup, Kafka context injection
- Key files: `application/core/config.py` (root Settings class)

**application/domain/**
- Purpose: Pure business logic, independent of frameworks
- Contains:
  - `entities/` - Business domain objects (LoanApplication)
  - `interfaces/` - Abstract protocols for repositories and gateways
- Key files:
  - `application/domain/entities/loan_application.py` - Core entity with decision logic
  - `application/domain/interfaces/*.py` - Protocol ABCs

**application/workflows/**
- Purpose: Use case orchestration, glue between domain and adapters
- Contains: Application-specific processes and DTOs
- Key files:
  - `application/workflows/submit_loan.py` - Main workflow implementation
  - `application/workflows/dtos.py` - Input/output data transfer objects

**application/infrastructure/**
- Purpose: External system adapters implementing domain interfaces
- Subdivisions:
  - `persistence/` - Database adapters and models
    - `postgres_loan_repo.py` - LoanRepository implementation
    - `models/` - SQLAlchemy + Pydantic schema definitions
  - `external/` - Third-party service clients
    - `bureau_adapter.py`, `bureau_client.py` - ClickHouse bureau queries
    - `dwh_adapter.py`, `dwh_client_ch.py` - ClickHouse mart queries
    - `kafka_scoring.py` - Kafka event publisher

**application/entrypoints/**
- Purpose: External triggers (API, Kafka consumers)
- Contains:
  - `api/main.py` - FastAPI application definition
  - `api/dependencies.py` - Dependency injection setup
  - `bureau_consumer.py` - Kafka consumer for bureau data
  - `feature_consumer.py` - Kafka consumer for DWH features
- Key files: `application/entrypoints/api/main.py` (REST API routes)

**application/feast_repo/**
- Purpose: Feast feature store definition and stream processing
- Contains:
  - `feature_views.py` - Feature view definitions (application, external, dwh)
  - `feature_services.py` - Feature service combining multiple views
  - `entities.py` - Feast entity definition
  - `stream_processor.py` - Kafka consumer → Feast materialization to Redis
  - `schema_loaders.py` - Dynamic schema loading from JSON
  - `feature_schema/` - JSON schema definitions (application_schema.json, etc.)
  - `feature_store.yaml` - Feast configuration (online/offline stores, registry)

**application/flink/jobs/**
- Purpose: PyFlink streaming ETL jobs
- Contains:
  - `cdc_application_etl.py` - Debezium CDC → application features
  - `cdc_udfs.py` - User-defined functions (decimal parsing, date math)
  - `bureau_aggregation_etl.py` - Bureau aggregation ETL
  - `bureau_aggregation_udfs.py` - Bureau aggregation UDFs
- Key files: `application/flink/jobs/cdc_application_etl.py` (main CDC job)

**application/scoring/**
- Purpose: BentoML serving service for ML inference
- Contains:
  - `service.py` - BentoML endpoints (/v1/score, /v1/score-by-id)
  - `pipeline.py` - Feature vector construction, postprocessing
  - `model_registry.py` - MLflow model loading
  - `schemas.py` - Request/response Pydantic models
  - `config.py` - Scoring service configuration
- Deployment: KServe InferenceService

**application/training/**
- Purpose: Model training and MLflow registration
- Contains:
  - `train_register.py` - Main training + registration pipeline
  - `train_clickhouse.py` - ClickHouse data loading for training
  - `train_spark_clickhouse.py` - Spark-based training variant
- Invocation: Manual or scheduled (no built-in scheduler shown)

**application/frontend/**
- Purpose: Streamlit dashboard for monitoring and manual testing
- Contains:
  - `frontend.py` - Main dashboard app
  - `utils.py` - Helper functions
  - `config.py` - Frontend configuration
- Deployment: Kubernetes pod (port 8501)

**platform/core/k8s/**
- Purpose: Kubernetes manifests for API layer
- Contains:
  - `01-api-config.yaml` - ConfigMap for API settings
  - `02-api-secrets.yaml` - Secret (credentials)
  - `05-api.yaml` - FastAPI Deployment
  - `06-ingress.yaml` - NGINX Ingress
  - `07-frontend.yaml` - Streamlit Deployment
  - `operational-db/` - PostgreSQL StatefulSet, PgBouncer
  - `cdc/` - Debezium connector configuration

**platform/data/k8s/**
- Purpose: Kubernetes manifests for data platform
- Contains:
  - `message-broker/` - Kafka broker and schema registry
  - `data-warehouse/` - ClickHouse cluster
  - `stream-processing/` - Flink JobManager + TaskManager
  - `object-storage/` - MinIO for Bento bundles and Feast registry

**platform/ml/k8s/**
- Purpose: Kubernetes manifests for ML platform
- Contains:
  - `feature-store/` - Feast deployment, Redis online store
  - `model-registry/` - MLflow + PostgreSQL backend
  - `model-serving/` - BentoML bundle storage, serving watcher
  - `kserve/` - KServe InferenceService, Knative Sequence

**platform/ops/k8s/**
- Purpose: Observability and operations
- Contains:
  - `monitoring/` - Prometheus scrape configs, Grafana dashboards
  - `logging/` - ECK (Elasticsearch + Kibana) stack
  - `automation/` - Jenkins CI/CD

**ml_data_mart/**
- Purpose: dbt data transformation project (ClickHouse data warehouse)
- Contains:
  - `models/` - dbt models
    - `staging/` - Raw source tables, basic cleaning
    - `warehouse/` - Normalized dimension/fact schemas
    - `mart/` - Business-ready aggregates (mart_previous_application, mart_pos_cash_balance, mart_credit_card_balance)
  - `macros/` - Custom dbt macros
  - `tests/` - dbt test suite (uniqueness, not-null, referential integrity)
  - `seeds/` - Static seed data
  - `dbt_project.yml` - dbt project configuration

**notebook/**
- Purpose: Jupyter notebooks for exploration, modeling, evaluation
- Contains:
  - `01_baseline_modeling.ipynb` - Baseline model with limited features
  - `02_aggregated_modeling.ipynb` - With bureau aggregations
  - `03_full_feature_modeling.ipynb` - Final model (24 features, AUC ~0.77)
  - `04-07_eda_*.ipynb` - Exploratory data analysis per table
  - `feature_elimination_analysis.py` - Feature importance analysis
  - `model_evaluation.ipynb` - Model evaluation metrics

**tests/unit/**
- Purpose: Unit tests (no external I/O)
- Contains:
  - `domain/test_*.py` - Domain entity tests
  - `workflows/test_*.py` - Workflow orchestration tests
  - `infrastructure/test_*.py` - Adapter unit tests
  - `schemas/test_*.py` - Pydantic schema validation tests
  - `scoring/test_*.py` - Scoring pipeline tests
  - `consumers/test_*.py` - Consumer message processing tests
  - `conftest.py` - Fixtures, mocks, patches

**tests/integration/**
- Purpose: Integration tests with real components (DB, Kafka mocks)
- Contains:
  - `api/test_*.py` - API endpoint tests with test database
  - `repository/test_*.py` - Repository persistence tests

**tests/test_load/**
- Purpose: Load and performance testing
- Contains:
  - `locustfile.py` - Locust load test (HTTP endpoints)
  - `locustfile_e2e_prediction.py` - E2E prediction flow (insert → CDC → scoring)
  - `reports/` - Load test results

**docs/adr/**
- Purpose: Architecture Decision Records
- Contains: Numbered decision documents for major components
  - 0001: ClickHouse as data warehouse
  - 0002: Event-driven architecture with Kafka
  - 0003: Feast as feature store
  - 0004: KServe + BentoML for model serving
  - 0005: Migration to Kubernetes
  - 0006: Clean Architecture for application layer
  - 0007: Flink for stream processing

## Key File Locations

**Entry Points:**
- `application/run.py` - FastAPI uvicorn launcher
- `application/entrypoints/api/main.py` - FastAPI app definition, routes
- `application/entrypoints/bureau_consumer.py` - Bureau data consumer
- `application/entrypoints/feature_consumer.py` - DWH features consumer

**Configuration:**
- `application/core/config.py` - Pydantic settings, environment variables
- `platform/core/k8s/01-api-config.yaml` - K8s ConfigMap
- `.env.example` - Environment variable template

**Core Logic:**
- `application/domain/entities/loan_application.py` - Business entity, decision logic
- `application/workflows/submit_loan.py` - Loan submission workflow
- `application/feast_repo/stream_processor.py` - Feature materialization

**Database:**
- `application/core/database.py` - SQLAlchemy async setup
- `application/infrastructure/persistence/models/sqlalchemy_models.py` - ORM schema
- `application/infrastructure/persistence/postgres_loan_repo.py` - Repository adapter

**Features:**
- `application/feast_repo/feature_views.py` - Feast feature definitions
- `application/feast_repo/feature_store.yaml` - Feast configuration
- `application/feast_repo/feature_schema/` - Schema JSON files

**ML Scoring:**
- `application/scoring/service.py` - BentoML scoring service
- `application/scoring/pipeline.py` - Feature mapping, postprocessing
- `application/training/train_register.py` - Training + MLflow registration

**Testing:**
- `tests/conftest.py` - Root session config (environment patches)
- `tests/unit/conftest.py` - Unit test fixtures
- `tests/unit/domain/test_loan_application.py` - Domain tests
- `tests/unit/workflows/test_submit_loan.py` - Workflow tests

**Data Transformation:**
- `ml_data_mart/dbt_project.yml` - dbt configuration
- `ml_data_mart/models/mart/` - Business-ready tables

## Naming Conventions

**Files:**
- Python modules: `snake_case.py` (e.g., `loan_application.py`)
- Jupyter notebooks: `##_description.ipynb` (e.g., `01_baseline_modeling.ipynb`)
- Kubernetes manifests: `##-component-name.yaml` (e.g., `05-api.yaml`)
- dbt models: `snake_case.sql` (e.g., `mart_previous_application.sql`)

**Directories:**
- Package directories: `lowercase` (e.g., `domain/`, `workflows/`)
- Feature-area directories: `lowercase` (e.g., `infrastructure/`, `entrypoints/`)
- dbt model subdirs: `staging/`, `warehouse/`, `mart/`

**Python Classes:**
- Domain entities: `PascalCase` (e.g., `LoanApplication`)
- Workflows: `PascalCase` + "Workflow" suffix (e.g., `SubmitLoanWorkflow`)
- Adapters: `PascalCase` + "Adapter" suffix (e.g., `BureauAdapter`)
- Repositories: `PascalCase` + "Repository" suffix (e.g., `PostgresLoanRepository`)
- Services: `PascalCase` + "Service" suffix (e.g., `ExternalBureauService`)

**Python Functions:**
- Regular functions: `snake_case` (e.g., `fetch_bureau_by_loan_id`)
- UDFs (Flink): `snake_case` (e.g., `decode_decimal_base64`)
- Data transformation: `snake_case` (e.g., `postprocess`)

**Variables:**
- Constants: `UPPER_SNAKE_CASE` (e.g., `BATCH_SIZE`)
- Instance variables: `snake_case` (e.g., `self.bootstrap_servers`)
- Kafka topics: `lowercase.with.dots` (e.g., `hc.applications.public.loan_applications`)

## Where to Add New Code

**New Feature (end-to-end workflow):**
- Primary code: `application/workflows/` - orchestration, DTOs
- Domain logic: `application/domain/entities/` or interfaces
- API endpoint: `application/entrypoints/api/main.py`
- Tests: `tests/unit/workflows/test_new_workflow.py`

**New Component/Module:**
- Implementation: `application/{module}/` (create new subdirectory if major area)
- Interfaces: `application/domain/interfaces/` (if public contract)
- Adapters: `application/infrastructure/{category}/` (if external integration)
- Tests: `tests/unit/{category}/test_new_module.py`

**Utilities/Helpers:**
- Shared helpers: `application/core/` (if cross-cutting) or `{module}/` (if domain-specific)
- Transformation logic: `application/flink/jobs/` (for streaming) or `ml_data_mart/macros/` (for dbt)

**New Feature (ML features):**
- Feast definitions: `application/feast_repo/feature_views.py`
- Feature schema: `application/feast_repo/feature_schema/new_features.json`
- dbt transformations: `ml_data_mart/models/{staging|warehouse|mart}/`
- Tests: `ml_data_mart/tests/test_new_feature.yml`

**New Kafka Topic:**
- Consumer: `application/entrypoints/new_consumer.py`
- Producer: Add to infrastructure gateway (e.g., `infrastructure/external/kafka_*.py`)
- Topic definition: Platform K8s manifest or Kafka topics script

**Tests:**
- Unit tests: `tests/unit/{module}/test_name.py`
- Integration tests: `tests/integration/{category}/test_name.py`
- Load tests: `tests/test_load/locustfile_*.py`

## Special Directories

**application/core/tracing/**
- Purpose: OpenTelemetry distributed tracing
- Generated: No (source code)
- Committed: Yes
- Contents: OTLP exporter setup, context propagation helpers

**platform/data/.volumes/**
- Purpose: Docker volume persistence (local dev)
- Generated: Dynamically created during `make k8s-up`
- Committed: No (.gitignore)
- Contains: PostgreSQL data, Kafka logs, ClickHouse data

**ml_data_mart/target/**
- Purpose: dbt compilation output
- Generated: Yes (`dbt run` creates)
- Committed: No (.gitignore)
- Contains: Compiled SQL, run results

**ml_data_mart/dbt_packages/**
- Purpose: dbt dependencies
- Generated: Yes (`dbt deps` creates)
- Committed: No (.gitignore)
- Contains: Community packages (e.g., dbt-utils)

**.planning/codebase/**
- Purpose: GSD codebase analysis documents
- Generated: Yes (gsd:map-codebase creates)
- Committed: Yes
- Contains: ARCHITECTURE.md, STRUCTURE.md, STACK.md, TESTING.md, CONVENTIONS.md, CONCERNS.md

**.pytest_cache/**
- Purpose: pytest cache
- Generated: Yes
- Committed: No (.gitignore)

---

*Structure analysis: 2026-04-15*
