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
def tune_hyperparams(data: Input[Dataset]) -> str:
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

    search_space = [
        {"n_estimators": 300, "max_depth": 6, "learning_rate": 0.05},
        {"n_estimators": 400, "max_depth": 4, "learning_rate": 0.03},
    ]

    best = {"auc": -1.0, "params": None}
    for p in search_space:
        clf = XGBClassifier(
            eval_metric="logloss",
            n_jobs=-1,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            **p,
        )
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

    base = dict(
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="logloss",
        n_jobs=-1,
        random_state=42,
    )

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

    search_space = {
        "n_estimators": tune.randint(200, 600),
        "max_depth": tune.randint(3, 9),
        "learning_rate": tune.loguniform(1e-2, 2e-1),
        "min_child_weight": tune.randint(1, 6),
        "gamma": tune.uniform(0.0, 0.3),
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
    entity_key: str = "SK_ID_CURR",
) -> str:
    """
    Train with provided params and register to MLflow.
    Logs simplified feast_metadata.yaml (serving discovers feature views dynamically).
    """
    import os
    import json
    import yaml
    import pandas as pd
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OrdinalEncoder, FunctionTransformer
    from sklearn.metrics import roc_auc_score
    from xgboost import XGBClassifier
    import mlflow
    import mlflow.sklearn

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

    params = json.loads(best_params_json) if best_params_json else {}
    base = dict(
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="logloss",
        n_jobs=-1,
        random_state=42,
    )
    base.update(params)
    clf = XGBClassifier(**base)
    pipe = Pipeline([("pre", pre), ("clf", clf)])

    pipe.fit(X_train, y_train)
    proba = pipe.predict_proba(X_test)[:, 1]
    auc = float(roc_auc_score(y_test, proba))

    mlflow.set_experiment(experiment)
    with mlflow.start_run() as run:
        mlflow.log_params(base)
        mlflow.log_metric("auc", auc)

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
        # v32
        # v34
        # Log as YAML artifact
        with open("feast_metadata.yaml", "w") as f:
            yaml.dump(feast_metadata, f, default_flow_style=False)
        mlflow.log_artifact("feast_metadata.yaml")

        print(f"✅ Logged feast_metadata.yaml with {len(FEATURES)} features")

        # Transition to stage (same as before)
        if stage:
            client = mlflow.tracking.MlflowClient()
            version = None
            for v in client.search_model_versions(f"name='{register_name}'"):
                if v.run_id == run.info.run_id:
                    version = v.version
                    break
            if version is not None:
                client.transition_model_version_stage(
                    name=register_name,
                    version=str(version),
                    stage=stage,
                    archive_existing_versions=False,
                )
        return run.info.run_id


@dsl.pipeline(name="credit-risk-training-pipeline")
def training_pipeline(
    s3_endpoint: str = "http://training-minio.training-data.svc.cluster.local:9000",
    bucket: str = "training-data",
    object_key: str = "snapshots/ds=2025-09-19/loan_applications.csv",
    mlflow_tracking_uri: str = "http://mlflow.model-registry.svc.cluster.local:80",
    mlflow_s3_endpoint_url: str = "http://minio.model-registry.svc.cluster.local:9000",
    aws_access_key_id: str = "minio_user",
    aws_secret_access_key: str = "minio_password",
    experiment: str = "credit-risk",
    register_name: str = "credit_risk_model",
    stage: str = "Production",
    # Ray tuning parameters (exposed in UI)
    ray_address: str = "",  # run locally by default for faster POC
    ray_num_samples: int = 1,  # Reduced from 4 for faster training
    ray_cpus_per_trial: float = 1,
    ray_gpus_per_trial: float = 0.0,
    entity_key: str = "sk_id_curr",  # Changed to lowercase to invalidate cache
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
        num_samples=ray_num_samples,
        cpus_per_trial=ray_cpus_per_trial,
        gpus_per_trial=ray_gpus_per_trial,
        ray_address=ray_address,
    ).set_caching_options(False)
    train_register = train_and_register(
        data=snap.outputs["output_csv"],
        best_params_json=tune.output,
        experiment=experiment,
        register_name=register_name,
        stage=stage,
        mlflow_tracking_uri=mlflow_tracking_uri,
        mlflow_s3_endpoint_url=mlflow_s3_endpoint_url,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        entity_key=entity_key,
    ).set_caching_options(False)
