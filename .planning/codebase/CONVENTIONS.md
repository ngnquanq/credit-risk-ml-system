# Coding Conventions

**Analysis Date:** 2026-04-15

## Naming Patterns

**Files:**
- Snake case with descriptive names: `test_submit_loan.py`, `postgres_loan_repo.py`, `bureau_consumer.py`
- Module-level files use domain/purpose: `pipeline.py`, `service.py`, `schemas.py`, `logger.py`
- Test files follow pattern `test_*.py` (pytest convention)

**Classes:**
- PascalCase for all classes: `LoanApplication`, `SubmitLoanWorkflow`, `PostgresLoanRepository`, `ExternalBureauService`
- Abstract base classes (ABC) use `Gateway`, `Repository`, `Client` suffixes: `ScoringGateway`, `LoanRepository`, `BureauGateway`
- Pydantic models use descriptive full names: `LoanApplicationCreate`, `LoanApplicationResponse`, `ScoreRequest`, `ScoreByIdRequest`

**Functions and Methods:**
- Snake case: `evaluate_worthiness()`, `debt_to_income_ratio`, `get_by_id()`, `save()`, `publish_for_scoring()`
- Async functions use `async def`: `async def execute()`, `async def save()`
- Private methods prefix with underscore: `_consume_predictions()`, `_expected_fields_for_source()`
- Properties use `@property` decorator: `debt_to_income_ratio` in `LoanApplication`

**Variables:**
- Snake case for local variables and instance attributes: `sk_id_curr`, `amt_credit`, `amt_income_total`, `db_model`, `raw_data`
- Configuration/constant names use UPPER_SNAKE_CASE in settings classes: `APP_NAME`, `OPS_DB_HOST`, `KAFKA_BOOTSTRAP_SERVERS`
- Special prefixes for domain concepts: `sk_id_curr` (customer ID, consistent across all files), `amt_*` (amounts)

**Enums:**
- PascalCase class names with UPPER_SNAKE_CASE members: `ApplicationStatus.SUBMITTED`, `ApplicationStatus.APPROVED`, `GenderType.MALE`, `IncomeType.WORKING`
- Enum values use lowercase or uppercase depending on context: `"submitted"` (lowercase for DB/API), `"M"` for coded values

## Code Style

**Formatting:**
- Tool: Black (configured in `pyproject.toml`)
- Line length: 88 characters
- Trailing commas in multi-line structures enforced (isort + Black compatibility)

**Linting:**
- Tool: isort (configured in `pyproject.toml`)
- Profile: black (compatible with Black formatter)
- Multi-line imports: trailing commas on multi-line lists

**Type Hints:**
- Mandatory on function signatures: `async def execute(self, input_data: SubmitLoanInput) -> SubmitLoanOutput:`
- Use `Optional[T]` for nullable types: `Optional[float]`, `Optional[dict]`
- Import from `typing`: `Optional`, `Dict`, `Any`, `Sequence`, `Mapping`, `Tuple`
- Async functions properly typed with return hints
- No bare `Any` without context — use specific types when possible

## Import Organization

**Order:**
1. Standard library: `import os`, `import json`, `from datetime import datetime`
2. Third-party: `from fastapi import FastAPI`, `from pydantic import BaseModel`, `from sqlalchemy`
3. Application layer: `from domain.entities.loan_application import LoanApplication`, `from infrastructure.persistence.postgres_loan_repo import PostgresLoanRepository`

**Path Aliases:**
- Imports assume `PYTHONPATH=application` (set in `pyproject.toml`)
- Absolute imports from application root: `from domain.entities.loan_application import ...` (not relative)
- Scoring-specific modules accessed as: `from scoring.pipeline import as_vector`
- Core config imported as: `from core.config import settings`

**Barrel Files:**
- Used in `application/core/__init__.py` to export common utilities
- Example: `from core import settings, get_db, init_db, close_db` in API main.py

## Error Handling

**Pattern:**
- Errors propagate to caller by default (no broad try/except)
- Example in `SubmitLoanWorkflow.execute()`: repo exceptions bubble up; caller (API endpoint) catches and returns 500
- Async errors propagate immediately: `await self.loan_repo.save(application)` raises on DB failure

**Logging Over Silent Failures:**
- Exceptions are logged with structured context before propagation
- Example in `ExternalBureauService.fetch_and_prepare_raw_data()`: catches parsing errors and logs, then continues
- Use `logger.bind()` for context: `logger.bind(event="bureau_fetched").info({...})`

**Fire-and-Forget Semantics:**
- `KafkaScoringGateway.publish_for_scoring()` catches and logs exceptions instead of raising
- Pattern: `try: producer.produce(...) except (Exception, BufferError): logger.error(...)`
- Rationale: Kafka producer errors are not fatal to the workflow

