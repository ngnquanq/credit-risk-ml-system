from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator


DEFAULT_ARGS = {
    "owner": "ml-platform",
    "depends_on_past": False,
    "retries": 0,
}


with DAG(
    dag_id="train_register_model",
    description="Train credit risk model and register to MLflow",
    default_args=DEFAULT_ARGS,
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,  # Trigger manually
    catchup=False,
    tags=["ml", "training", "mlflow"],
    params={
        "data_path": "/opt/airflow/data/complete_feature_dataset.csv",
        "experiment": "credit-risk",
        "register_name": "credit_risk_model",
        "stage": "Production",  # e.g. "Staging" or "Production"
    },
) as dag:

    bash_cmd = (
        "python /opt/airflow/application/training/train_register.py "
        "--data {{ params.data_path }} "
        "--experiment {{ params.experiment }} "
        "--register-name {{ params.register_name }} "
        "{% if params.stage %}--stage {{ params.stage }}{% endif %}"
    )

    run_training = BashOperator(
        task_id="run_training",
        bash_command=bash_cmd,
        env={
            # Point to services started by services/ml/docker-compose.registry.yml
            "MLFLOW_TRACKING_URI": "http://mlflow-server:5000",
            "MLFLOW_S3_ENDPOINT_URL": "http://mlflow-minio:9006",
            "AWS_ACCESS_KEY_ID": "minio_user",
            "AWS_SECRET_ACCESS_KEY": "minio_password",
        },
    )

    run_training

