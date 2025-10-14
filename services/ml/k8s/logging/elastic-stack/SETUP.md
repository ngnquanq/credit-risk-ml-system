# EFK Stack Setup Guide

This is a custom deployment of the Elastic Stack (Elasticsearch-Filebeat-Kibana) for centralized logging from both Docker containers and Kubernetes pods.

## Architecture

```
Docker hc-network containers → Filebeat (Docker) ─┐
                                                   ├─→ Elasticsearch (K8s) → Kibana (K8s)
Kubernetes pods → Filebeat DaemonSet (K8s) ───────┘
```

## Prerequisites

- Minikube running (`minikube -p mlops start`)
- Helm 3 installed
- Docker Filebeat configured (see `services/ops/docker-compose.logging.yml`)
- At least 4GB memory available for Elasticsearch

## Installation Steps

### 1. Create logging namespace

```bash
kubectl create namespace logging
```

### 2. Install Elasticsearch

```bash
cd /home/nhatquang/home-credit-credit-risk-model-stability/services/ml/k8s/logging/elastic-stack

helm upgrade --install elasticsearch ./elasticsearch \
  -n logging \
  -f elasticsearch-values.custom.yaml
```

Wait for Elasticsearch to be ready:
```bash
kubectl wait --for=condition=ready pod -l app=elasticsearch-master -n logging --timeout=300s
```

### 3. Install Kibana

```bash
helm upgrade --install kibana ./kibana \
  -n logging \
  -f kibana-values.custom.yaml
```

Wait for Kibana to be ready:
```bash
kubectl wait --for=condition=ready pod -l app=kibana -n logging --timeout=300s
```

### 4. Install Filebeat DaemonSet (K8s logs)

```bash
helm upgrade --install filebeat ./filebeat \
  -n logging \
  -f filebeat-values.custom.yaml
```

### 5. Start Docker Filebeat (Docker logs)

```bash
cd /home/nhatquang/home-credit-credit-risk-model-stability/services/ops
docker compose -f docker-compose.logging.yml up -d
```

## Access

- **Kibana**: http://localhost:30561
- **Elasticsearch**: http://localhost:30920

## Configuration Highlights

- **Elasticsearch**:
  - Single node cluster (development)
  - 10GB storage
  - Security disabled (enable in production!)
  - NodePort 30920 for Docker Filebeat access

- **Kibana**:
  - Timezone: Server default (configure in kibana.yml if needed)
  - NodePort 30561 for browser access
  - Security disabled

- **Filebeat (K8s)**:
  - DaemonSet on all nodes
  - Auto-discovers pod logs
  - Index pattern: `filebeat-k8s-*`

- **Filebeat (Docker)**:
  - Runs in hc-network
  - Auto-discovers containers via Docker socket
  - Index pattern: `filebeat-docker-*`

## Index Patterns

Create these in Kibana (Management → Stack Management → Index Patterns):

1. **filebeat-docker-*** - Docker container logs from hc-network
2. **filebeat-k8s-*** - Kubernetes pod logs

## Query Examples

### Find logs from specific Docker container
```
docker.container.name: "kafka_broker"
```

### Find logs from specific K8s pod
```
kubernetes.pod.name: "prometheus-stack-*"
```

### Filter by log level (if logs are JSON)
```
json.level: "ERROR"
```

## Troubleshooting

### Elasticsearch not starting
```bash
# Check pod logs
kubectl logs -n logging -l app=elasticsearch-master

# Check storage
kubectl get pvc -n logging
```

### Filebeat not shipping logs
```bash
# Check Docker Filebeat logs
docker logs docker_filebeat

# Check K8s Filebeat logs
kubectl logs -n logging -l app=filebeat --tail=50
```

### Kibana can't connect to Elasticsearch
```bash
# Verify Elasticsearch service
kubectl get svc -n logging elasticsearch-master

# Check Kibana logs
kubectl logs -n logging -l app=kibana
```

## Uninstall

```bash
# Stop Docker Filebeat
docker compose -f services/ops/docker-compose.logging.yml down

# Uninstall K8s components
helm uninstall filebeat -n logging
helm uninstall kibana -n logging
helm uninstall elasticsearch -n logging

# Delete namespace (this will delete PVCs!)
kubectl delete namespace logging
```

## Production Considerations

For production, enable these features:

1. **Security**: Enable X-Pack security with authentication
2. **High Availability**: Run 3 Elasticsearch master nodes
3. **Storage**: Use persistent volumes with backup strategy
4. **Resource Limits**: Adjust CPU/memory based on log volume
5. **Index Lifecycle Management**: Enable ILM for log rotation
6. **TLS**: Enable HTTPS for Elasticsearch and Kibana
