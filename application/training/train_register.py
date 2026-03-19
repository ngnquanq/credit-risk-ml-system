#!/usr/bin/env python3
"""
Train a preprocessing + model pipeline and register it to MLflow.

Defaults are aligned to the features you fetch from Feast in serving.

Usage (with MLflow stack up):
  export MLFLOW_TRACKING_URI=http://localhost:5000
  export MLFLOW_S3_ENDPOINT_URL=http://localhost:9006
  export AWS_ACCESS_KEY_ID=minio_user
  export AWS_SECRET_ACCESS_KEY=minio_password

  python application/training/train_register.py \
    --data data/complete_feature_dataset.csv \
    --register-name credit_risk_model \
    --experiment credit-risk \
    --stage Production
"""

from __future__ import annotations

import argparse
from typing import List

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder
from sklearn.base import BaseEstimator, TransformerMixin
from xgboost import XGBClassifier
from loguru import logger



def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Train + register model to MLflow")
    p.add_argument("--data", required=True, help="Path to application_train.csv")
    p.add_argument("--experiment", default="credit-risk", help="MLflow experiment name")
    p.add_argument("--register-name", default="credit_risk_model", help="MLflow registered model name")
    p.add_argument("--stage", default=None, help="Optional stage to transition (e.g., Production)")
    p.add_argument("--test-size", type=float, default=0.2)
    p.add_argument("--random-state", type=int, default=42)
    return p


