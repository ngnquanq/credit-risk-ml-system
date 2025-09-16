#!/usr/bin/env python3
"""
Train a model using data pulled from ClickHouse mart tables and register it to MLflow.

It performs:
- Connect to ClickHouse (HTTP interface) and build a dataset by joining:
  application_mart.mart_application (features) AS a
  application_mart.mart_application_train (labels) AS t
  application_mart.mart_credit_card_balance (transactions) AS cc (aggregated per key)

Defaults assume the join key column is SK_ID_CURR. Adjust with --join-key.

Examples:
  export MLFLOW_TRACKING_URI=http://localhost:5000
  export MLFLOW_S3_ENDPOINT_URL=http://localhost:9006
  export AWS_ACCESS_KEY_ID=minio_user
  export AWS_SECRET_ACCESS_KEY=minio_password

  python application/training/train_clickhouse.py \
    --ch-host localhost --ch-port 8123 \
    --database application_mart \
    --app-table mart_application \
    --train-table mart_application_train \
    --cc-table mart_credit_card_balance \
    --experiment credit-risk \
    --register-name credit_risk_model_clickhouse \
    --stage Staging
"""

from __future__ import annotations

import argparse
from typing import List, Optional

import numpy as np
import pandas as pd
from loguru import logger


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Train model from ClickHouse mart and register to MLflow")
    # ClickHouse connection
    p.add_argument("--ch-host", default="ch-server", help="ClickHouse host (service name or hostname)")
    p.add_argument("--ch-port", type=int, default=8123, help="ClickHouse HTTP port")
    p.add_argument("--ch-user", default="default", help="ClickHouse user")
    p.add_argument("--ch-password", default="", help="ClickHouse password")

    # Schema and tables
    p.add_argument("--database", default="application_mart", help="ClickHouse database name")
    p.add_argument("--app-table", default="mart_application", help="Application mart table (features)")
    p.add_argument("--train-table", default="mart_application_train", help="Training labels table (must contain TARGET)")
    p.add_argument("--cc-table", default="mart_credit_card_balance", help="Credit card balance mart table (will be aggregated)")
    p.add_argument("--join-key", default="SK_ID_CURR", help="Join key column shared by mart tables")

    # Data scope
    p.add_argument("--sample", type=int, default=0, help="Optional LIMIT for debugging (0 = no limit)")

    # MLflow
    p.add_argument("--experiment", default="credit-risk", help="MLflow experiment name")
    p.add_argument("--register-name", default="credit_risk_model_clickhouse", help="MLflow registered model name")
    p.add_argument("--stage", default=None, help="Optional stage to transition (e.g., Staging/Production)")

    # Train config
    p.add_argument("--test-size", type=float, default=0.2)
    p.add_argument("--random-state", type=int, default=42)
    p.add_argument("--cv", type=int, default=3, help="CV folds for tuning")
    p.add_argument("--tune-iter", type=int, default=10, help="RandomizedSearch iterations")
    return p


def _build_cc_agg_sql(db: str, cc_table: str, key: str, client) -> str:
    # Discover numeric columns in credit card table to aggregate
    cols = client.query(
        f"""
        SELECT name, type
        FROM system.columns
        WHERE database = %(db)s AND table = %(tbl)s
        """,
        parameters={"db": db, "tbl": cc_table},
    ).result_rows

    numeric_prefixes = ("Int", "UInt", "Float", "Decimal")
    num_cols: List[str] = [name for (name, ctype) in cols if name != key and ctype.startswith(numeric_prefixes)]

    # Keep it modest to avoid huge wide tables
    num_cols = num_cols[:50]
    if not num_cols:
        return f"SELECT {key} FROM {db}.{cc_table} GROUP BY {key}"

    aggs = ", ".join([f"avg({c}) AS cc_avg_{c}" for c in num_cols])
    return f"SELECT {key}, {aggs} FROM {db}.{cc_table} GROUP BY {key}"


