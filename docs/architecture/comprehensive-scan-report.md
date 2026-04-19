# Comprehensive Architectural Scan Report

**Date of Scan:** 2026-04-19
**Target Repository:** Credit Risk Model Stability
**Repository Purpose:** End-to-end credit risk decisioning platform using ML for real-time/near real-time scoring.

This report is generated from a comprehensive repository scan to summarize the current architecture, directory structure, data flows, and infrastructure configurations supporting the platform.

---

## 1. Executive Summary

The project implements a highly scalable, event-driven Machine Learning platform specifically built for real-time/near real-time credit risk assessment. It follows a Clean Architecture design pattern in its application layer, backed by robust Streaming and MLOps tooling orchestrating models through a Kubernetes-native data ecosystem. 

**Key Characteristics:**
- **App Architecture:** Clean Architecture (Domain -> Application Workflows -> Infrastructure / Adapters).
- **Processing Paradigm:** Event-driven microservices architecture driven by Apache Kafka and Debezium CDC.
- **Data Warehousing & Features:** ClickHouse for DWH/analytical workloads, managed via dbt. Redis serves as the low-latency online Feature Store, with materializations handled by Feast and Flink.
- **ML Lifecycle & Serving:** Managed with Kubeflow/Ray (Training), MLflow (Registry), BentoML (Bundling), and KServe via Knative (Model Serving).
- **Observability:** Robust monitoring using the Prometheus/Grafana stack and full logging via ECK (Elasticsearch, Kibana, Filebeat).

---

## 2. Directory & Structure Breakdown

The codebase strictly segments infrastructure-as-code (IaC) and application code into specialized directories:

### A. Application Layer (`application/`)
Follows SOLID and Clean Architecture principles to decouple the domain problem from external mechanisms (frameworks, DBs, ML servers).
- **`domain/`**: The core. Contains python domain model concepts (e.g., `LoanApplication` entity), value objects, and abstraction interfaces without external dependencies.
- **`workflows/`**: Handles the application logic/use case orchestration (e.g., retrieving app statuses, firing events, gathering data). Interacts directly with domain entities.
- **`infrastructure/`**: Adapters to the outside world. It contains `external` code for dealing with API integrations, and `persistence` (SQLAlchemy/Postgres, ClickHouse queries).
- **`entrypoints/`**: The presentation/trigger mechanisms. Specifically, the FastAPI structure and Kafka consumers processing streams are housed here.
- **`feast_repo/`**: Feast syntax models to define features for online (Redis) and offline (ClickHouse) syncing.
- **`flink/`**: PyFlink streaming application jobs to manage transformations (e.g., computing aggregated Bureau records or doing CDC merges on the fly).
- **`scoring/` & `training/`**: Logic regarding ML specific implementations (XGBoost logic, MLflow registry wrappers, and Bento service runnables).

### B. Platform Layer (`platform/`)
Contains all infrastructure definitions, scripts, and Kubernetes manifests (split contextually).
- **`core/`**: Foundations (Namespaces, PostgreSQL, PgBouncer pooling, NGINX Ingress, API Gateway structures).
- **`data/`**: Data mesh and streaming backbone structures (Kafka operators, Schema Registry, ClickHouse operators, Flink clusters, Debezium connect).
- **`ml/`**: Machine Learning operation platforms (KServe deployments, MLflow helm/manifests, Feast registry endpoints, Ray Clusters, Kubeflow pipelines).
- **`ops/`**: Observability, including the Prometheus-Grafana stack and the Elastic-Cloud-on-Kubernetes (ECK) components.

### C. Data Definitions (`ml_data_mart/`)
DWH orchestration utilizing **dbt**.
- Contains models (staging, mart, warehouse) for ELT processing natively within the ClickHouse nodes.

### D. Testing & Development (`tests/` & `notebook/`)
- Contains extensive integration, unit testing, and load testing (via `locust`) validating layers natively without demanding K8s.
- `notebook/` contains raw EDA, prototyping, and evaluation matrices.

---

## 3. The Data & Execution Flow

### Data Acquisition to ML Serving Lifecycle

1. **Intake & Transact:** A loan application starts via a REST request to the FastAPI application (`application.entrypoints.api`). It is stored relationally inside **PostgreSQL**.
2. **Change Data Capture (CDC):** **Debezium** attaches to the PostgreSQL Write-Ahead Log (WAL), capturing the new database transactions and emitting schemas safely into localized **Kafka** topics.
3. **Data Streaming & Processing:** Data is actively grabbed by **Flink** application flows from Kafka. Flink calculates rolling windows and consumer traits (bureau aggregation features).
4. **Data Materialization:** Computed features are pushed continuously downstream. **Feast** consumes these computed states to push immediate state feature vectors to **Redis** (Used for Sub-ms Online feature access) while syncing bulk histories to **ClickHouse** (Offline analytical queries / training).
5. **Real-time Scoring:** Upon recognizing feature readiness via a specialized topic (`hc.feature_ready`), a **Knative Sequence** initiates a RESTful/RPC query against **KServe** inferences (using bundled BentoML models).
6. **Decision & Feedback:** The evaluated score is fired back to the application messaging queue (Kafka -> API Workflow) for approval/rejection determination.

---

## 4. Assessment & Areas of Note

1. **High Code Cohesion:** The migration to pure Clean Architecture isolating `domain` layer from FastAPI/ML nuances sets a tremendous foundation for testing without depending upon massive K8s resources, evidenced by `tests/integration` mapping out to SQLite.
2. **Infrastructure Modularity:** The `Makefile` exposes decoupled phases perfectly (`make k8s-core`, `make k8s-streaming`, `make k8s-mlflow-watcher`).
3. **Handling The "Thundering Herd":** As documented in iterations, the transition from continuous Feast polling over to a Kafka Event-Driven pattern (`hc.feature_ready`) to trigger scoring vastly improves platform resiliency and negates the IO blockages on Redis.
4. **Adherence to Code Rules:** Code styles generally seem to uphold required rule principles set forth in `AGENT.md` guidelines, particularly regarding type-hinting protocols and keeping operations Pythonic (Pep8) while using Clean Architecture.

This structure allows the team to isolate ML scaling separately from domain logic operations, allowing domain engineers to develop safely offline via Docker/SQLite while MLOps engineers leverage the comprehensive minikube suite for Ray/Kubeflow orchestration.
