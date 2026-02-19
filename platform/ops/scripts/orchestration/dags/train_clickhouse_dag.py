from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator


DEFAULT_ARGS = {"owner": "ml-platform", "depends_on_past": False, "retries": 0}


with DAG(
    dag_id="train_clickhouse_model",
    description="Train model from ClickHouse marts and register to MLflow",
    default_args=DEFAULT_ARGS,
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,
    catchup=False,
    tags=["ml", "training", "mlflow", "clickhouse"],
    params={
        "ch_host": "ch-server",
        "ch_port": 8123,
        "database": "application_mart",
        "app_table": "mart_application",
        "train_table": "mart_application_train",
        "cc_table": "mart_credit_card_balance",
        "join_key": "SK_ID_CURR",
        "sample": 0,  # 0 = no limit; set e.g., 10000 for a quick run
        "experiment": "credit-risk",
        "register_name": "credit_risk_model_clickhouse",
        "stage": None,  # e.g., "Staging" or "Production"
        "test_size": 0.2,
        "random_state": 42,
        "cv": 3,
        "tune_iter": 10,
    },
) as dag:
    cmd = (
        "python -u /opt/airflow/application/training/train_clickhouse.py "
        "--ch-host {{ params.ch_host }} "
        "--ch-port {{ params.ch_port }} "
        "--database {{ params.database }} "
        "--app-table {{ params.app_table }} "
        "--train-table {{ params.train_table }} "
        "--cc-table {{ params.cc_table }} "
        "--join-key {{ params.join_key }} "
        "--sample {{ params.sample }} "
        "--experiment {{ params.experiment }} "
        "--register-name {{ params.register_name }} "
        "--test-size {{ params.test_size }} "
        "--random-state {{ params.random_state }} "
        "--cv {{ params.cv }} "
        "--tune-iter {{ params.tune_iter }} "
        "{% if params.stage %} --stage {{ params.stage }} {% endif %}"
    )

    run = BashOperator(
        task_id="train_from_clickhouse",
        bash_command=cmd,
        env={
            "PYTHONUNBUFFERED": "1",
            "MLFLOW_TRACKING_URI": "http://mlflow-server:5000",
            "MLFLOW_S3_ENDPOINT_URL": "http://mlflow-minio:9006",
            "AWS_ACCESS_KEY_ID": "minio_user",
            "AWS_SECRET_ACCESS_KEY": "minio_password",
            "MLFLOW_HTTP_REQUEST_TIMEOUT": "15",
        },
    )

    run