def main() -> int:
    logger.remove()
    logger.add(lambda msg: print(msg, end=""), level="INFO")
    args = build_parser().parse_args()
    logger.info(f"📥 Loading data from: {args.data}\n")
    df = pd.read_csv(args.data)
    # Ensure expected columns exist
    target_col = "TARGET"
    if target_col not in df.columns:
        raise ValueError(f"TARGET column not found in {args.data}")

    # Exact feature set provided (uppercase, as in the dataset)
    FEATURES: List[str] = [
        "EXT_SOURCE_3",
        "EXT_SOURCE_2",
        "EXT_SOURCE_1",
        "DAYS_BIRTH",
        "AMT_GOODS_PRICE",
        "AMT_CREDIT",
        "AMT_ANNUITY",
        "DAYS_EMPLOYED",
        "CODE_GENDER",
        "BUREAU_DEBT_TO_CREDIT_RATIO",
        "BUREAU_ACTIVE_CREDIT_SUM",
        "NAME_EDUCATION_TYPE",
        "POS_MEAN_CONTRACT_LENGTH",
        "PREV_ANNUITY_MEAN",
        "PREV_GOODS_TO_CREDIT_RATIO",
        "NAME_FAMILY_STATUS",
        "POS_LATEST_MONTH",
        "ORGANIZATION_TYPE",
        "BUREAU_AMT_MAX_OVERDUE_EVER",
        "POS_TOTAL_MONTHS_OBSERVED",
        "AMT_INCOME_TOTAL",
        "PREV_REFUSAL_RATE",
        "NAME_INCOME_TYPE",
        "CNT_CHILDREN"
    ]

    missing_feat = [c for c in FEATURES if c not in df.columns]
    if missing_feat:
        raise ValueError(f"Missing expected feature columns: {missing_feat}")

    # Identify categorical subset from the provided list
    cat_cols: List[str] = [
        "CODE_GENDER",
        "NAME_EDUCATION_TYPE",
        "NAME_FAMILY_STATUS",
        "ORGANIZATION_TYPE",
        "NAME_INCOME_TYPE",
    ]
    num_cols: List[str] = [c for c in FEATURES if c not in cat_cols]

    missing = [c for c in num_cols + cat_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns in data: {missing}")

    logger.info("🔎 Validating columns present and splitting features/target\n")
    X = df[FEATURES]
    y = df[target_col].astype(int)

    logger.info("✂️  Train/test split (stratified)")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=args.test_size, random_state=args.random_state, stratify=y
    )
    logger.info(f"   Train: {X_train.shape}, Test: {X_test.shape}\n")

    class ReplaceInf(BaseEstimator, TransformerMixin):
        def fit(self, X, y=None):
            return self
        def transform(self, X):
            return pd.DataFrame(X, columns=self.features_) if hasattr(self, 'features_') else pd.DataFrame(X)
        def set_output(self, *, transform=None):
            return self

    class ClipQuantiles(BaseEstimator, TransformerMixin):
        def __init__(self, qlow=0.001, qhigh=0.999):
            self.qlow = qlow
            self.qhigh = qhigh
        def fit(self, X, y=None):
            Xdf = pd.DataFrame(X)
            self.lower_ = Xdf.quantile(self.qlow, interpolation="nearest")
            self.upper_ = Xdf.quantile(self.qhigh, interpolation="nearest")
            return self
        def transform(self, X):
            Xdf = pd.DataFrame(X).clip(self.lower_, self.upper_, axis=1)
            return Xdf.values

    # Specialized imputers per business logic for PREV_ columns
    prev_ratio_cols = [c for c in num_cols if c.startswith("PREV_") and ("RATIO" in c or "RATE" in c)]
    prev_other_cols = [c for c in num_cols if c.startswith("PREV_") and c not in prev_ratio_cols]
    other_num_cols = [c for c in num_cols if not c.startswith("PREV_")]

    logger.info("🧹 Building preprocessing pipelines (clip + impute + encode)")
    # Column-wise pipelines
    num_prev_ratio_pipe = Pipeline([
        ("clip", ClipQuantiles()),
        ("impute", SimpleImputer(strategy="median")),
    ])
    num_prev_other_pipe = Pipeline([
        ("clip", ClipQuantiles()),
        ("impute", SimpleImputer(strategy="constant", fill_value=0)),
    ])
    num_other_pipe = Pipeline([
        ("clip", ClipQuantiles()),
        ("impute", SimpleImputer(strategy="median")),
    ])
    cat_pipe = Pipeline([
        ("impute", SimpleImputer(strategy="most_frequent")),
        ("ord", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)),
    ])

    transformers = []
    if other_num_cols:
        transformers.append(("num_other", num_other_pipe, other_num_cols))
    if prev_ratio_cols:
        transformers.append(("num_prev_ratio", num_prev_ratio_pipe, prev_ratio_cols))
    if prev_other_cols:
        transformers.append(("num_prev_other", num_prev_other_pipe, prev_other_cols))
    if cat_cols:
        transformers.append(("cat", cat_pipe, cat_cols))

    pre = ColumnTransformer(transformers, remainder="drop")
    logger.info("🔧 Estimator: XGBoost (n_estimators=300, max_depth=4, lr=0.05)")

    clf = XGBClassifier(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="logloss",
        n_jobs=-1,
        random_state=args.random_state,
    )

    pipe = Pipeline([("pre", pre), ("clf", clf)])

    logger.info("🚀 Training pipeline...")
    pipe.fit(X_train, y_train)
    logger.info("✅ Training complete")
    
    logger.info("📈 Evaluating metrics on test set")
    proba = pipe.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, proba)
    preds = (proba >= 0.3).astype(int)
    acc = float((preds == y_test.to_numpy()).mean())
    logger.info(f"   AUC: {auc:.4f}, Accuracy@0.3: {acc:.4f}\n")

    # Log to MLflow
    import mlflow
    import mlflow.sklearn

    logger.info("📝 Logging to MLflow")
    mlflow.set_experiment(args.experiment)
    with mlflow.start_run() as run:
        mlflow.log_params({
            "n_estimators": clf.n_estimators,
            "max_depth": clf.max_depth,
            "learning_rate": clf.learning_rate,
            "subsample": clf.subsample,
            "colsample_bytree": clf.colsample_bytree,
        })
        mlflow.log_metric("auc", float(auc))
        mlflow.log_metric("accuracy_threshold_0.3", float(acc))

        # Input example for signature
        input_example = X_train.iloc[:1]
        model_info = mlflow.sklearn.log_model(
            sk_model=pipe,
            artifact_path="model",
            input_example=input_example,
            registered_model_name=args.register_name,
        )
        logger.info(f"   Run ID: {run.info.run_id}")
        logger.info(f"   Tracking URI: {mlflow.get_tracking_uri()}")
        logger.info(f"   Artifact URI: {run.info.artifact_uri}")
        logger.info(f"   Logged model URI: {getattr(model_info, 'model_uri', 'n/a')}\n")

        # Optionally transition to stage
        if args.stage:
            client = mlflow.tracking.MlflowClient()
            # Find the version registered for this run id
            version = None
            for v in client.search_model_versions(f"name='{args.register_name}'"):
                if v.run_id == run.info.run_id:
                    version = v.version
                    break
            if version is None:
                logger.warning("Could not resolve model version for this run; skipping stage transition")
            else:
                logger.info(f"🔁 Transitioning model '{args.register_name}' version {version} -> {args.stage}")
                client.transition_model_version_stage(
                    name=args.register_name,
                    version=str(version),
                    stage=args.stage,
                    archive_existing_versions=False,
                )

    logger.info(f"🏁 Run complete. AUC={auc:.4f}, Accuracy@0.3={acc:.4f}. Registered under '{args.register_name}'.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
