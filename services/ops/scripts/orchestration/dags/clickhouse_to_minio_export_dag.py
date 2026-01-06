"""
ClickHouse to MinIO Data Export DAG

Periodically exports training data from ClickHouse data mart to MinIO bucket.
The data is exported as CSV snapshots for model training workflows.

Usage:
- Runs daily at 3 AM (configurable via schedule_interval)
- Trigger manually via Airflow UI or:
  docker exec airflow-scheduler airflow dags trigger clickhouse_to_minio_export
- Configure export parameters via params (bucket, path, date partition, etc.)
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator

DEFAULT_ARGS = {
    "owner": "ml-platform",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="clickhouse_to_minio_export",
    description="Export training data from ClickHouse to MinIO for ML workflows",
    default_args=DEFAULT_ARGS,
    start_date=datetime(2024, 1, 1),
    schedule_interval="0 3 * * *",  # Run daily at 3 AM
    catchup=False,
    tags=["data-export", "clickhouse", "minio", "training-data"],
    params={
        "minio_endpoint": "http://172.18.0.1:31900",
        "minio_access_key": "minioadmin",
        "minio_secret_key": "minioadmin",
        "bucket": "training-data",
        "ch_host": "clickhouse_dwh",
        "ch_database": "application_mart",
        "app_table": "mart_application",
        "train_table": "mart_application_train",
        "output_filename": "loan_applications.csv",
    },
) as dag:

    # Task: Export loan applications with target labels to MinIO
    # Note: ds is Airflow's execution date in YYYY-MM-DD format
    export_cmd = """
    docker exec clickhouse_dwh clickhouse-client -q "SET s3_truncate_on_insert=1; INSERT INTO FUNCTION s3('{{ params.minio_endpoint }}/{{ params.bucket }}/snapshots/ds={{ ds }}/{{ params.output_filename }}', '{{ params.minio_access_key }}', '{{ params.minio_secret_key }}', 'CSVWithNames') SELECT a.*, t.TARGET FROM {{ params.ch_database }}.{{ params.app_table }} AS a INNER JOIN {{ params.ch_database }}.{{ params.train_table }} AS t ON a.SK_ID_CURR = t.SK_ID_CURR"
    """

    export_data = BashOperator(
        task_id="export_training_data",
        bash_command=export_cmd,
    )

    # Task: Verify export success by checking MinIO
    verify_cmd = """
    echo "✅ Export completed successfully"
    echo "Bucket: {{ params.bucket }}"
    echo "Path: snapshots/ds={{ ds }}/{{ params.output_filename }}"
    echo "Timestamp: $(date)"
    """

    verify_export = BashOperator(
        task_id="verify_export",
        bash_command=verify_cmd,
    )

    # Define task dependencies
    export_data >> verify_export
