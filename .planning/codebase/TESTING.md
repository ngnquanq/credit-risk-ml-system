# Testing Patterns

**Analysis Date:** 2026-04-15

## Test Framework

**Runner:**
- Framework: pytest 7.0+
- Config: `pyproject.toml` with `[tool.pytest.ini_options]`
- Python: 3.10+
- Async support: pytest-asyncio 0.23+

**Key Configuration:**
```ini
[tool.pytest.ini_options]
minversion = "6.0"
addopts = "-ra -q --strict-markers"
testpaths = ["tests"]
python_files = "test_*.py"
asyncio_mode = "auto"
pythonpath = ["application"]
markers = [
    "unit: Unit tests (no I/O)",
    "integration: Integration tests (in-memory DB, httpx)",
    "slow: Slow tests",
    "kafka: Tests involving Kafka mocks",
    "db: Tests involving database",
]
```

**Assertion Library:**
- Standard pytest assertions: `assert result == expected`
- NumPy assertions for arrays: `np.testing.assert_array_equal(result, [[3.0, 1.0, 2.0]])`
- Mock spec assertions: `mock.assert_called_once()`, `mock.assert_called_once_with(...)`

**Run Commands:**
```bash
pytest tests/                           # Run all tests
pytest tests/unit/ -v                   # Run unit tests with verbose output
pytest tests/integration/ -v            # Run integration tests
pytest tests/ --cov=application         # Run with coverage
pytest tests/test_load/                 # Run Locust load tests
pytest -m unit                          # Run tests marked as @pytest.mark.unit
pytest -m "not slow"                    # Skip slow tests
```

## Test File Organization

**Location:**
- Co-located with code: `tests/` mirrors `application/` structure
- Unit tests in `tests/unit/`: domain, workflows, infrastructure, scoring, schemas, consumers
- Integration tests in `tests/integration/`: API endpoints, repository operations
- Load tests in `tests/test_load/`: Locust E2E prediction tracking

**Directory Structure:**
```
tests/
├── conftest.py                  # Root fixtures (env setup, tracing patches)
├── unit/
│   ├── conftest.py              # Unit test fixtures (mocks, sample data)
│   ├── domain/test_*.py
│   ├── workflows/test_*.py
│   ├── infrastructure/test_*.py
│   ├── scoring/test_*.py
│   ├── schemas/test_*.py
│   └── consumers/test_*.py
├── integration/
│   ├── conftest.py              # Integration fixtures (in-memory DB, httpx client)
│   ├── api/test_*.py
│   └── repository/test_*.py
└── test_load/
    ├── locustfile.py            # Basic load test
    └── locustfile_e2e_prediction.py  # Full pipeline load test
```

**Naming:**
- Test files: `test_{module}.py` (matches pytest convention)
- Test classes: `Test{FeatureName}` (e.g., `TestEvaluateWorthiness`, `TestSubmitLoanWorkflow`)
- Test methods: `test_{specific_case}` (e.g., `test_approve_below_threshold`, `test_execute_saves_application`)
- Fixtures: `{entity}_fixture()` or descriptive name (e.g., `sample_loan_application`, `mock_loan_repo`, `db_session`)

## Test Structure

**Suite Organization:**
```python
class TestEvaluateWorthiness:
    def test_approve_below_threshold(self):
        app = LoanApplication(sk_id_curr="1", amt_credit=100, amt_income_total=100)
        result = app.evaluate_worthiness(risk_score=0.3, threshold=0.5)
        assert result is True
        assert app.status == ApplicationStatus.APPROVED

    def test_reject_above_threshold(self):
        app = LoanApplication(sk_id_curr="1", amt_credit=100, amt_income_total=100)
        result = app.evaluate_worthiness(risk_score=0.6, threshold=0.5)
        assert result is False
        assert app.status == ApplicationStatus.REJECTED
```

