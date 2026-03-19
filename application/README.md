# Application Directory Map

This directory contains the source code for the Credit Risk Scoring Application.
It is currently being migrated to **Clean Architecture**.

## 1. Clean Architecture (New Structure)
The goal is to decouple business logic from frameworks.

### `domain/` (The Core)
- **Purpose**: Pure business logic and rules.
- **Dependencies**: None (Standard Library only).
- **Key Files**:
    - `entities/loan_application.py`: The `LoanApplication` entity with `evaluate_worthiness` logic.
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
    - `external/bureau_adapter.py`: Wraps the legacy bureau service.
    - `external/dwh_adapter.py`: Adapts the ClickHouse DWH client.

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
