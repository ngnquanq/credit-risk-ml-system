# K8s Gateway - Bidirectional Proxy

## Purpose

Enables communication between Docker Compose services and Kubernetes services in local development and production environments.

## Architecture

```
┌─────────────────────────────────────┐         ┌──────────────────────────────────┐
│      Docker Compose Network         │         │      Kubernetes Cluster          │
│         (hc-network)                │         │                                  │
│                                     │         │                                  │
│  ┌──────────────┐                  │         │    ┌─────────────────┐          │
│  │  ClickHouse  │──────────────────┼────────►│────│ training-minio  │          │
│  │              │  Write snapshots  │         │    │ (NodePort 30900)│          │
│  └──────────────┘                  │         │    └─────────────────┘          │
│                                     │         │                                  │
│  ┌──────────────┐                  │         │    ┌─────────────────┐          │
│  │    Kafka     │◄─────────────────┼─────────│────│  Serving Pod    │          │
│  │  (port 9092) │  Consume messages│         │    │ (Kafka consumer)│          │
│  └──────────────┘                  │         │    └─────────────────┘          │
│                                     │         │                                  │
│                                     │         │    ┌─────────────────┐          │
│                                     │◄────────│────│ Feature Store   │          │
│                                     │         │    │ (Kafka consumer)│          │
└─────────────────────────────────────┘         │    └─────────────────┘          │
                                                 │                                  │
                                                 └──────────────────────────────────┘
                    │
                    │ All traffic routed through
                    ▼
        ┌────────────────────────┐
        │    K8s Gateway         │
        │  (NGINX TCP Proxy)     │
        │  with hostNetwork      │
        └────────────────────────┘
```

## Service Mappings

### Docker Compose → K8s

| Source Service | Target Service | Gateway Port | K8s NodePort | Purpose |
|----------------|----------------|--------------|--------------|---------|
| ClickHouse | training-minio | 30900 | 30900 | Write training data snapshots |
| - | training-minio-console | 30901 | 30901 | MinIO UI access |

**Usage in ClickHouse**:
```sql
INSERT INTO FUNCTION s3(
  'http://k8s-gateway:30900/training-data/snapshots/ds=2025-09-19/loan_applications.csv',
  'minio_user',
  'minio_password',
  'CSVWithNames'
)
SELECT * FROM application_mart.mart_application;
```

### K8s → Docker Compose

| Source Service | Target Service | Gateway Port | Docker Port | Purpose |
|----------------|----------------|--------------|-------------|---------|
| Serving Pod | Kafka | 9092 | 9092 | Consume application events |
| Feature Store Pod | Kafka | 9092 | 9092 | Consume feature updates |

**Usage in K8s Pods**:
```yaml
env:
  - name: KAFKA_BOOTSTRAP_SERVERS
    value: "k8s-gateway:9092"
```

## Deployment

### 1. Deploy ConfigMap
```bash
kubectl apply -f configmap-stream.yaml
```

### 2. Deploy Gateway
```bash
helm install k8s-gateway . -f values.internal.yaml
```

### 3. Verify Deployment
```bash
kubectl get pods -l app.kubernetes.io/name=nginx
kubectl logs -l app.kubernetes.io/name=nginx
```

## Testing Connectivity

### Test Docker → K8s (MinIO)
```bash
# From ClickHouse container
docker exec clickhouse_dwh wget -O- http://k8s-gateway:30900/minio/health/live
```

### Test K8s → Docker (Kafka)
```bash
# From a K8s pod
kubectl run test-kafka --image=confluentinc/cp-kafka:7.4.0 --rm -it -- \
  kafka-topics --bootstrap-server k8s-gateway:9092 --list
```

## Production Considerations

In production VPC deployments:

1. **Replace Minikube IP (`192.168.49.2`)** with actual K8s LoadBalancer/NodePort IPs
2. **Replace Docker bridge IP (`172.18.0.1`)** with actual VM/EC2 instance IPs
3. **Use DNS names** instead of IPs:
   ```nginx
   upstream kafka_broker {
       server kafka.vpc.internal:9092;
   }
   ```
4. **Add TLS termination** for encrypted communication
5. **Implement authentication** via mTLS or API keys

## Troubleshooting

### Gateway pod not starting
```bash
# Check logs
kubectl logs -l app.kubernetes.io/name=nginx

# Verify ConfigMap
kubectl get configmap k8s-gateway-stream-config -o yaml
```

### Connection timeouts
```bash
# Verify host network access
kubectl exec -it <gateway-pod> -- ip addr show

# Check if Minikube IP is reachable
kubectl exec -it <gateway-pod> -- ping 192.168.49.2
```

### Kafka connection refused from K8s
```bash
# Verify Kafka is listening on Docker bridge
docker exec kafka_broker netstat -tuln | grep 9092

# Test from gateway pod
kubectl exec -it <gateway-pod> -- telnet 172.18.0.1 9092
```

## Maintenance

### Update Minikube IP (after restart)
```bash
# Get new Minikube IP
minikube ip -p mlops

# Update ConfigMap
kubectl edit configmap k8s-gateway-stream-config

# Restart gateway
kubectl rollout restart deployment k8s-gateway
```

### Add new service proxy
1. Edit `configmap-stream.yaml` to add new upstream/server
2. Apply changes: `kubectl apply -f configmap-stream.yaml`
3. Update `values.internal.yaml` to add new service port
4. Upgrade: `helm upgrade k8s-gateway . -f values.internal.yaml`