**Patterns:**
- One test class per public feature/method: `TestEvaluateWorthiness` for `evaluate_worthiness()`
- Single assertion per logical case when possible: focus on one aspect
- Multi-assertion allowed when testing state change: `assert app.evaluate_worthiness(...) is True` + `assert app.status == ...`
- Descriptive test names encode the scenario: `test_at_threshold_approves` (vs. generic `test_threshold`)
- Bug documentation via comments and test names: `test_domain_vs_pipeline_boundary` documents threshold inconsistency

**Setup and Teardown:**
- `@pytest.fixture` for setup: `sample_loan_application()` creates default entity
- Async fixtures with `async def` and `yield`: `async_engine`, `db_session`
- Session-scoped fixtures for expensive setup: `_mock_bentoml_and_import` mocks module-level side effects once
- Cleanup via `yield` or fixture teardown: `await engine.dispose()` after session
- `autouse=True` for required fixtures: `_set_test_env()`, `_patch_tracing()` run automatically

**Test Isolation:**
- Environment variables reset per-test: `_set_test_env()` saves/restores `os.environ`
- Mutable state reset between tests: `_reset_state()` fixture in scoring tests clears globals
- Database rolls back after each test: `async with session_factory() as session: ... await session.rollback()`
- Dependency overrides cleared: `app.dependency_overrides.clear()` in integration tests

## Mocking

**Framework:** unittest.mock (`MagicMock`, `AsyncMock`, `patch`)

**Patterns:**

### Using spec_set for Type Safety:
```python
@pytest.fixture
def mock_loan_repo():
    """AsyncMock repository implementing LoanRepository."""
    repo = AsyncMock(spec=LoanRepository)
    repo.save.return_value = None
    repo.get_by_id.return_value = None
    return repo
```

### Patching at Import Time:
```python
@pytest.fixture
def gateway():
    with patch("infrastructure.external.kafka_scoring.Producer") as MockProducer:
        mock_producer = MagicMock()
        MockProducer.return_value = mock_producer
        gw = KafkaScoringGateway()
        gw._mock_producer = mock_producer
        yield gw
```

### Session-Scoped Mocking for Module-Level Side Effects:
```python
@pytest.fixture(scope="module", autouse=True)
def _mock_bentoml_and_import():
    """Mock bentoml + bare-name modules BEFORE import scoring.service."""
    mock_bentoml = MagicMock()
    mock_bentoml.importing.return_value.__enter__ = MagicMock(return_value=None)
    saved_modules = {}
    for mod_name in ["bentoml"]:
        saved_modules[mod_name] = sys.modules.get(mod_name)
        sys.modules[mod_name] = mock_bentoml
    
    import scoring.service as svc
    # ... populate globals
    yield svc
    
    # Restore
    for mod_name, saved in saved_modules.items():
        if saved: sys.modules[mod_name] = saved
```

**What to Mock:**
- External APIs: Kafka producer, ClickHouse client, Redis
- Database sessions: provide in-memory SQLite instead
- BentoML service: mock `bentoml.Service()` and its context managers
- Expensive I/O: bureau client queries, scoring gateway publishes
- Do NOT mock domain entities: test real `LoanApplication` behavior

**What NOT to Mock:**
- Domain business logic: test `LoanApplication.evaluate_worthiness()` with real logic
- Pydantic models: test real validation errors
- Enum classes: test real enum values
- Simple utility functions: test `as_vector()`, `postprocess()` with real implementation

## Fixtures and Factories

**Test Data:**

### Sample Domain Entity:
```python
@pytest.fixture
def sample_loan_application():
    """Valid LoanApplication domain entity."""
    return LoanApplication(
        sk_id_curr="100001",
        amt_credit=500_000.0,
        amt_income_total=200_000.0,
        amt_goods_price=450_000.0,
        details={"code_gender": "M", "cnt_children": 1},
    )
```

