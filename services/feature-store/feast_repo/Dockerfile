FROM python:3.10-slim

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Pin versions known to work with our streaming definitions
RUN pip install --no-cache-dir \
    'feast[redis,kafka]==0.34.1' \
    'pyarrow==11.0.0' \
    'dask==2023.3.2' \
    'pandas==1.5.3' \
    'kafka-python==2.0.2' \
    'loguru==0.7.2' \
    'clickhouse-connect==0.7.17' \
    'boto3>=1.28.0' \
    'redis'

WORKDIR /work

COPY . /work/

# Default command executes Feast CLI; compose overrides to generate config then apply
CMD ["feast", "apply"]
