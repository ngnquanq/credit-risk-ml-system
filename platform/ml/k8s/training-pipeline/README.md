# Kubeflow Pipelines - Training Prototype

This prototype pipeline snapshots training data from MinIO, tunes hyperparameters, and registers the best model to MLflow. Treat `application/training/train_register.py` as the validated local training and MLflow registration path unless you have a verified KFP run artifact.

Components
- fetch_minio_snapshot: downloads a CSV from MinIO/S3 to the pipeline workspace (auditable snapshot).
- ray_tune_hyperparams: distributed/parallel hyperparameter tuning using Ray Tune (connect to an external Ray cluster or run locally in‑pod).
- train_and_register: trains with best params and registers/logs to MLflow; optionally transitions stage.

Notes
- This is a quick-iteration skeleton; swap `ray_tune_hyperparams` with Katib or a validated production pipeline before making production training claims.
- All credentials are provided as parameters/envs; do not hardcode secrets.

Quick Start
1) Build both recipe images from the repository root, then compile the pipeline.

   ```bash
   docker build -f platform/ml/k8s/training-pipeline/Dockerfile -t credit-risk-kfp-trainer:dev .
   docker build -f platform/ml/k8s/training-pipeline/Dockerfile \
     --build-arg BASE_IMAGE=python:3.9-slim -t credit-risk-kfp-ray:dev .
   python platform/ml/k8s/training-pipeline/compile_pipeline.py
   ```

   The compiler writes `training_pipeline.yaml`. Load both images into the trial cluster or
   compile with `CRQ_KFP_TRAINER_IMAGE` and `CRQ_KFP_RAY_IMAGE` set to pullable, versioned
   image references. Both images must contain the recipe from the same source revision.
   The pipeline expects the same 24 input columns as the local CLI plus `TARGET`.
   Extra snapshot columns, including `SK_ID_CURR`, are excluded from model inputs.


2) (Optional) Deploy Ray for distributed tuning
   - Install KubeRay operator (Helm) and apply the cluster manifest:
     helm repo add kuberay https://ray-project.github.io/kuberay-helm && helm repo update
     helm install kuberay-operator kuberay/kuberay-operator -n ray-system --create-namespace
     kubectl apply -f platform/ml/k8s/kuberay-operator/raycluster.yaml

3) Upload to KFP UI and supply the snapshot, registry and trial run parameters:
   - s3_endpoint: http://minio.minio.svc.cluster.local:9000 (example)
   - bucket: your-bucket
   - object_key: path/to/your.csv
   - mlflow_tracking_uri: http://mlflow.ml.svc.cluster.local:80 (example)
   - mlflow_s3_endpoint_url: http://minio.minio.svc.cluster.local:9000
   - aws_access_key_id / aws_secret_access_key: MinIO creds (consider K8s secrets + KFP params)
   - experiment: credit-risk
   - register_name: credit_risk_model
   - stage: leave empty during validation so the candidate stays unpromoted
   - ray_address: leave empty for the first trial. For remote Ray, every worker must use
     the recipe module, the same dependency versions as the tuning task, and access to the snapshot path.
   - ray_num_samples: 12 (number of HPO trials)
   - ray_cpus_per_trial: 1.0
   - ray_gpus_per_trial: 0.0

Security
- Use K8s Secrets + KFP runtime parameterization for credentials.
- If your cluster blocks egress, pre-bake images with required packages.

Future
- Optionally integrate Katib, or connect to a KubeRay-managed RayCluster for multi-pod tuning.
- Add data versioning tags from MinIO object ETag/last-modified to MLflow run params.
