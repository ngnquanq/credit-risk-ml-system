from kfp import dsl
from kfp.dsl import component, Input, Output, Dataset


@component(
    base_image="python:3.11-slim",
    packages_to_install=["boto3==1.40.26"],
)
def fetch_minio_snapshot(
    s3_endpoint: str,
    bucket: str,
    object_key: str,
    aws_access_key_id: str,
    aws_secret_access_key: str,
    output_csv: Output[Dataset],
):
    """
    Download a CSV from MinIO/S3 into the provided artifact path.
    The artifact is then passed to downstream steps.
    """
    import os
    import sys
    import boto3
    import botocore

    session = boto3.session.Session()
    s3 = session.client(
        service_name="s3",
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        endpoint_url=s3_endpoint,
        config=botocore.client.Config(signature_version="s3v4"),
        verify=False,
    )
    local_path = output_csv.path
    # Ensure parent dir exists
    os.makedirs(os.path.dirname(local_path), exist_ok=True)

    # Helpful diagnostics before download
    print(f"[fetch_minio_snapshot] endpoint={s3_endpoint} bucket={bucket} key={object_key}")
    try:
        # Validate bucket exists
        s3.head_bucket(Bucket=bucket)
    except Exception as e:
        print(f"[fetch_minio_snapshot] head_bucket failed: {e}", file=sys.stderr)
        raise

    try:
        s3.download_file(bucket, object_key, local_path)
        print(f"[fetch_minio_snapshot] downloaded to {local_path} ({os.path.getsize(local_path)} bytes)")
    except Exception as e:
        print(f"[fetch_minio_snapshot] download failed: {e}", file=sys.stderr)
        # Optional: list bucket keys prefix to aid debugging
        try:
            prefix = os.path.dirname(object_key).rstrip('/')
            if prefix:
                resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
            else:
                resp = s3.list_objects_v2(Bucket=bucket, MaxKeys=20)
            keys = [c.get('Key') for c in (resp.get('Contents') or [])]
            print(f"[fetch_minio_snapshot] sample keys under '{prefix or bucket}': {keys[:10]}")
        except Exception as le:
            print(f"[fetch_minio_snapshot] listing keys failed too: {le}", file=sys.stderr)
        raise


@component(
    base_image="python:3.11-slim",
    packages_to_install=[
        "pandas==2.2.2",
        "scikit-learn==1.5.1",
        "xgboost==2.1.0",
    ],
)
def tune_hyperparams(data: Input[Dataset], config_json: str = "{}") -> str:
    """
    Skeleton grid search for XGBoost AUC. Returns JSON string of best params.
    Replace later with Katib or a richer search.
    """
    import json
    import pandas as pd
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import roc_auc_score
    from xgboost import XGBClassifier

    df = pd.read_csv(data.path)
    target_col = "TARGET"
    if target_col not in df.columns:
        raise ValueError("TARGET column not found in data")

    # Basic feature subset (adjust to your data schema)
    FEATURES = [c for c in df.columns if c != target_col]
    X = df[FEATURES]
    y = df[target_col].astype(int)

    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    cfg = json.loads(config_json) if config_json else {}
    base_params = cfg.get("base_params", {
        "eval_metric": "logloss",
        "n_jobs": -1,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "random_state": 42
    })

    search_space = cfg.get("grid_search", [
        {"n_estimators": 300, "max_depth": 6, "learning_rate": 0.05},
        {"n_estimators": 400, "max_depth": 4, "learning_rate": 0.03},
    ])

    best = {"auc": -1.0, "params": None}
    for p in search_space:
        clf = XGBClassifier(**{**base_params, **p})
        clf.fit(X_train, y_train)
        proba = clf.predict_proba(X_val)[:, 1]
        auc = float(roc_auc_score(y_val, proba))
        if auc > best["auc"]:
            best = {"auc": auc, "params": p}

    return json.dumps(best["params"]) if best["params"] else json.dumps({})


