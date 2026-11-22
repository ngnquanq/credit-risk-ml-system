# Builder stage
FROM python:3.10-slim as builder

WORKDIR /build
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY ./application/entrypoints/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Final runner stage
FROM python:3.10-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 
ENV PATH="/opt/venv/bin:$PATH"

COPY --from=builder /opt/venv /opt/venv
# Used by the enrichment consumers, decision recorder and audit verification job.
COPY application/entrypoints/bureau_consumer.py application/entrypoints/feature_consumer.py application/entrypoints/decision_recorder.py /app/entrypoints/
COPY application/audit /app/audit
COPY application/core /app/core
COPY application/decisions /app/decisions
COPY application/infrastructure /app/infrastructure
ENV PYTHONPATH=/app

CMD ["python", "entrypoints/bureau_consumer.py"]