def main() -> int:
    logger.remove()
    logger.add(lambda m: print(m, end=""), level="INFO")
    args = build_parser().parse_args()

    import clickhouse_connect

    logger.info("🔌 Connecting to ClickHouse: {}:{} (db={})\n", args.ch_host, args.ch_port, args.database)
    client = clickhouse_connect.get_client(
        host=args.ch_host,
        port=args.ch_port,
        username=args.ch_user,
        password=args.ch_password,
        database=args.database,
    )

    # Build credit card aggregation subquery dynamically
    logger.info("🧮 Building credit card aggregation subquery for table: {}\n", args.cc_table)
    cc_agg_sql = _build_cc_agg_sql(args.database, args.cc_table, args.join_key, client)

    limit_clause = f"LIMIT {int(args.sample)}" if args.sample and args.sample > 0 else ""

    # Assemble final SQL
    sql = f"""
    WITH cc AS (
        {cc_agg_sql}
    )
    SELECT
        a.*, t.TARGET,
        cc.* EXCEPT({args.join_key})
    FROM {args.database}.{args.app_table} AS a
    INNER JOIN {args.database}.{args.train_table} AS t
        ON a.{args.join_key} = t.{args.join_key}
    LEFT JOIN cc
        ON a.{args.join_key} = cc.{args.join_key}
    {limit_clause}
    """

    logger.info("📥 Querying dataset from ClickHouse...\n")
    df = client.query_df(sql)
    logger.info("✅ Retrieved rows: {}, columns: {}\n", df.shape[0], df.shape[1])

    # Basic validation
    if "TARGET" not in df.columns:
        raise ValueError("TARGET column not found in assembled dataset")

    # Split features/target
    y = df["TARGET"].astype(int)
    X = df.drop(columns=["TARGET"])  # Keep all other columns, including join key

    # Simple, robust preprocessing: numeric -> to_numeric + median fill; categorical -> fill + factorize codes
    from pandas.api.types import is_numeric_dtype

    def simple_preprocess(df_in: pd.DataFrame) -> pd.DataFrame:
        df = df_in.copy()
        for col in df.columns:
            if is_numeric_dtype(df[col]):
                df[col] = pd.to_numeric(df[col], errors="coerce")
                med = df[col].median()
                df[col] = df[col].fillna(med)
            else:
                df[col] = df[col].astype("string").fillna("__MISSING__")
                df[col] = pd.factorize(df[col], sort=False)[0]
        return df

    X_processed = simple_preprocess(X)

    from sklearn.model_selection import train_test_split, RandomizedSearchCV
    from sklearn.metrics import roc_auc_score
    from xgboost import XGBClassifier

    logger.info("✂️  Train/test split + randomized search ({} iters, cv={} )", args.tune_iter, args.cv)
    X_train, X_test, y_train, y_test = train_test_split(
        X_processed, y, test_size=args.test_size, random_state=args.random_state, stratify=y
    )

    clf = XGBClassifier(
        eval_metric="auc",
        n_jobs=-1,
        random_state=args.random_state,
        tree_method="hist",
    )

    param_dist = {
        "n_estimators": [200, 300, 400],
        "max_depth": [3, 4, 5, 6],
        "learning_rate": [0.03, 0.05, 0.07, 0.1],
        "subsample": [0.7, 0.8, 0.9, 1.0],
        "colsample_bytree": [0.6, 0.8, 1.0],
    }

    search = RandomizedSearchCV(
        estimator=clf,
        param_distributions=param_dist,
        n_iter=args.tune_iter,
        scoring="roc_auc",
        cv=args.cv,
        verbose=1,
        n_jobs=1,
        random_state=args.random_state,
    )

    logger.info("🚀 Tuning + training...")
    search.fit(X_train, y_train)
    best_clf = search.best_estimator_
    logger.info("✅ Best params: {}\n", search.best_params_)

    logger.info("📈 Evaluating on holdout test")
    proba = best_clf.predict_proba(X_test)[:, 1]
    auc = float(roc_auc_score(y_test, proba))
    logger.info("   AUC: {:.4f}\n", auc)

    # Log to MLflow
    import mlflow
    import mlflow.sklearn

    logger.info("📝 Logging to MLflow")
    mlflow.set_experiment(args.experiment)
    with mlflow.start_run() as run:
        mlflow.log_params(search.best_params_)
        mlflow.log_metric("auc", auc)

        # Input example limited to a small subset for signature
        input_example = X_train.iloc[:1]
        model_info = mlflow.sklearn.log_model(
            sk_model=best_clf,
            artifact_path="model",
            input_example=simple_preprocess(input_example),
            registered_model_name=args.register_name,
        )
        logger.info("   Run ID: {}", run.info.run_id)
        logger.info("   Tracking URI: {}", mlflow.get_tracking_uri())
        logger.info("   Artifact URI: {}", run.info.artifact_uri)

        if args.stage:
            client = mlflow.tracking.MlflowClient()
            version: Optional[str] = None
            for v in client.search_model_versions(f"name='{args.register_name}'"):
                if v.run_id == run.info.run_id:
                    version = v.version
                    break
            if version:
                logger.info("🔁 Transitioning model '{}' version {} -> {}", args.register_name, version, args.stage)
                client.transition_model_version_stage(
                    name=args.register_name,
                    version=str(version),
                    stage=args.stage,
                    archive_existing_versions=False,
                )
            else:
                logger.warning("Could not resolve registered model version for this run")

    logger.info("🏁 Done. AUC={:.4f}\n", auc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