@component(
    # Match Ray cluster runtime (Ray 2.31.0 on Python 3.9)
    base_image="rayproject/ray:2.31.0-py39",
    packages_to_install=[
        "pandas==2.2.2",
        "scikit-learn==1.5.1",
        "xgboost==2.1.0",
    ],
)
def ray_tune_hyperparams(
    data: Input[Dataset],
    config_json: str = "{}",
    num_samples: int = 12,
    cpus_per_trial: float = 1.0,
    gpus_per_trial: float = 0.0,
    ray_address: str = "",
) -> str:
    """
    Distributed (or parallel) hyperparameter tuning using Ray Tune via tune-sklearn.
    - If `ray_address` is provided, connects to an existing Ray cluster (e.g., KubeRay);
      otherwise starts a local Ray runtime inside the pod and parallelizes across CPUs.
    Returns best params as JSON.
    """
    import json
    import os
    import pandas as pd
    import ray
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import roc_auc_score
    from sklearn.compose import ColumnTransformer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OrdinalEncoder, FunctionTransformer
    from sklearn.impute import SimpleImputer
    from xgboost import XGBClassifier
    from ray.tune.schedulers import ASHAScheduler

    # Connect/start Ray
    if ray_address:
        ray.init(address=ray_address, ignore_reinit_error=True, namespace=os.getenv("RAY_NAMESPACE", "kfp"))
    else:
        ray.init(ignore_reinit_error=True)

    cfg = json.loads(config_json) if config_json else {}
    base = cfg.get("base_params", dict(
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="logloss",
        n_jobs=-1,
        random_state=42,
    ))

    # Define search space
    from ray import tune

    # Objective function for Ray Tune
    def train_eval(config):
        # Load data inside the trainable to avoid capturing large arrays in the closure
        import pandas as pd
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import roc_auc_score
        from sklearn.compose import ColumnTransformer
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import OrdinalEncoder
        from sklearn.impute import SimpleImputer
        from xgboost import XGBClassifier
        from ray.air import session

        df = pd.read_csv(data.path, low_memory=False)
        target_col = "TARGET"
        if target_col not in df.columns:
            raise ValueError("TARGET column not found in data")

        cat_cols = [c for c in df.columns if df[c].dtype == "object" and c != target_col]
        FEATURES = [c for c in df.columns if c != target_col]
        num_cols = [c for c in FEATURES if c not in cat_cols]

        X = df[FEATURES]
        y = df[target_col].astype(int)
        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=0.2, stratify=y, random_state=42
        )

        num_pipe = Pipeline([("impute", SimpleImputer(strategy="median"))])
        cat_pipe = Pipeline([
            ("impute", SimpleImputer(strategy="most_frequent")),
            ("ord", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)),
        ])
        transformers = []
        if num_cols:
            transformers.append(("num", num_pipe, num_cols))
        if cat_cols:
            transformers.append(("cat", cat_pipe, cat_cols))
        pre = ColumnTransformer(transformers, remainder="drop")

        # Build model with current config
        params = {
            **base,
            "n_estimators": int(config.get("n_estimators", 300)),
            "max_depth": int(config.get("max_depth", 4)),
            "learning_rate": float(config.get("learning_rate", 0.05)),
            "min_child_weight": int(config.get("min_child_weight", 1)),
            "gamma": float(config.get("gamma", 0.0)),
        }
        model = Pipeline([("pre", pre), ("clf", XGBClassifier(**params))])
        model.fit(X_train, y_train)
        proba = model.predict_proba(X_val)[:, 1]
        auc = float(roc_auc_score(y_val, proba))
        session.report({"auc": auc})

    ray_search = cfg.get("ray_search", {
        "n_estimators": [200, 600],
        "max_depth": [3, 9],
        "learning_rate": [0.01, 0.2],
        "min_child_weight": [1, 6],
        "gamma": [0.0, 0.3]
    })
    
    search_space = {
        "n_estimators": tune.randint(ray_search["n_estimators"][0], ray_search["n_estimators"][1]),
        "max_depth": tune.randint(ray_search["max_depth"][0], ray_search["max_depth"][1]),
        "learning_rate": tune.loguniform(ray_search["learning_rate"][0], ray_search["learning_rate"][1]),
        "min_child_weight": tune.randint(ray_search["min_child_weight"][0], ray_search["min_child_weight"][1]),
        "gamma": tune.uniform(ray_search["gamma"][0], ray_search["gamma"][1]),
    }

    trainable = tune.with_resources(train_eval, {"cpu": cpus_per_trial, "gpu": gpus_per_trial})
    scheduler = ASHAScheduler(max_t=1, grace_period=1, reduction_factor=2)
    tuner = tune.Tuner(
        trainable,
        tune_config=tune.TuneConfig(
            metric="auc",
            mode="max",
            num_samples=num_samples,
            scheduler=scheduler,
        ),
        param_space=search_space,
    )
    results = tuner.fit()
    best = results.get_best_result(metric="auc", mode="max")
    best_cfg = best.config or {}
    mapped = {
        "n_estimators": int(best_cfg.get("n_estimators", 300)),
        "max_depth": int(best_cfg.get("max_depth", 4)),
        "learning_rate": float(best_cfg.get("learning_rate", 0.05)),
        "min_child_weight": int(best_cfg.get("min_child_weight", 1)),
        "gamma": float(best_cfg.get("gamma", 0.0)),
    }
    return json.dumps(mapped)


