from datetime import datetime
import os

from airflow import DAG
from airflow.providers.docker.operators.docker import DockerOperator
from docker.types import Mount


DEFAULT_ARGS = {"owner": "ml-platform", "depends_on_past": False, "retries": 0}


with DAG(
    dag_id="train_spark_clickhouse_model_docker",
    description="Run spark-submit in a Spark client container (bitnami/spark) to train and register model",
    default_args=DEFAULT_ARGS,
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,
    catchup=False,
    tags=["ml", "training", "mlflow", "spark", "docker"],
    params={
        # Simple, public image with Spark + Python
        "image": "jupyter/pyspark-notebook:spark-3.4.1",
        # Default to local[2] to avoid executor python issues; switch to spark://spark-master:7077 later
        "spark_master": "local[2]",
        "ch_host": "ch-server",
        "ch_port": 8123,
        "database": "application_mart",
        "app_table": "mart_application",
        "train_table": "mart_application_train",
        "cc_table": "mart_credit_card_balance",
        "join_key": "SK_ID_CURR",
        "sample": 0,
        "experiment": "credit-risk",
        "register_name": "credit_risk_model_spark",
        "stage": "",  # leave blank to skip
        "max_depth": 5,
        "max_iter": 150,
        "train_ratio": 0.8,
    },
) as dag:

    app_args = [
        "--ch-host", "{{ params.ch_host }}",
        "--ch-port", "{{ params.ch_port }}",
        "--database", "{{ params.database }}",
        "--app-table", "{{ params.app_table }}",
        "--train-table", "{{ params.train_table }}",
        "--cc-table", "{{ params.cc_table }}",
        "--join-key", "{{ params.join_key }}",
        "--sample", "{{ params.sample }}",
        "--experiment", "{{ params.experiment }}",
        "--register-name", "{{ params.register_name }}",
        "--max-depth", "{{ params.max_depth }}",
        "--max-iter", "{{ params.max_iter }}",
        "--train-ratio", "{{ params.train_ratio }}",
        "--stage", "{{ params.stage }}",
    ]

    # Add a quick directory listing to verify bind mount is present before submitting
    verify_and_run = (
        "set -euo pipefail; "
        "echo 'Listing /workspace/application:'; ls -la /workspace/application; "
        "echo 'Listing /workspace/application/training:'; ls -la /workspace/application/training; "
        "echo 'Submitting Spark job...'; "
        "/usr/local/spark/bin/spark-submit --master {{ params.spark_master }} "
        "--packages com.clickhouse:clickhouse-jdbc:0.4.6,com.clickhouse:clickhouse-http-client:0.4.6 "
        "/workspace/application/training/train_spark_clickhouse.py "
        + " ".join(app_args)
    )

    cmd = ["bash", "-lc", verify_and_run]

    host_app_dir = os.environ.get("APPLICATION_HOST_DIR", "/opt/airflow/application")

    spark_client = DockerOperator(
        task_id="spark_train_clickhouse_docker",
        image="{{ params.image }}",
        api_version="auto",
        auto_remove="success",
        command=cmd,
        network_mode="hc-network",
        mount_tmp_dir=False,
        tty=False,
        mounts=[
            Mount(target="/workspace/application", source=host_app_dir, type="bind"),
        ],
        environment={
            "PYTHONUNBUFFERED": "1",
            "PYSPARK_PYTHON": "python3",
            "PYSPARK_DRIVER_PYTHON": "python3",
            "MLFLOW_TRACKING_URI": "http://mlflow-server:5000",
            "MLFLOW_S3_ENDPOINT_URL": "http://mlflow-minio:9006",
            "AWS_ACCESS_KEY_ID": "minio_user",
            "AWS_SECRET_ACCESS_KEY": "minio_password",
            "MLFLOW_HTTP_REQUEST_TIMEOUT": "15",
        },
        docker_url="tcp://docker-proxy:2375",
    )

    spark_client