### Valid API Payload:
```python
@pytest.fixture
def valid_create_payload():
    """Minimal valid dict for LoanApplicationCreate schema."""
    return {
        "sk_id_curr": "100001",
        "code_gender": "M",
        "birth_date": "1990-01-15",
        "cnt_children": 0,
        "amt_income_total": 180_000.0,
        "amt_credit": 406_597.5,
        "name_income_type": "Working",
        "name_education_type": "Higher education",
        "name_family_status": "Married",
        "name_housing_type": "House / apartment",
    }
```

### Factory Function:
```python
def _make_app(sk_id="T001", **overrides):
    """Create LoanApplication with sensible defaults, allowing overrides."""
    defaults = dict(
        sk_id_curr=sk_id,
        amt_credit=100_000.0,
        amt_income_total=50_000.0,
        details={
            "sk_id_curr": sk_id,
            "code_gender": "M",
            "birth_date": date(1990, 1, 1),
            "cnt_children": 0,
            # ... more fields
        },
    )
    defaults.update(overrides)
    return LoanApplication(**defaults)
```

**Location:**
- Root fixtures in `tests/conftest.py`: environment setup (patching, env vars)
- Unit fixtures in `tests/unit/conftest.py`: mocks, sample entities, DTOs
- Integration fixtures in `tests/integration/conftest.py`: in-memory DB, httpx client, FastAPI app
- Test-specific fixtures defined in test file when used by single test class

**Scope:**
- `scope="session"`: expensive patches applied once (BentoML mocking, Python path setup)
- `scope="function"` (default): fresh instance per test (isolation)
- `scope="module"`: shared across test class (mutable state reset via separate fixture)

## Coverage

**Requirements by Area (from CI gates in `.github/workflows/test.yml`):**
- Domain & Workflows: 90% (`--cov-fail-under=90`)
- Schemas & Validation: 90%
- Scoring Pipeline: 60%
- Infrastructure Adapters: 80%
- Kafka Consumers: 45%
- Integration (API + Repository): 60%

**View Coverage:**
```bash
pytest tests/ --cov=application --cov-report=html
open htmlcov/index.html  # View in browser
pytest tests/ --cov=application --cov-report=term-missing  # Show missing lines
```

**Known Coverage Gaps:**
- `entrypoints/bureau_consumer.py`: partial (45% threshold) — async Kafka loop hard to test
- `feast_repo/stream_processor.py`: partial (45%) — Redis coordination complex to mock
- Error paths in external adapters: often skipped in unit, tested indirectly in integration

## Test Types

**Unit Tests:** `tests/unit/`
- No I/O, no database, no external services
- Test pure functions and domain entities
- Examples: `test_loan_application.py` (domain logic), `test_pipeline.py` (numpy operations)
- Scope: domain, workflows, pure utilities
- Mock all infrastructure dependencies

**Integration Tests:** `tests/integration/`
- In-memory SQLite database, httpx ASGI client
- Test API endpoints with mocked external services
- Examples: `test_applications.py` (POST /api/v1/applications), `test_postgres_repo.py` (DB ops)
- Scope: API boundary, repository persistence
- Real: FastAPI app, SQLAlchemy ORM; Mocked: Kafka, external bureaus, BentoML

**Load Tests:** `tests/test_load/`
- Framework: Locust
- Purpose: E2E pipeline latency measurement
- File: `locustfile_e2e_prediction.py` traces loan submission → CDC → Flink → Feast → KServe prediction
- Execution: `locust -f tests/locustfile_e2e_prediction.py --users 50 --spawn-rate 10 --run-time 5m`
- Tracks: per-request latency, throughput, failure rate

## Common Patterns

**Async Testing:**
```python
async def test_execute_saves_application(self, mock_loan_repo, mock_scoring_gateway, valid_input):
    wf = SubmitLoanWorkflow(mock_loan_repo, mock_scoring_gateway)
    await wf.execute(valid_input)
    
    mock_loan_repo.save.assert_called_once()
    saved_app = mock_loan_repo.save.call_args[0][0]
    assert saved_app.sk_id_curr == valid_input.sk_id_curr
```