@component(
    base_image="python:3.11-slim",
    packages_to_install=[
        "pandas==2.2.2",
        "numpy==1.26.4",
        "scikit-learn==1.5.1",
        "xgboost==2.1.0",
        "mlflow==2.14.3",
        "pyyaml==6.0.1",
    ],
)
def train_and_register(
    data: Input[Dataset],
    best_params_json: str,
    experiment: str,
    register_name: str,
    stage: str,
    mlflow_tracking_uri: str,
    mlflow_s3_endpoint_url: str,
    aws_access_key_id: str,
    aws_secret_access_key: str,
    config_json: str = "{}",
    entity_key: str = "SK_ID_CURR",
    n_bootstrap: int = 1000,
    ci_level: float = 0.95,
    decision_threshold: float = 0.3,
) -> str:
    """
    Train with provided params and register to MLflow.
    Evaluates metrics using bootstrap resampling to produce confidence intervals.
    Logs simplified feast_metadata.yaml (serving discovers feature views dynamically).
    """
    import os
    import json
    import yaml
    import numpy as np
    import pandas as pd
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OrdinalEncoder, FunctionTransformer
    from sklearn.metrics import roc_auc_score, precision_score, recall_score
    from xgboost import XGBClassifier
    import mlflow
    import mlflow.sklearn

    def bootstrap_evaluate(y_true, y_proba, n_bootstrap, ci_level, threshold):
        """Compute metrics with bootstrap confidence intervals.

        Resamples the test set predictions with replacement ``n_bootstrap``
        times and computes AUC, accuracy, precision, and recall on each
        sample.  Returns point estimates and CI bounds for every metric.
        """
        rng = np.random.RandomState(42)
        n = len(y_true)
        y_true = np.asarray(y_true)
        y_proba = np.asarray(y_proba)
        y_pred = (y_proba >= threshold).astype(int)

        aucs, accs, precisions, recalls = [], [], [], []

        for _ in range(n_bootstrap):
            idx = rng.randint(0, n, size=n)
            bt_true = y_true[idx]
            bt_proba = y_proba[idx]
            bt_pred = y_pred[idx]

            # Skip degenerate samples (single class)
            if len(np.unique(bt_true)) < 2:
                continue

            aucs.append(float(roc_auc_score(bt_true, bt_proba)))
            accs.append(float((bt_pred == bt_true).mean()))
            precisions.append(float(precision_score(bt_true, bt_pred, zero_division=0)))
            recalls.append(float(recall_score(bt_true, bt_pred, zero_division=0)))

        alpha = 1 - ci_level
        lo = alpha / 2 * 100
        hi = (1 - alpha / 2) * 100

        def summarize(values):
            arr = np.array(values)
            return {
                "mean": float(np.mean(arr)),
                "std": float(np.std(arr)),
                "lower": float(np.percentile(arr, lo)),
                "upper": float(np.percentile(arr, hi)),
            }

        return {
            "auc": summarize(aucs),
            "accuracy": summarize(accs),
            "precision": summarize(precisions),
            "recall": summarize(recalls),
        }

    os.environ["MLFLOW_TRACKING_URI"] = mlflow_tracking_uri
    os.environ["MLFLOW_S3_ENDPOINT_URL"] = mlflow_s3_endpoint_url
    os.environ["AWS_ACCESS_KEY_ID"] = aws_access_key_id
    os.environ["AWS_SECRET_ACCESS_KEY"] = aws_secret_access_key

    df = pd.read_csv(data.path, low_memory=False)
    target_col = "TARGET"
    if target_col not in df.columns:
        raise ValueError("TARGET column not found in data")

    # Feature preparation
    cat_cols = [c for c in df.columns if df[c].dtype == "object" and c != target_col]
    FEATURES = [c for c in df.columns if c != target_col]
    num_cols = [c for c in FEATURES if c not in cat_cols]

    X = df[FEATURES]
    y = df[target_col].astype(int)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # Build pipeline - convert categorical columns to string before pipeline
    # This avoids unpicklable FunctionTransformer with custom functions
    if cat_cols:
        for col in cat_cols:
            X_train[col] = X_train[col].astype(str)
            X_test[col] = X_test[col].astype(str)

    num_pipe = Pipeline([("impute", SimpleImputer(strategy="median"))])
    cat_pipe = Pipeline([
        ("impute", SimpleImputer(strategy="most_frequent")),
        ("ord", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)),
    ])

    transformers = []
    if num_cols:
        transformers.append(("num", num_pipe, num_cols))
    if cat_cols:
        transformers.append(("cat", cat_pipe, cat_cols))
    pre = ColumnTransformer(transformers, remainder="drop")

    cfg = json.loads(config_json) if config_json else {}
    base = cfg.get("base_params", dict(
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="logloss",
        n_jobs=-1,
        random_state=42,
    ))

    params = json.loads(best_params_json) if best_params_json else {}
    base.update(params)
    clf = XGBClassifier(**base)
    pipe = Pipeline([("pre", pre), ("clf", clf)])

    pipe.fit(X_train, y_train)
    proba = pipe.predict_proba(X_test)[:, 1]

    # Point estimates
    auc = float(roc_auc_score(y_test, proba))
    preds = (proba >= decision_threshold).astype(int)
    accuracy = float((preds == y_test.to_numpy()).mean())

    # Bootstrap confidence intervals
    print(f"Running {n_bootstrap} bootstrap iterations for {ci_level*100:.0f}% CI...")
    boot = bootstrap_evaluate(y_test.to_numpy(), proba, n_bootstrap, ci_level, decision_threshold)
    print(f"  AUC: {auc:.4f} [{boot['auc']['lower']:.4f}, {boot['auc']['upper']:.4f}]")
    print(f"  Accuracy@{decision_threshold}: {accuracy:.4f} [{boot['accuracy']['lower']:.4f}, {boot['accuracy']['upper']:.4f}]")
    print(f"  Precision@{decision_threshold}: {boot['precision']['mean']:.4f} [{boot['precision']['lower']:.4f}, {boot['precision']['upper']:.4f}]")
    print(f"  Recall@{decision_threshold}: {boot['recall']['mean']:.4f} [{boot['recall']['lower']:.4f}, {boot['recall']['upper']:.4f}]")

    mlflow.set_experiment(experiment)
    with mlflow.start_run() as run:
        mlflow.log_params(base)
        mlflow.log_params({
            "n_bootstrap": n_bootstrap,
            "ci_level": ci_level,
            "decision_threshold": decision_threshold,
        })

        # Point estimates
        mlflow.log_metric("auc", auc)
        mlflow.log_metric("accuracy", accuracy)

        # Bootstrap CI for each metric
        for metric_name, stats in boot.items():
            mlflow.log_metric(f"{metric_name}_mean", stats["mean"])
            mlflow.log_metric(f"{metric_name}_std", stats["std"])
            mlflow.log_metric(f"{metric_name}_ci_lower", stats["lower"])
            mlflow.log_metric(f"{metric_name}_ci_upper", stats["upper"])

        input_example = X_train.iloc[:1]
        model_info = mlflow.sklearn.log_model(
            sk_model=pipe,
            artifact_path="model",
            input_example=input_example,
            registered_model_name=register_name,
        )
        feast_metadata = {
            "selected_features": [f.lower() for f in FEATURES],  # Features the model needs (serving discovers which views have them)
            "entity_key": entity_key.lower(),  # Entity key for Feast queries
            "num_features": len(FEATURES),
            "categorical_features": [c.lower() for c in cat_cols],
            "numerical_features": [c.lower() for c in num_cols],
            "model_signature": {
                "inputs": list(X_train.columns),
                "output": "binary_classification",
            },
            "training_date": pd.Timestamp.now().isoformat(),
        }
        # Log as YAML artifact
        with open("feast_metadata.yaml", "w") as f:
            yaml.dump(feast_metadata, f, default_flow_style=False)
        mlflow.log_artifact("feast_metadata.yaml")

        # Log bootstrap summary as artifact for detailed review
        boot_summary = {
            "n_bootstrap": n_bootstrap,
            "ci_level": ci_level,
            "decision_threshold": decision_threshold,
            "metrics": boot,
        }
        with open("bootstrap_metrics.yaml", "w") as f:
            yaml.dump(boot_summary, f, default_flow_style=False)
        mlflow.log_artifact("bootstrap_metrics.yaml")

        print(f"Logged feast_metadata.yaml with {len(FEATURES)} features")
        print(f"Logged bootstrap_metrics.yaml ({n_bootstrap} iterations, {ci_level*100:.0f}% CI)")

        # Promote to stage via tag (MLflow 3.x compatible)
        # Setting tag stage=Production triggers the MLflow Watcher → Bento build → KServe deploy
        if stage:
            client = mlflow.tracking.MlflowClient()
            version = None
            for v in client.search_model_versions(f"name='{register_name}'"):
                if v.run_id == run.info.run_id:
                    version = v.version
                    break
            if version is not None:
                client.set_model_version_tag(register_name, version, "stage", stage)
                print(f"Promoted version {version} to stage={stage} (MLflow Watcher will trigger)")
                try:
                    client.set_registered_model_alias(register_name, "champion", version)
                    print(f"Set alias 'champion' -> version {version}")
                except Exception as e:
                    print(f"Warning: could not set alias: {e}")
            else:
                print(f"Warning: could not find registered version for run {run.info.run_id}")
        else:
            print(f"Stage not set — model registered but NOT promoted (MLflow Watcher will not trigger)")
            print(f"To promote later, run: python promote_model.py --version <N>")
        return run.info.run_id


