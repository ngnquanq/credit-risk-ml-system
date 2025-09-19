# Training Data Storage (MinIO) – Helm Values

Purpose
- Provide a minimal, production-friendly MinIO configuration so ClickHouse (running outside the cluster via Docker) can write training snapshots directly into MinIO using INSERT ... (S3-compatible API).

What this gives you
- MinIO running inside Kubernetes
- NodePort exposure so external services (ClickHouse in Docker) can reach the S3 API
- A pre-created bucket for training artifacts (configurable)

Usage
1) Add the MinIO Helm repo (official):
   helm repo add minio https://charts.min.io
   helm repo update

2) Install with the provided values file, adjusting secrets/ports as needed:
   kubectl create namespace training-data || true
   helm upgrade --install training-minio minio/minio \
     -n training-data \
     -f services/ml/k8s/training-data-storage/minio.values.yaml

3) From ClickHouse (Docker), use the Node IP and NodePort to write:
   INSERT INTO FUNCTION s3('http://<node-ip>:30900/training-data/snapshots/ds=2025-09-19/data.csv',
                          'minio_user', 'minio_password', 'CSV')
   SELECT ... FROM ...;

Parameters to adjust
- root credentials: `rootUser`, `rootPassword`
- bucket name: `buckets[0].name`
- NodePorts: `service.nodePorts.api` (S3), `consoleService.nodePorts.console` (UI)
- Persistence: enable and set PVC if you want data to survive pod restarts

Notes
- Ensure your cluster nodes are reachable from your Docker host (where ClickHouse runs). Use the node’s IP (or a routable address) with the NodePort configured here.
- If your environment supports LoadBalancer, you can set `service.type: LoadBalancer` and omit NodePorts.
- Keep `MINIO_BROWSER` enabled for convenience; disable in hardened environments.
- TLS is disabled here for simplicity. If you require TLS, place your certs and switch service to HTTPS with proper certificates.

ClickHouse tips
- MinIO endpoint (from Docker/ClickHouse): `http://<node-ip>:30900`
- Credentials must match `rootUser/rootPassword` in values.
- For large exports, consider `CSVWithNames` and parallelization options in ClickHouse.

