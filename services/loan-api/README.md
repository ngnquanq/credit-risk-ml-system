# loan-api

The Loan API, the decision recorder and the Kafka consumers. They share the audit, authz, identity, decisions, domain, infrastructure and workflows code, so they are one service built into two images (API; consumers and decision recorder).

- Code: `src/` (import names are unchanged: `domain`, `workflows`, `infrastructure`, `entrypoints`, ...)
- Schema: `schema/` holds the SQL that creates the operational database. It is idempotent, so applying it again is safe. The cluster ConfigMap is generated from it: `python scripts/render_db_init_configmap.py` (a unit test fails if they differ)
- Images: `Dockerfile` (API), `src/entrypoints/Dockerfile` (consumers and decision recorder)
- Deploy: `deploy/` (API, decision recorder, audit verification CronJob)
- Contract it publishes: `contracts/openapi/loan-api.json` (`make contracts`)
- Test: `pytest tests/unit tests/integration`
- Run locally: `make local-ui-up`, then `make local-api`

## 1. Clean Architecture (New Structure)
The goal is to decouple business logic from frameworks.

### `domain/` (The Core)
- **Purpose**: Pure business logic and rules.
- **Dependencies**: None (Standard Library only).
- **Key Files**:
    - `entities/loan_application.py`: The `LoanApplication` entity and its `ApplicationStatus`.
    - `interfaces/`: Protocols/Abstract Base Classes for repositories and gateways.

### `workflows/` (The Orchestration)
- **Purpose**: Application-specific use cases. Defines *how* to execute a business process.
- **Dependencies**: `domain`.
- **Key Files**:
    - `submit_loan.py`: Orchestrates the loan submission process (Input -> Domain -> Persistence -> Kafka).
    - `dtos.py`: Data Transfer Objects for the workflows.

### `infrastructure/` (The Adapters)
- **Purpose**: Implement interfaces defined in `domain`. Talks to the outside world.
- **Dependencies**: `domain`, `workflows`, External Libraries (SQLAlchemy, Kafka, etc.).
- **Key Files**:
    - `persistence/postgres_loan_repo.py`: Saves entities to Postgres.
    - `external/kafka_scoring.py`: Publishes applications to the Kafka event bus.
    - `external/bureau_client.py`: ClickHouse client for bureau lookups (used by the bureau consumer).
    - `external/dwh_client_ch.py`: ClickHouse client for the dbt marts (used by the DWH consumer).

---

### `infrastructure/persistence/models/` (Data Models)
- **Purpose**: Database definitions.
- **Key Files**: `sqlalchemy_models.py`, `pydantic_schemas.py`.

### `entrypoints/` (Driving Adapters)
- **Purpose**: Entry points that trigger the application.
- **Key Files**:
    - `api/`: The REST API (FastAPI).
    - `feature_consumer.py`: Kafka Consumer for DWH.
    - `bureau_consumer.py`: Kafka Consumer for Bureau.

### `core/` (Shared Kernel)
- **Purpose**: Configuration, logging, database connection.

### `feast_repo/` (Feature Store)
- **Purpose**: Definitions for Feast (Feature Store).
- **Status**: Defines offline (file/DWH) and online (Redis) feature views.

### `training/` & `scoring/` (ML Ops)
- **Purpose**: Model training pipelines and BentoML serving code.
- **Status**: Independent ML lifecycle components.
