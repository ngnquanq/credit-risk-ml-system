FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 

WORKDIR /app


# Copy minimal service requirements and install
COPY ./application/services/requirements-service.txt /app/requirements.txt
RUN python -m pip install -r /app/requirements.txt

# Copy application code
COPY application/ /app/application/

ENV PYTHONPATH=/app

# Default command can be overridden by compose
CMD ["python", "application/services/external_bureau_service.py"]
