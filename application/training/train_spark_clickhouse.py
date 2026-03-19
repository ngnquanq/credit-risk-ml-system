#!/usr/bin/env python3
"""
PySpark training job: read mart tables from ClickHouse via JDBC, join, train a Spark ML model,
and register the model to MLflow. Intended to be submitted with spark-submit.

Example spark-submit (adjust packages/versions to your cluster):
    # These are same as before, but with Spark and ClickHouse JDBC/HTTP packages
  export MLFLOW_TRACKING_URI=http://localhost:5000
  export MLFLOW_S3_ENDPOINT_URL=http://localhost:9006
  export AWS_ACCESS_KEY_ID=minio_user
  export AWS_SECRET_ACCESS_KEY=minio_password

  spark-submit \
    --packages com.clickhouse:clickhouse-jdbc:0.4.6,com.clickhouse:clickhouse-http-client:0.4.6 \
    --driver-memory 4g \
    --executor-memory 4g \
    application/spark/train_spark_clickhouse.py \
      --ch-host ch-server --ch-port 8123 \
      --database application_mart \
      --app-table mart_application \
      --train-table mart_application_train \
      --cc-table mart_credit_card_balance \
      --join-key SK_ID_CURR \
      --experiment credit-risk \
      --register-name credit_risk_model_spark \
      --stage Staging

Environment variables expected for MLflow:
  MLFLOW_TRACKING_URI, MLFLOW_S3_ENDPOINT_URL, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
"""

from __future__ import annotations

import argparse
from typing import List, Optional

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql import types as T
from pyspark.ml import Pipeline
from pyspark.ml.feature import Imputer, StringIndexer, VectorAssembler
from pyspark.ml.classification import GBTClassifier
from pyspark.ml.evaluation import BinaryClassificationEvaluator


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Train Spark model from ClickHouse marts and register to MLflow")
    # ClickHouse connection
    p.add_argument("--ch-host", default="ch-server", help="ClickHouse host")
    p.add_argument("--ch-port", type=int, default=8123, help="ClickHouse HTTP port")
    p.add_argument("--ch-user", default="default", help="ClickHouse user")
    p.add_argument("--ch-password", default="", help="ClickHouse password")

    # Schema and tables
    p.add_argument("--database", default="application_mart", help="ClickHouse database name")
    p.add_argument("--app-table", default="mart_application", help="Application mart table (features)")
    p.add_argument("--train-table", default="mart_application_train", help="Training labels table (must contain TARGET)")
    p.add_argument("--cc-table", default="mart_credit_card_balance", help="Credit card balance mart table (aggregated)")
    p.add_argument("--join-key", default="SK_ID_CURR", help="Join key column shared by mart tables")

    # Data scope
    p.add_argument("--sample", type=int, default=0, help="Optional LIMIT for debugging (0 = no limit)")

    # MLflow
    p.add_argument("--experiment", default="credit-risk", help="MLflow experiment name")
    p.add_argument("--register-name", default="credit_risk_model_spark", help="MLflow registered model name")
    p.add_argument("--stage", default=None, help="Optional stage to transition (e.g., Staging/Production)")

    # Model params
    p.add_argument("--max-depth", type=int, default=5)
    p.add_argument("--max-iter", type=int, default=150)
    p.add_argument("--train-ratio", type=float, default=0.8)
    return p


def _jdbc_options(url: str, user: str, password: str) -> dict:
    return {
        "url": url,
        "user": user,
        "password": password,
        "driver": "com.clickhouse.jdbc.ClickHouseDriver",
    }


def _discover_numeric_columns(df: DataFrame, exclude: List[str]) -> List[str]:
    numeric_types = (
        T.ByteType, T.ShortType, T.IntegerType, T.LongType, T.FloatType, T.DoubleType, T.DecimalType,
    )
    out: List[str] = []
    for f in df.schema.fields:
        if f.name in exclude:
            continue
        if isinstance(f.dataType, numeric_types):
            out.append(f.name)
    return out


def build_spark() -> SparkSession:
    return (
        SparkSession.builder.appName("credit-risk-train-spark")
        # Tune or add configs here as needed
        .getOrCreate()
    )


