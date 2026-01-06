FROM apache/airflow:2.10.5
USER root

# Install minimal system dependencies only (no Spark client to keep builds fast)
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        libgl1-mesa-glx \
        libglib2.0-0 \
        gosu \
        git; \
    rm -rf /var/lib/apt/lists/*

USER airflow

# Python dependencies needed for training and MLflow logging
COPY requirements-airflow.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Drop back to the airflow user
# USER airflow