**Error Testing:**
```python
async def test_repo_exception_propagates(self, mock_loan_repo, mock_scoring_gateway, valid_input):
    """No try/except in workflow — errors propagate to caller."""
    mock_loan_repo.save.side_effect = RuntimeError("DB down")
    
    wf = SubmitLoanWorkflow(mock_loan_repo, mock_scoring_gateway)
    with pytest.raises(RuntimeError, match="DB down"):
        await wf.execute(valid_input)
```

**Mock Assertion Patterns:**
```python
# Assert called once with specific args
mock_loan_repo.save.assert_called_once()

# Capture call arguments for assertion
saved_app = mock_loan_repo.save.call_args[0][0]
assert saved_app.sk_id_curr == "100001"

# Side effects to simulate behavior
mock_workflow.execute.side_effect = RuntimeError("boom")

# Verify call order
call_order = []
mock_repo.save.side_effect = lambda _: call_order.append("save")
mock_gateway.publish.side_effect = lambda _: call_order.append("publish")
await wf.execute(input_data)
assert call_order == ["save", "publish"]
```

**In-Memory Database Testing:**
```python
@pytest.fixture
async def async_engine():
    """In-memory SQLite engine with tables created."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest.fixture
async def db_session(async_engine):
    """Async session that rolls back after each test."""
    session_factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()
```

**FastAPI Integration Testing:**
```python
@pytest.fixture
async def api_client(test_app):
    """httpx AsyncClient bound to the test app."""
    import httpx
    from httpx import ASGITransport
    
    transport = ASGITransport(app=test_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

# Usage in test:
async def test_post_valid_payload_succeeds(self, api_client, valid_payload):
    resp = await api_client.post("/api/v1/applications", json=valid_payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["application_id"] == valid_payload["sk_id_curr"]
```

## CI Configuration

**Workflow File:** `.github/workflows/test.yml`

**Triggering:**
- On push to `main` and `feature/**` branches
- On pull requests to `main`
- Only if changes touch: `application/**`, `tests/**`, or `pyproject.toml`

**Gates (6 parallel jobs, all must pass):**

1. **Domain & Workflows** (90% coverage required)
   ```bash
   pytest tests/unit/domain tests/unit/workflows \
     --cov=domain/entities --cov=workflows \
     --cov-fail-under=90 --tb=short -q
   ```

2. **Schemas & Validation** (90% required)
   ```bash
   pytest tests/unit/schemas \
     --cov=infrastructure/persistence/models/pydantic_schemas \
     --cov-fail-under=90 --tb=short -q
   ```

3. **Scoring Pipeline** (60% required)
   ```bash
   pytest tests/unit/scoring \
     --cov=scoring --cov-fail-under=60 --tb=short -q
   ```

4. **Infrastructure Adapters** (80% required)
   ```bash
   pytest tests/unit/infrastructure \
     --cov=infrastructure/external --cov=infrastructure/persistence \
     --cov-fail-under=80 --tb=short -q
   ```

5. **Kafka Consumers** (45% required)
   ```bash
   pytest tests/unit/consumers \
     --cov=entrypoints/bureau_consumer --cov=entrypoints/feature_consumer \
     --cov=feast_repo/stream_processor \
     --cov-fail-under=45 --tb=short -q
   ```

6. **Integration Tests** (60% required)
   ```bash
   pytest tests/integration \
     --cov=entrypoints/api --cov=infrastructure/persistence \
     --cov-fail-under=60 --tb=short -q
   ```

**Environment:**
- Python 3.10
- `PYTHONPATH=application` set in workflow env
- Dependencies installed with: `pip install -e ".[test]"`
- Runs on `ubuntu-latest`

**Failure Behavior:**
- Test failure blocks PR merge
- Coverage threshold failure blocks PR merge
- Short traceback (`--tb=short`) for clarity
- Quiet output (`-q`) for brevity

---

*Testing analysis: 2026-04-15*