def main() -> int:
    args = build_parser().parse_args()

    spark = build_spark()
    spark.sparkContext.setLogLevel("WARN")

    jdbc_url = f"jdbc:clickhouse://{args.ch_host}:{args.ch_port}/{args.database}"
    jdbc_opts = _jdbc_options(jdbc_url, args.ch_user, args.ch_password)

    print(f"[INFO] Reading tables from ClickHouse at {jdbc_url}")
    a_df = spark.read.format("jdbc").options(**jdbc_opts, dbtable=args.app_table).load()
    t_df = spark.read.format("jdbc").options(**jdbc_opts, dbtable=args.train_table).load()
    cc_df = spark.read.format("jdbc").options(**jdbc_opts, dbtable=args.cc_table).load()

    # Aggregate credit card numeric columns by join key with avg(), capped at 50 columns like the Python version
    print(f"[INFO] Aggregating credit card table '{args.cc_table}'")
    num_cols_cc = _discover_numeric_columns(cc_df, exclude=[args.join_key])[:50]
    if num_cols_cc:
        agg_exprs = [F.avg(c).alias(f"cc_avg_{c}") for c in num_cols_cc]
        cc_agg = cc_df.groupBy(args.join_key).agg(*agg_exprs)
    else:
        cc_agg = cc_df.select(args.join_key).distinct()

    print("[INFO] Joining mart tables")
    joined = (
        a_df.alias("a")
        .join(t_df.alias("t"), on=[F.col(f"a.{args.join_key}") == F.col(f"t.{args.join_key}")], how="inner")
        .join(cc_agg.alias("cc"), on=[F.col(f"a.{args.join_key}") == F.col(f"cc.{args.join_key}")], how="left")
        .drop(F.col(f"t.{args.join_key}"))
        .drop(F.col(f"cc.{args.join_key}"))
    )

    if args.sample and args.sample > 0:
        print(f"[INFO] Applying LIMIT {args.sample}")
        joined = joined.limit(int(args.sample))

    if "TARGET" not in joined.columns:
        raise RuntimeError("TARGET column not found after join")

    # Prepare label and features
    label_col = "TARGET"
    df = joined.withColumn(label_col, F.col(label_col).cast("double"))

    # Identify numeric/categorical columns dynamically (exclude join key and label)
    exclude_cols = {args.join_key, label_col}
    num_cols = []
    cat_cols = []
    for f in df.schema.fields:
        if f.name in exclude_cols:
            continue
        dt = f.dataType
        if isinstance(dt, (T.ByteType, T.ShortType, T.IntegerType, T.LongType, T.FloatType, T.DoubleType, T.DecimalType)):
            num_cols.append(f.name)
        elif isinstance(dt, T.BooleanType):
            num_cols.append(f.name)
        else:
            cat_cols.append(f.name)

    print(f"[INFO] Feature columns -> numeric={len(num_cols)}, categorical={len(cat_cols)}")

    # Cast numeric to double for Imputer
    for c in num_cols:
        df = df.withColumn(c, F.col(c).cast("double"))

    # Build feature engineering stages
    stages = []

    # Impute numeric columns
    if num_cols:
        imputer = Imputer(strategy="median", inputCols=num_cols, outputCols=[f"{c}__imputed" for c in num_cols])
        stages.append(imputer)
        num_out = [f"{c}__imputed" for c in num_cols]
    else:
        num_out = []

    # Index categoricals
    cat_indexed = []
    for c in cat_cols:
        idx = StringIndexer(inputCol=c, outputCol=f"{c}__idx", handleInvalid="keep")
        stages.append(idx)
        cat_indexed.append(f"{c}__idx")

    feature_cols = num_out + cat_indexed
    if not feature_cols:
        raise RuntimeError("No features identified after preprocessing")

    assembler = VectorAssembler(inputCols=feature_cols, outputCol="features", handleInvalid="keep")
    stages.append(assembler)

    clf = GBTClassifier(labelCol=label_col, featuresCol="features", maxDepth=args.max_depth, maxIter=args.max_iter)
    stages.append(clf)

    pipe = Pipeline(stages=stages)

    # Split
    train_ratio = max(0.1, min(0.95, float(args.train_ratio)))
    train_df, test_df = df.randomSplit([train_ratio, 1 - train_ratio], seed=42)
    print(f"[INFO] Train count={train_df.count()}, Test count={test_df.count()}")

    print("[INFO] Fitting Spark ML pipeline (GBTClassifier)")
    model = pipe.fit(train_df)

    print("[INFO] Evaluating on test set (AUC)")
    preds = model.transform(test_df)
    evaluator = BinaryClassificationEvaluator(labelCol=label_col, rawPredictionCol="rawPrediction", metricName="areaUnderROC")
    auc = float(evaluator.evaluate(preds))
    print(f"[INFO] Test AUC = {auc:.4f}")

    # Log to MLflow
    import mlflow
    import mlflow.spark

    mlflow.set_experiment(args.experiment)
    with mlflow.start_run() as run:
        mlflow.log_params({
            "gbt_maxDepth": args.max_depth,
            "gbt_maxIter": args.max_iter,
            "train_ratio": train_ratio,
            "num_features": len(feature_cols),
            "num_numeric": len(num_cols),
            "num_categorical": len(cat_cols),
        })
        mlflow.log_metric("auc", auc)

        mlflow.spark.log_model(
            spark_model=model,
            artifact_path="model",
            registered_model_name=args.register_name,
        )
        print(f"[INFO] MLflow run_id={run.info.run_id}")
        print(f"[INFO] Tracking URI={mlflow.get_tracking_uri()}")

        # Optional stage transition
        if args.stage:
            client = mlflow.tracking.MlflowClient()
            version: Optional[str] = None
            for v in client.search_model_versions(f"name='{args.register_name}'"):
                if v.run_id == run.info.run_id:
                    version = v.version
                    break
            if version:
                print(f"[INFO] Transitioning model '{args.register_name}' v{version} -> {args.stage}")
                client.transition_model_version_stage(
                    name=args.register_name,
                    version=str(version),
                    stage=args.stage,
                    archive_existing_versions=False,
                )
            else:
                print("[WARN] Could not resolve registered model version for this run")

    print(f"[INFO] Done. AUC={auc:.4f}")
    spark.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

