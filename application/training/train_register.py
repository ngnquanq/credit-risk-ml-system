#!/usr/bin/env python3
"""
NOT RELATED TO THE ACTUAL TRAINING PIPELINE, THIS IS FOR LOCAL ONLY

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
from pathlib import Path
from typing import List, Optional

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder
from xgboost import XGBClassifier
from loguru import logger

try:
    from catboost import CatBoostClassifier
    CATBOOST_AVAILABLE = True
except ImportError:
    CATBOOST_AVAILABLE = False



def ece_score(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
    """Expected Calibration Error — must stay in sync with notebook/model_pipeline.py."""
    y_true = np.asarray(y_true)
    y_prob = np.asarray(y_prob)
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (y_prob >= lo) & (y_prob < hi)
        if mask.sum() == 0:
            continue
        ece += mask.mean() * abs(y_true[mask].mean() - y_prob[mask].mean())
    return float(ece)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Train + register model to MLflow")
    p.add_argument("--data", required=True, help="Path to complete_feature_dataset.csv")
    p.add_argument("--config", default=None,
                   help="Path to best_model_config.json from notebook/model_pipeline.py. "
                        "When provided, overrides hardcoded hyperparameters.")
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

    # ── Load model config (from notebook/model_pipeline.py output) ──────────
    if args.config:
        model_config = json.loads(Path(args.config).read_text())
        MODEL_TYPE        = model_config.get("model_type", "xgboost")
        MODEL_PARAMS      = dict(model_config["hyperparameters"])
        CALIBRATION_METHOD: Optional[str] = model_config.get("calibration_method")
        THRESHOLD         = float(model_config.get("threshold", 0.3))
        logger.info(
            f"📋 Loaded config from {args.config}\n"
            f"   model={MODEL_TYPE}  calibration={CALIBRATION_METHOD}  threshold={THRESHOLD}\n"
            f"   CV AUC (dev) = {model_config.get('cv_auc_mean', 'n/a'):.4f} "
            f"± {model_config.get('cv_auc_std', 0):.4f}\n"
        )
    else:
        MODEL_TYPE        = "xgboost"
        MODEL_PARAMS      = {
            "n_estimators": 300, "max_depth": 4, "learning_rate": 0.05,
            "subsample": 0.8, "colsample_bytree": 0.8,
        }
        CALIBRATION_METHOD = None
        THRESHOLD          = 0.3
        logger.warning(
            "⚠️  No --config provided. Using hardcoded fallback XGBoost params.\n"
            "   Run notebook/model_pipeline.py first to generate best_model_config.json.\n"
        )

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

    # ── Construct classifier ─────────────────────────────────────────────────
    if MODEL_TYPE == "catboost":
        if not CATBOOST_AVAILABLE:
            raise ImportError(
                "CatBoost not installed but config requests it. "
                "Run: pip install catboost"
            )
        cat_params = {k: v for k, v in MODEL_PARAMS.items() if k != "scale_pos_weight"}
        scale_pw = MODEL_PARAMS.get("scale_pos_weight",
                                     float((y_train == 0).sum() / max((y_train == 1).sum(), 1)))
        clf = CatBoostClassifier(
            **cat_params,
            class_weights=[1.0, scale_pw],
            verbose=False,
            random_seed=args.random_state,
        )
        logger.info(f"🔧 Estimator: CatBoost  params={cat_params}")
    else:
        clf = XGBClassifier(
            **MODEL_PARAMS,
            eval_metric="logloss",
            n_jobs=-1,
            random_state=args.random_state,
        )
        logger.info(f"🔧 Estimator: XGBoost  params={MODEL_PARAMS}")

    pipe: Pipeline | CalibratedClassifierCV = Pipeline([("pre", pre), ("clf", clf)])

    if CALIBRATION_METHOD:
        logger.info(f"🎯 Wrapping in CalibratedClassifierCV (method={CALIBRATION_METHOD}, cv=5)")
        pipe = CalibratedClassifierCV(pipe, method=CALIBRATION_METHOD, cv=5)

    logger.info("🚀 Training pipeline...")
    pipe.fit(X_train, y_train)
    logger.info("✅ Training complete")
    
    logger.info("📈 Evaluating metrics on test set")
    proba = pipe.predict_proba(X_test)[:, 1]
    y_np  = y_test.to_numpy()

    # Threshold < 0.5 prioritises recall over precision — a missed default (FN) incurs
    # higher expected loss than a declined creditworthy applicant (FP).
    preds     = (proba >= THRESHOLD).astype(int)
    auc       = roc_auc_score(y_np, proba)
    aucpr     = average_precision_score(y_np, proba)
    brier     = brier_score_loss(y_np, proba)
    ece       = ece_score(y_np, proba)
    acc       = float((preds == y_np).mean())
    precision = precision_score(y_np, preds, zero_division=0)
    recall    = recall_score(y_np, preds, zero_division=0)
    f1        = f1_score(y_np, preds, zero_division=0)

    logger.info(f"   AUC-ROC:   {auc:.4f}")
    logger.info(f"   AUC-PR:    {aucpr:.4f}")
    logger.info(f"   Brier:     {brier:.4f}  (lower = better calibrated probabilities)")
    logger.info(f"   ECE:       {ece:.4f}  (mean calibration gap across 10 bins)")
    logger.info(f"   Threshold: {THRESHOLD}")
    logger.info(f"   Precision: {precision:.4f}  (of predicted defaults, how many are real)")
    logger.info(f"   Recall:    {recall:.4f}  (of real defaults, how many we caught)")
    logger.info(f"   F1:        {f1:.4f}")
    logger.info(f"   Accuracy:  {acc:.4f}\n")

    # Log to MLflow
    import mlflow
    import mlflow.sklearn

    logger.info("📝 Logging to MLflow")
    mlflow.set_experiment(args.experiment)
    with mlflow.start_run() as run:
        mlflow.log_params({
            **{f"model_{k}": v for k, v in MODEL_PARAMS.items()},
            "model_type":          MODEL_TYPE,
            "calibration_method":  CALIBRATION_METHOD or "none",
            "threshold":           THRESHOLD,
        })
        mlflow.log_metric("auc",       float(auc))
        mlflow.log_metric("aucpr",     float(aucpr))
        mlflow.log_metric("brier",     float(brier))
        mlflow.log_metric("ece",       float(ece))
        mlflow.log_metric("precision", float(precision))
        mlflow.log_metric("recall",    float(recall))
        mlflow.log_metric("f1",        float(f1))
        mlflow.log_metric("accuracy",  float(acc))

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

        # Generate feast_metadata.yaml — consumed by the scoring service at startup to:
        #   1. Validate that all required features are present in the Feast registry
        #   2. Build the feature_refs list for online store lookup
        #   3. Map Feast feature names (lowercase) -> model column names (uppercase)
        # This artifact is the contract between training and serving; without it the
        # scoring service raises RuntimeError on startup.
        feast_metadata = {
            "selected_features": FEATURES,
            "num_features": len(FEATURES),
            "cat_features": cat_cols,
            "num_features_list": num_cols,
            "threshold": THRESHOLD,
            "training_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "model_signature": {
                "inputs": FEATURES,  # uppercase column names expected by the sklearn pipeline
            },
            # feature_mapping and feast_feature_refs are resolved dynamically at serving
            # startup by querying the live Feast registry — no hardcoding needed here.
            "feature_mapping": {f.lower(): f for f in FEATURES},
        }
        feast_metadata_path = "/tmp/feast_metadata.yaml"
        import yaml
        with open(feast_metadata_path, "w") as f:
            yaml.dump(feast_metadata, f, default_flow_style=False, sort_keys=False)
        mlflow.log_artifact(feast_metadata_path, artifact_path="model")
        logger.info(f"   Logged feast_metadata.yaml ({len(FEATURES)} features)\n")

        # Log the config JSON for full reproducibility traceability
        if args.config and Path(args.config).exists():
            mlflow.log_artifact(args.config, artifact_path="model")
            logger.info(f"   Logged config artifact: {args.config}\n")

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