**Domain Boundary Inconsistencies (Documented):**
- `test_loan_application.py::TestThresholdInconsistency` documents domain vs. pipeline threshold bug
  - Domain uses `>` (score > threshold → reject), pipeline uses `>=` (score >= threshold → reject)
  - At threshold boundary, domain approves but pipeline rejects
- `test_postgres_repo.py::TestGetById` documents missing `status` column bug in repository conversion

## Logging

**Framework:** Loguru (not Python logging)
- Imported as: `from loguru import logger`
- Structured JSON logging: configured in `scoring/logger.py`
- Service-level initialization: `tracer = setup_tracing("service-name", sampling_rate=0.1)`

**Patterns:**
- Info events with context: `logger.info(f"Received application for {application.sk_id_curr}")`
- Structured bind for event tracking: `logger.bind(event="bureau_fetched").info({...})`
- Errors logged before propagation: catch, log, re-raise or handle
- JSON serialization mode enabled in production (`serialize=True`)

**OpenTelemetry Integration:**
- Tracing initialized per service: `from core.tracing import setup_tracing`
- Tracer accessed globally: `tracer = setup_tracing("service-name")`
- Sampling configured: default 0.1 (10% of spans)
- Context propagation via `extract_or_create_trace_context()`

## Comments

**When to Comment:**
- Complex business rules documented inline: "Business Rule 1: High risk score means rejection"
- Bug documentation explicit: comments marked with `BUG DOC:` flagged in test files
- Data structure clarifications: "Store other details that are not evaluating factors but needed for persistence"
- Not required for obvious code: self-documenting function/variable names preferred

**JSDoc/Docstrings:**
- Function docstrings use triple-quoted format: `"""Fetch external bureau data and prepare for Flink."""`
- Parameter documentation in docstring: "Returns: raw_data dictionary containing: - sk_id_curr..."
- Abstract interface methods documented: base class defines contract
- Return type hints substitute for return documentation when types are clear

**Class-Level Documentation:**
- Dataclass purpose stated: `"""Domain Entity for Loan Application. This is the core business object..."""`
- Domain/infrastructure boundary clarified: comments explain separation of concerns
- Example in `PostgresLoanRepository`: "Infrastructure implementation of the Domain Repository. Bridges the gap between pure Domain Entities and SQLAlchemy Models."

## Function Design

**Size:** Keep functions small and focused
- Single responsibility: `evaluate_worthiness()` makes approval decision only
- Orchestration separated from implementation: `SubmitLoanWorkflow.execute()` calls domain, repo, gateway
- Helper functions for common operations: `as_vector()`, `postprocess()` in scoring pipeline

**Parameters:**
- Use Data Transfer Objects (DTOs) for multiple parameters: `SubmitLoanInput` instead of multiple params
- Domain entities passed to workflows: `LoanApplication` to `evaluate_worthiness()`
- Config passed once at initialization: `settings` injected into service constructors

**Return Values:**
- Domain entities return from workflows: `LoanApplication` returned from repository
- DTOs used for workflow output: `SubmitLoanOutput` from `execute()`
- Tuples for paired return values: `postprocess()` returns `Tuple[float, str]` (probability, decision)
- None for void operations: `save()` and `publish_for_scoring()` return None

**Async/Await:**
- All I/O operations are async: `async def save()`, `async def execute()`
- Async context managers used for resource management: `async with engine.begin()`
- Task execution via thread pools allowed for sync operations: `ThreadPoolExecutor` in consumers

## Module Design

**Exports:**
- Explicit imports from modules: `from domain.entities.loan_application import LoanApplication, ApplicationStatus`
- Core module re-exports utilities: `from core import settings, get_db, init_db, close_db`
- No wildcard imports (`from x import *`) in production code

**Clean Architecture Layers:**
- `domain/`: Pure business logic, no I/O, dataclasses and enums
- `infrastructure/`: Adapters to external systems (DB, Kafka, ClickHouse)
- `workflows/`: Orchestration of domain + infrastructure (no domain logic)
- `entrypoints/`: HTTP API (FastAPI) and async consumers (Kafka)
- `scoring/`: Model inference pipeline (BentoML service)
- `core/`: Shared configuration, database, tracing setup

**Separation of Concerns:**
- Domain entities immutable properties: `status`, `request_date` managed by entity
- Repository converts between domain and DB models: handles SQLAlchemy mapping
- Workflow orchestrates save → publish sequence, doesn't know DB/Kafka details
- API endpoint validates input schema, calls workflow, maps response schema

---

*Convention analysis: 2026-04-15*
