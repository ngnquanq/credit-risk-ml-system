# Production-Ready MinIO Setup

## Current Setup (Development with Minikube)

MinIO is deployed in Kubernetes with **NodePort** services for external access from Docker Compose.

### Access Endpoints

**From Docker Compose (ClickHouse, etc.):**
```bash
# MinIO API
http://192.168.49.2:30900

# MinIO Console
http://192.168.49.2:30901

# Credentials
Access Key: minio_user
Secret Key: minio_password
```

**From within Kubernetes (BentoML, training jobs):**
```bash
# Use Kubernetes DNS
http://training-minio.training-data.svc.cluster.local:9000

# Credentials retrieved from Secret:
kubectl get secret training-minio -n training-data -o jsonpath="{.data.root-user}" | base64 -d
kubectl get secret training-minio -n training-data -o jsonpath="{.data.root-password}" | base64 -d
```

### Example: ClickHouse Writing to MinIO

```bash
docker exec clickhouse_dwh clickhouse-client -q "
SET s3_truncate_on_insert=1;
INSERT INTO FUNCTION s3(
    'http://192.168.49.2:30900/training-data/snapshots/ds=2025-09-19/loan_applications.csv',
    'minio_user',
    'minio_password',
    'CSVWithNames'
)
SELECT a.SK_ID_CURR, /* your columns */, t.TARGET
FROM application_mart.mart_application AS a
INNER JOIN application_mart.mart_application_train AS t
ON a.SK_ID_CURR = t.SK_ID_CURR
"
```

---

## Production Migration Path

### Option 1: Cloud Provider LoadBalancer (Recommended)

**For GKE/EKS/AKS:**

1. Update `minio.values.yaml`:
```yaml
service:
  type: LoadBalancer  # Cloud provider will provision external IP
  ports:
    api: 9000
  annotations:
    # GKE example
    cloud.google.com/load-balancer-type: "External"
    # AWS example
    # service.beta.kubernetes.io/aws-load-balancer-type: "nlb"
```

2. Deploy and get external IP:
```bash
kubectl get svc training-minio -n training-data
# NAME             TYPE           EXTERNAL-IP      PORT(S)
# training-minio   LoadBalancer   35.123.45.67     9000:30900/TCP
```

3. Update Docker Compose to use external IP:
```bash
# In .env.k8s-services
K8S_NODE_IP=35.123.45.67

# ClickHouse now uses:
http://35.123.45.67:9000/training-data/...
```

**Pros:** Simple, cloud-native, auto-scaling
**Cons:** Costs money, no custom domain

---

### Option 2: Ingress with Custom Domain (Production Best Practice)

**Setup Ingress Controller (nginx):**

1. Update `minio.values.yaml`:
```yaml
service:
  type: ClusterIP  # Internal only

ingress:
  enabled: true
  ingressClassName: "nginx"
  hostname: minio.yourdomain.com
  path: /
  pathType: Prefix
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"  # For SSL
    nginx.ingress.kubernetes.io/proxy-body-size: "0"    # Large uploads
  tls: true  # Enable HTTPS
```

2. Configure DNS:
```bash
# Point your domain to Ingress controller IP
minio.yourdomain.com  →  <ingress-controller-external-ip>
```

3. Docker Compose uses domain:
```bash
# In .env.k8s-services
MINIO_ENDPOINT=minio.yourdomain.com
MINIO_USE_SSL=true

# ClickHouse uses:
https://minio.yourdomain.com/training-data/...
```

**Pros:** Custom domain, SSL/TLS, path-based routing
**Cons:** Requires DNS, cert-manager setup

---

### Option 3: Hybrid - External MinIO (Simplest for Mixed Workloads)

**If you have many Docker Compose services accessing storage:**

1. Keep MinIO in Docker Compose (already exists: `docker-compose.storage.yml`)
2. Kubernetes services access via ExternalName:

```yaml
# services/ml/k8s/training-data-storage/external-minio-service.yaml
apiVersion: v1
kind: Service
metadata:
  name: training-minio
  namespace: training-data
spec:
  type: ExternalName
  externalName: data-minio-server.hc-network  # Docker Compose service
  ports:
  - port: 9000
```

**Pros:** Simplest for development, single MinIO instance
**Cons:** Not truly K8s-native, harder to scale

---

## Current Architecture Pattern

Your current setup uses **NodePort**, which is a good middle ground:

✅ **Production-compatible** (works on any K8s cluster)
✅ **No cloud dependencies** (works on-prem)
✅ **Predictable ports** (30900/30901)
⚠️  **Requires firewall rules** in production
⚠️  **No automatic SSL** (add later with Ingress)

### Migration Steps

**When moving to production Kubernetes:**

1. Get your K8s node/LoadBalancer IP:
```bash
# For managed K8s (GKE/EKS/AKS)
kubectl get nodes -o wide
# Or get LoadBalancer IP if using that
kubectl get svc training-minio -n training-data
```

2. Update `.env.k8s-services`:
```bash
K8S_NODE_IP=<your-production-node-ip>
```

3. Update Docker Compose services to source this file:
```yaml
# docker-compose.warehouse.yml
services:
  ch-server:
    env_file:
      - ../ml/k8s/training-data-storage/.env.k8s-services
```

4. For SSL in production, switch to Ingress (Option 2 above)

---

## Verification

Test MinIO access from Docker Compose:

```bash
# From ClickHouse container
docker exec clickhouse_dwh curl http://192.168.49.2:30900/minio/health/live

# Should return: HTTP 200 OK
```

Test from Kubernetes:

```bash
kubectl run -n training-data test-minio --rm -it --restart=Never \
  --image=curlimages/curl -- \
  curl http://training-minio:9000/minio/health/live
```

---

## Best Practice Recommendation

For your use case (credit risk ML platform):

1. **Development (now)**: Use current NodePort setup ✅
2. **Staging**: Migrate to LoadBalancer (Option 1)
3. **Production**: Use Ingress + custom domain (Option 2)

This gives you a smooth migration path without breaking changes.
