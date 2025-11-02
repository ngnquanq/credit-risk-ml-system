"""
dbt Data Transformation DAG

Runs dbt transformations on ClickHouse data warehouse using BashOperator.
The dbt project is mounted at /opt/airflow/dbt inside Airflow containers.

Usage:
- Trigger manually via Airflow UI or:
  docker exec airflow-scheduler airflow dags trigger dbt_transform
- Configure target environment via params (default: dev)
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator

DEFAULT_ARGS = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}

with DAG(
    dag_id="dbt_transform",
    description="Run dbt transformations on ClickHouse data warehouse",
    default_args=DEFAULT_ARGS,
    start_date=datetime(2024, 1, 1),
    schedule_interval="0 2 * * *",  # Run daily at 2 AM
    catchup=False,
    tags=["dbt", "transformation", "clickhouse", "data-warehouse"],
    params={
        "target": "dev",  # dbt target: dev, staging, prod
        "full_refresh": False,  # Set to True to rebuild all incremental models
        "select": None,  # Optional: specific models to run (e.g., "staging.*")
        "exclude": None,  # Optional: models to exclude
    },
) as dag:

    # Task 1: dbt debug - verify connection and configuration
    dbt_debug = BashOperator(
        task_id="dbt_debug",
        bash_command="cd /opt/airflow/dbt && dbt debug --target {{ params.target }}",
    )

    # Task 2: dbt deps - install dbt packages (if any)
    dbt_deps = BashOperator(
        task_id="dbt_deps",
        bash_command="cd /opt/airflow/dbt && dbt deps --target {{ params.target }}",
    )

    # Task 3: dbt seed - load CSV seeds (if any)
    dbt_seed = BashOperator(
        task_id="dbt_seed",
        bash_command="cd /opt/airflow/dbt && dbt seed --target {{ params.target }}",
    )

    # Task 4: dbt run - execute models
    # Build command with optional flags
    dbt_run_cmd = """
    cd /opt/airflow/dbt && dbt run --target {{ params.target }} \
    {% if params.full_refresh %} --full-refresh {% endif %} \
    {% if params.select %} --select {{ params.select }} {% endif %} \
    {% if params.exclude %} --exclude {{ params.exclude }} {% endif %}
    """

    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=dbt_run_cmd,
    )

    # Task 5: dbt test - run data quality tests
    dbt_test_cmd = """
    cd /opt/airflow/dbt && dbt test --target {{ params.target }} \
    {% if params.select %} --select {{ params.select }} {% endif %} \
    {% if params.exclude %} --exclude {{ params.exclude }} {% endif %}
    """

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=dbt_test_cmd,
    )

    # Task 6: dbt docs generate - generate documentation (optional, runs on success)
    dbt_docs = BashOperator(
        task_id="dbt_docs_generate",
        bash_command="cd /opt/airflow/dbt && dbt docs generate --target {{ params.target }}",
        trigger_rule="all_success",  # Only run if all upstream tasks succeed
    )

    # Define task dependencies
    # debug → deps → seed → run → test → docs
    dbt_debug >> dbt_deps >> dbt_seed >> dbt_run >> dbt_test >> dbt_docs
