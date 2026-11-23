# Builder stage
FROM python:3.10-slim as builder

WORKDIR /build
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install dependencies into venv
COPY services/loan-api/requirements-api.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements-api.txt

# Final runner stage
FROM python:3.10-slim

WORKDIR /app

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
# Make sure we use the virtualenv
ENV PATH="/opt/venv/bin:$PATH"

# Copy the venv from builder
COPY --from=builder /opt/venv /opt/venv

# Loan API runtime and the catalog text it uses to render decision reasons.
COPY services/loan-api/src/run.py /app/run.py
COPY services/loan-api/src/entrypoints/api /app/entrypoints/api
COPY services/loan-api/src/audit /app/audit
COPY services/loan-api/src/authz /app/authz
COPY services/loan-api/src/core /app/core
COPY services/loan-api/src/decisions /app/decisions
COPY services/loan-api/src/domain /app/domain
COPY services/loan-api/src/identity /app/identity
COPY services/loan-api/src/infrastructure /app/infrastructure
COPY services/loan-api/src/workflows /app/workflows
COPY contracts/feature_catalog/__init__.py contracts/feature_catalog/reasons.yaml /app/feature_catalog/

# Create non-root user and set permissions
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app
USER app

EXPOSE 8000

CMD ["python", "-m", "run"]
