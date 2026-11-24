# Configuration and secrets

Two kinds of settings, handled differently.

| | Config | Secret |
|---|---|---|
| What | Where services find each other, topic names, bucket names, replica counts | Passwords, keys, tokens, client secrets, encryption keys |
| Safe in git | Yes | Never |
| Lives in | `platform/config/endpoints/endpoints.env` (addresses), overlays in `platform/environments/` (per environment), each service's own ConfigMap (its own settings) | A Kubernetes Secret created outside git |
| Read by pods through | `envFrom` or `valueFrom.configMapKeyRef` on `shared-endpoints` | `secretKeyRef` or `secretRef` |

A hostname like `kafka-broker.data-services.svc.cluster.local` is config, not a secret (Twelve-Factor III counts it as a per-deploy value). `endpoints.env` is public by design, and a test fails if a key in it looks like a secret.

## Where addresses live

One definition per address in `platform/config/endpoints/endpoints.env`. `make k8s-shared-config` creates the `shared-endpoints` ConfigMap in every namespace that reads it, and every service that is applied with `kubectl apply -k` also includes it as a Kustomize component.

How each kind of consumer reads it:

| Consumer | How |
|---|---|
| A pod env var with the same name | `envFrom: shared-endpoints` |
| A pod that wants one key under its own name | `valueFrom.configMapKeyRef` |
| A Knative `KafkaSink`/`KafkaSource` (a spec field) | `replacements` in the service's `kustomization.yaml` |
| A shell script in a ConfigMap | the pod gets the variable and the script reads `$CLICKHOUSE_HOST` |
| Python rendered at runtime from a template (serving watcher, MLflow poller) | `${NAME}` in the template, filled from the watcher's own environment |
| A file rendered by `make` (pgbouncer, Knative serving config) | a `<set-via-NAME>` placeholder that the Make target fills from `endpoints.env` |

Still written out in full, with the reason, in `tests/unit/infra/test_endpoints_single_source.py`: the Feast `feature_store.yaml` used inside the scoring bundle, and the generated Kubeflow pipeline file.

## Secrets today

All are created by `make` targets from environment variables (`.env`, not committed). Nothing secret is in a committed manifest.

| Secret | Namespace | Keys | Used by | Created by |
|---|---|---|---|---|
| `db-secrets` | data-services | `POSTGRES_PASSWORD` | operational database | `k8s-secrets` |
| `minio-root-credentials` | data-services | `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` | data MinIO | `k8s-secrets` |
| `api-secrets` | api-gateway | `OPS_DB_PASSWORD`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `APP_PII_KEKS`, `APP_PII_HMAC_KEY` | Loan API, decision recorder | `k8s-secrets` |
| `audit-secrets` | api-gateway | `verifier-dsn` | audit verification job | |
| `cdc-db-secrets` | data-services | `CDC_DB_PASSWORD` | Debezium | `k8s-cdc` |
| `model-serving-minio-credentials` | model-serving | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | serving watcher, Feast, scoring | `k8s-model-serving` |
| `dockerhub-creds` | model-serving | `username`, `password` | serving watcher (image push) | `k8s-model-serving` |
| `keycloak-admin`, `keycloak-db-credentials`, `keycloak-clients` | identity | admin password, DB password, client secrets | Keycloak | `k8s-identity-secrets` |
| `portal-secrets` | portals | `staff-portal`, `applicant-portal` | the two portals | `k8s-portals` |

## Places where a secret passes through something that is not a Secret

These work, but a secret ends up in a ConfigMap or a rendered file. They are the first things to fix when a real secret manager arrives.

1. **`services/model-lifecycle/mlflow-watcher/builder-configmap.yaml`** has `<set-via-MINIO_ACCESS_KEY>` and `<set-via-MINIO_SECRET_KEY>` in a ConfigMap that the poller reads to build the bundle Job. The Job should read the keys from a Secret with `secretKeyRef`.
2. **`platform/data/k8s/operational-db/05-pgbouncer-config.yaml.template`** is rendered with the database password and its md5 hash into a ConfigMap. PgBouncer's `userlist` belongs in a Secret.
3. **MinIO and MLflow `values.internal.yaml`** carry `<set-via-MINIO_*>` for Helm. Helm stores release values in a Secret, which is acceptable, but the keys should come from an existing Secret (`auth.existingSecret`).

## Using a real secret manager

Kubernetes documents two ways to keep secrets outside the cluster's own store: a Secrets Store CSI Driver that mounts them from an external store, or syncing them into ordinary Secrets from one. Both leave the pod manifests unchanged, because pods already read named Secrets.

For this repository the smallest change is an operator that creates the Secrets above from the cloud provider's secret manager (External Secrets Operator is the common choice; the sources in the project notebook name it and the CSI driver, but do not compare them). Then:

- `make k8s-secrets` and the other `kubectl create secret` lines go away for that environment.
- Each environment overlay in `platform/environments/` declares which external entries feed which Secret. The Secret names and keys in the table above stay the same.
- Items 1 and 2 above are fixed first, because they currently bypass Secrets entirely.
- Rotation then becomes a change in the secret manager. A pod only sees a new value after it restarts, unless the secret is mounted as a file.

This part is a design. Nothing here has been run against a cluster or a secret manager.
