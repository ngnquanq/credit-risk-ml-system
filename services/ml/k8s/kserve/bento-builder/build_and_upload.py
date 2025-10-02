"""
Flow:
- Clone application repo and cd into the scoring service (convention: application/scoring).
- Load the promoted model from MLflow (MODEL_URI).
- Serialize it into bundle/model.joblib inside the scoring service directory.
- Build a Bento with bentoml build --version <VERSION_TAG>.
- Upload the built Bento directory to MinIO/S3 at s3://<bucket>/<prefix>/<model_name>/<version_tag>/.

Required env:
- MLFLOW_TRACKING_URI: http://mlflow.model-registry.svc.cluster.local:80
- MODEL_NAME: credit_risk_model (used in storage path)
- MODEL_URI: e.g. models:/credit_risk_model/12 or models:/credit_risk_model/Production
- VERSION_TAG: e.g. v12 (tag to use for Bento and storage)
- APP_REPO: git URL to this repo
- APP_REF: git ref/branch (default: main)
- APP_SUBPATH: subdir of scoring service (default: application/scoring)
- BENTO_BUCKET: destination bucket (e.g., bento-bundles)
- BENTO_PREFIX: prefix under bucket (default: bentos)
- AWS_REGION: default us-east-1
- AWS_S3_ENDPOINT: http://minio.model-registry.svc.cluster.local:9000
- AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
- AWS_S3_FORCE_PATH_STYLE: "true" (recommended for MinIO)
"""

from __future__ import annotations

import os
import sys
import subprocess
import tempfile
import pathlib
import shutil


def sh(cmd: str, cwd: str | None = None) -> None:
    print("+", cmd, flush=True)
    subprocess.check_call(cmd, shell=True, cwd=cwd)


def _import_or_install():
    """Import runtime deps. Assumes container pre-installed or caller pip installs before run."""
    global mlflow, joblib, boto3
    try:
        import mlflow  # type: ignore
        import joblib  # type: ignore
        import boto3   # type: ignore
    except Exception as e:  # pragma: no cover
        raise SystemExit(f"Missing dependencies. Ensure mlflow, joblib, boto3 installed: {e}")
    return mlflow, joblib, boto3


def _git_clone(repo: str, ref: str, dest: str) -> None:
    """Clone repo@ref to dest using git if available, else GitPython."""
    # Prefer system git for simplicity
    try:
        sh(f"git clone --depth 1 --branch {ref} {repo} {dest}")
        return
    except Exception:
        pass
    # Fallback to GitPython when git CLI missing
    try:
        import git  # type: ignore
        git.Repo.clone_from(repo, dest, branch=ref, depth=1)
    except Exception as e:
        raise SystemExit(f"Failed to clone repo {repo}@{ref}: {e}")


