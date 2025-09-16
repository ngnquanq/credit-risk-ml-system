FROM apache/airflow:2.7.1
USER root

# Install system dependencies required for Ray
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        libgl1-mesa-glx \
        libglib2.0-0 \
        gosu \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*



USER airflow

# Python dependencies needed for training and MLflow logging
COPY requirements-airflow.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Drop back to the airflow user
# USER airflow