import os
import json
import yaml

_config_path = os.path.join(os.path.dirname(__file__), "training_param.yaml")
try:
    with open(_config_path, "r") as f:
        DEFAULT_CONFIG_JSON = json.dumps(yaml.safe_load(f))
except Exception:
    DEFAULT_CONFIG_JSON = "{}"

@dsl.pipeline(name="credit-risk-training-pipeline")
def training_pipeline(
    config_json: str = DEFAULT_CONFIG_JSON,
    s3_endpoint: str = "http://training-minio.training-data.svc.cluster.local:9000",
    bucket: str = "training-data",
    object_key: str = "snapshots/ds=2025-09-19/loan_applications.csv",
    mlflow_tracking_uri: str = "http://mlflow.model-registry.svc.cluster.local:80",
    mlflow_s3_endpoint_url: str = "http://minio.model-registry.svc.cluster.local:9000",
    aws_access_key_id: str = "minioadmin",
    aws_secret_access_key: str = "minioadmin",
    experiment: str = "credit-risk",
    register_name: str = "credit_risk_model",
    stage: str = "",  # Set to "Production" to auto-promote and trigger MLflow Watcher; leave empty to register only
    # Ray tuning parameters (exposed in UI)
    ray_address: str = "",  # run locally by default for faster POC
    ray_num_samples: int = 1,  # Reduced from 4 for faster training
    ray_cpus_per_trial: float = 1,
    ray_gpus_per_trial: float = 0.0,
    entity_key: str = "sk_id_curr",  # Changed to lowercase to invalidate cache
    # Bootstrap evaluation parameters
    n_bootstrap: int = 1000,
    ci_level: float = 0.95,
    decision_threshold: float = 0.3,
):
    snap = fetch_minio_snapshot(
        s3_endpoint=s3_endpoint,
        bucket=bucket,
        object_key=object_key,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
    ).set_caching_options(False)
    # Parallel/distributed tuning via Ray (connect to an external cluster by setting `ray_address` in UI)
    tune = ray_tune_hyperparams(
        data=snap.outputs["output_csv"],
        config_json=config_json,
        num_samples=ray_num_samples,
        cpus_per_trial=ray_cpus_per_trial,
        gpus_per_trial=ray_gpus_per_trial,
        ray_address=ray_address,
    ).set_caching_options(False)
    train_register = train_and_register(
        data=snap.outputs["output_csv"],
        best_params_json=tune.output,
        config_json=config_json,
        experiment=experiment,
        register_name=register_name,
        stage=stage,
        mlflow_tracking_uri=mlflow_tracking_uri,
        mlflow_s3_endpoint_url=mlflow_s3_endpoint_url,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        entity_key=entity_key,
        n_bootstrap=n_bootstrap,
        ci_level=ci_level,
        decision_threshold=decision_threshold,
    ).set_caching_options(False)