def main() -> None:
    mlflow, joblib, boto3 = _import_or_install()

    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI")
    model_name = os.environ.get("MODEL_NAME")
    model_uri = os.environ.get("MODEL_URI")
    version_tag = os.environ.get("VERSION_TAG")
    app_repo = os.environ.get("APP_REPO")
    app_local_path = os.environ.get("APP_LOCAL_PATH")  # Optional: use a pre-mounted local repo path
    app_ref = os.environ.get("APP_REF", "main")
    app_subpath = os.environ.get("APP_SUBPATH", "application/scoring")

    bkt = os.environ.get("BENTO_BUCKET")
    prefix = os.environ.get("BENTO_PREFIX", "bentos")

    s3_endpoint = os.environ.get("AWS_S3_ENDPOINT")
    force_path_style = os.environ.get("AWS_S3_FORCE_PATH_STYLE", "true").lower() == "true"

    if not (tracking_uri and model_name and model_uri and version_tag and (app_repo or app_local_path) and bkt):
        missing = [k for k, v in {
            "MLFLOW_TRACKING_URI": tracking_uri,
            "MODEL_NAME": model_name,
            "MODEL_URI": model_uri,
            "VERSION_TAG": version_tag,
            "APP_REPO/APP_LOCAL_PATH": app_repo or app_local_path,
            "BENTO_BUCKET": bkt,
        }.items() if not v]
        raise SystemExit(f"Missing required env: {', '.join(missing)}")

    # Configure MLflow client
    mlflow.set_tracking_uri(tracking_uri)

    # Prepare workspace
    work = tempfile.mkdtemp(prefix="bento-build-")
    repo_dir = os.path.join(work, "repo")
    if app_local_path and os.path.isdir(app_local_path):
        print(f"Copying local repo from {app_local_path} -> {repo_dir}")
        shutil.copytree(app_local_path, repo_dir, dirs_exist_ok=True)
    else:
        if not app_repo:
            raise SystemExit("APP_LOCAL_PATH does not exist and APP_REPO is not set")
        print(f"Cloning {app_repo}@{app_ref} -> {repo_dir}")
        _git_clone(app_repo, app_ref, repo_dir)

    # Resolve scoring service path
    svc_dir = os.path.join(repo_dir, app_subpath)
    bentofile = os.path.join(svc_dir, "bentofile.yaml")
    service_py = os.path.join(svc_dir, "service.py")
    if not (os.path.exists(bentofile) and os.path.exists(service_py)):
        raise SystemExit(f"Scoring service not found at {svc_dir} (expected bentofile.yaml and service.py)")

    # Load model from MLflow (prefer native flavor for predict_proba)
    print(f"Loading MLflow model: {model_uri}")
    try:
        try:
            mdl = mlflow.sklearn.load_model(model_uri)  # type: ignore[attr-defined]
        except Exception:
            try:
                mdl = mlflow.xgboost.load_model(model_uri)  # type: ignore[attr-defined]
            except Exception:
                mdl = mlflow.pyfunc.load_model(model_uri)
    except Exception as e:
        raise SystemExit(f"Failed to load model from MLflow: {e}")

    # Serialize to a single file included in the Bento context
    bundle_dir = os.path.join(svc_dir, "bundle")
    pathlib.Path(bundle_dir).mkdir(parents=True, exist_ok=True)
    model_rel_path = os.path.join("bundle", "model.joblib")
    model_file = os.path.join(svc_dir, model_rel_path)
    print(f"Saving model to {model_file}")
    joblib.dump(mdl, model_file)

    # Do NOT modify mlflow.env here; runtime (KServe) will provide
    # SCORING_MODEL_SOURCE=local and SCORING_MODEL_PATH via container env.

    # Build Bento
    print("Installing build deps...")
    sh("pip install --no-cache-dir bentoml mlflow boto3 joblib gitpython", cwd=repo_dir)
    print(f"Building Bento version={version_tag}")
    sh(f"bentoml build --version {version_tag}", cwd=svc_dir)

    # Determine Bento location. Service name is defined in service.py
    # In your code: svc = bentoml.Service("credit_risk_scoring")
    bento_tag = f"credit_risk_scoring:{version_tag}"
    bento_path = subprocess.check_output(
        f"bentoml get {bento_tag} --print-location", shell=True, cwd=repo_dir
    ).decode().strip()
    print(f"Bento path: {bento_path}")

    # Upload to S3/MinIO
    import boto3.session
    session = boto3.session.Session()
    # Note: address style is controlled via AWS_S3_FORCE_PATH_STYLE env; boto3 picks it up via config if needed
    s3 = session.resource("s3", endpoint_url=s3_endpoint)
    bucket = s3.Bucket(bkt)

    storage_uri = f"s3://{bkt}/{prefix}/{model_name}/{version_tag}/"
    print(f"Uploading to {storage_uri}")
    for root, _, files in os.walk(bento_path):
        for fn in files:
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, bento_path)
            key = f"{prefix}/{model_name}/{version_tag}/{rel}"
            bucket.upload_file(full, key)

    print("DONE:", storage_uri)


if __name__ == "__main__":
    main()
