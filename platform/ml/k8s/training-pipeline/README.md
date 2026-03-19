# Kubeflow Pipelines – Training Skeleton

This pipeline snapshots training data from MinIO, tunes hyperparameters, and registers the best model to MLflow.

Components
- fetch_minio_snapshot: downloads a CSV from MinIO/S3 to the pipeline workspace (auditable snapshot).
- ray_tune_hyperparams: distributed/parallel hyperparameter tuning using Ray Tune (connect to an external Ray cluster or run locally in‑pod).
- train_and_register: trains with best params and registers/logs to MLflow; optionally transitions stage.

Notes
- This is a skeleton for quick iteration. Swap `tune_hyperparams` with Katib later if you prefer full HPO.
- All credentials are provided as parameters/envs; do not hardcode secrets.

Quick Start
1) Compile pipeline spec
   python services/ml/k8s/training-pipeline/compile_pipeline.py

   Outputs `training_pipeline.json` next to the script.

2) (Optional) Deploy Ray for distributed tuning
   - Install KubeRay operator (Helm) and apply the cluster manifest:
     helm repo add kuberay https://ray-project.github.io/kuberay-helm && helm repo update
     helm install kuberay-operator kuberay/kuberay-operator -n ray-system --create-namespace
     kubectl apply -f services/ml/k8s/training-pipeline/ray/raycluster.yaml

3) Upload to KFP UI and run with parameters (defaults pre-filled; you can run without changes):
   - s3_endpoint: http://minio.minio.svc.cluster.local:9000 (example)
   - bucket: your-bucket
   - object_key: path/to/your.csv
   - mlflow_tracking_uri: http://mlflow.ml.svc.cluster.local:80 (example)
   - mlflow_s3_endpoint_url: http://minio.minio.svc.cluster.local:9000
   - aws_access_key_id / aws_secret_access_key: MinIO creds (consider K8s secrets + KFP params)
   - experiment: credit-risk
   - register_name: credit_risk_model
   - stage: Production (or leave empty to skip)
   - ray_address: (optional) ray://raycluster-k8s-head-svc.ray.svc.cluster.local:10001 (leave empty to run Ray locally)
   - ray_num_samples: 12 (number of HPO trials)
   - ray_cpus_per_trial: 1.0
   - ray_gpus_per_trial: 0.0

Security
- Use K8s Secrets + KFP runtime parameterization for credentials.
- If your cluster blocks egress, pre-bake images with required packages.

Future
- Optionally integrate Katib, or connect to a KubeRay-managed RayCluster for multi-pod tuning.
- Add data versioning tags from MinIO object ETag/last-modified to MLflow run params.
