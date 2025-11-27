# Test Suite for Home Credit Application

This directory contains the comprehensive test suite for the Home Credit loan application system.

## Test Structure

```
tests/
├── unit/                    # Unit tests (fast, isolated)
│   └── api/                # API endpoint tests
│       ├── test_health.py          # Health check endpoint
│       ├── test_presigned_url.py   # Document upload URLs
│       └── test_loan_applications.py # Loan CRUD operations
├── integration/            # Integration tests (with real services)
├── e2e/                   # End-to-end tests (full pipeline)
├── performance/           # Load and performance tests
├── fixtures/              # Test data files
├── conftest.py           # Shared pytest fixtures
├── pytest.ini            # Pytest configuration
└── requirements-test.txt # Test dependencies
```

## Running Tests

### Install test dependencies
```bash
cd tests/
pip install -r requirements-test.txt
```

### Run all tests
```bash
pytest
```

### Run specific test categories
```bash
# Unit tests only (fast)
pytest -m unit

# Integration tests
pytest -m integration

# E2E tests
pytest -m e2e

# Performance tests
pytest -m performance
```

### Run with coverage
```bash
pytest --cov=../ --cov-report=html
```

### Run specific test file
```bash
pytest unit/api/test_health.py -v
```

## Test Coverage

### ✅ Completed
- **Health Check Endpoint** (`test_health.py`)
  - Healthy status response
  - Unhealthy status when DB fails

- **Pre-signed URL Endpoint** (`test_presigned_url.py`)
  - Successful URL generation
  - Invalid document type validation
  - Invalid file extension validation
  - Missing customer ID validation
  - Path traversal security test

- **Loan Application Endpoints** (`test_loan_applications.py`)
  - Create application successfully
  - Get application status
  - Application not found (404)
  - Status not found (404)

### 🚧 In Progress
- More API validation tests
- Scoring service tests
- Feature store tests

### 📋 Planned
- Integration tests with real database
- Kafka consumer tests
- E2E pipeline tests
- Performance/load tests

## Test Conventions

### Naming
- Test files: `test_*.py`
- Test functions: `test_*`
- Test classes: `Test*`

### Markers
- `@pytest.mark.unit` - Fast, isolated tests
- `@pytest.mark.integration` - Tests requiring external services
- `@pytest.mark.e2e` - Full pipeline tests
- `@pytest.mark.slow` - Tests taking > 1 second

### Fixtures
- Use fixtures from `conftest.py` for reusable test data
- `sample_loan_application` - Generates loan application data
- `api_client` - Async HTTP client for API testing
- `async_db_session` - Database session for testing
- `mock_redis`, `mock_kafka_producer` - Mock services

## Code Quality

All tests follow:
- **PEP 8** style guidelines
- **88 character** line length (Black formatter)
- **Comprehensive docstrings** explaining what each test does
- **Small, focused functions** testing one thing at a time

## Contributing

When adding new tests:
1. Place in appropriate directory (unit/integration/e2e)
2. Add proper pytest markers
3. Write clear docstrings
4. Use existing fixtures when possible
5. Follow PEP 8 conventions
6. Keep functions small and focused
