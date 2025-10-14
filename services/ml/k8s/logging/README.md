# EFK Stack (Elasticsearch-Filebeat-Kibana) Setup

Centralized logging solution for Docker containers and Kubernetes pods.

## Architecture

```
Docker Containers (hc-network)
    ↓ (Filebeat)
    → k8s_gateway:39200
    → Elasticsearch:30920

K8s Pods
    ↓ (Filebeat DaemonSet)
    → Elasticsearch:9200
```

## Components

### Elasticsearch
- **NodePort**: 30920
- **Internal**: elasticsearch-master:9200
- **Credentials**: admin/admin (HTTP only)
- **Storage**: 10Gi

### Kibana
- **URL**: http://192.168.49.2:30561
- **Internal**: kibana-kibana:5601
- **Auth**: None (development mode)

### Filebeat (Docker)
- **Location**: `services/ops/docker-compose.logging.yml`
- **Config**: `services/ops/filebeat.docker.yml`
- **Scope**: hc-network containers only
- **Index**: `.ds-filebeat-docker-YYYY.MM.DD` (data streams)

### Filebeat (Kubernetes)
- **Type**: DaemonSet (one pod per node)
- **Scope**: All K8s pods
- **Index**: `filebeat-8.5.1`
- **Resources**: 512Mi memory, 500m CPU

## Deployment

### Prerequisites
```bash
# Ensure k8s_gateway is running
docker-compose -f services/ops/docker-compose.gateway.yml up -d

# Create logging namespace
kubectl create namespace logging
```

### Install Elasticsearch
```bash
cd services/ml/k8s/logging/elastic-stack
helm install elasticsearch ./elasticsearch -n logging -f elasticsearch-values.custom.yaml
```

### Install Kibana
```bash
helm install kibana ./kibana -n logging \
  -f kibana-values.custom.yaml \
  --no-hooks
```

### Install Filebeat (K8s)
```bash
helm install filebeat ./filebeat -n logging -f filebeat-values.custom.yaml
```

### Install Filebeat (Docker)
```bash
cd services/ops
docker-compose -f docker-compose.logging.yml up -d
```

## Verification

### Check Services
```bash
# Elasticsearch
curl http://192.168.49.2:30920/_cluster/health?pretty

# Kibana
curl http://192.168.49.2:30561/api/status

# K8s Filebeat
kubectl get pods -n logging -l app=filebeat-filebeat

# Docker Filebeat
docker logs docker_filebeat --tail 50
```

### Check Indices
```bash
# List all indices
curl http://192.168.49.2:30920/_cat/indices?v

# K8s logs count
curl http://192.168.49.2:30920/_cat/indices/filebeat-8.5.1?v

# Docker logs count
curl http://192.168.49.2:30920/_cat/indices/.ds-filebeat-docker-*?v
```

## Kibana Setup

### Create Index Patterns
1. Open: http://192.168.49.2:30561
2. Navigate: **Stack Management** → **Index Patterns**
3. Create:
   - Pattern: `filebeat-8.5.1` (K8s logs)
   - Pattern: `.ds-filebeat-docker-*` (Docker logs)
   - Time field: `@timestamp`

### View Logs
Navigate: **Analytics** → **Discover**

**Useful Filters:**
```
log_source: "kubernetes-pods"
log_source: "docker-hc-network"
kubernetes.namespace: "kserve"
kubernetes.pod.name: "mlflow*"
```

## Troubleshooting

### Filebeat OOMKilled
**Symptom**: Pod restarts with exit code 137
**Solution**: Memory limits already set to 512Mi in `filebeat-values.custom.yaml`

### Elasticsearch Yellow Health
**Normal**: Single-node cluster with replica shards (replicas set to 0)

### Kibana Pre-install Job Errors
**Solution**: Already installed with `--no-hooks` flag

### Docker Filebeat Connection Refused
**Check**: k8s_gateway is running and forwarding port 39200→30920
```bash
docker logs k8s_gateway
netstat -tuln | grep 39200
```

### No Logs Appearing
```bash
# Check Filebeat is harvesting
kubectl logs -n logging -l app=filebeat-filebeat --tail=100 | grep harvester

# Check Elasticsearch connectivity
kubectl logs -n logging -l app=filebeat-filebeat --tail=100 | grep -i error
```

## Files

```
services/ml/k8s/logging/
├── README.md                              # This file
└── elastic-stack/
    ├── elasticsearch-values.custom.yaml   # ES config
    ├── kibana-values.custom.yaml          # Kibana config
    ├── filebeat-values.custom.yaml        # K8s Filebeat config
    └── SETUP.md                           # Detailed setup guide

services/ops/
├── filebeat.docker.yml                    # Docker Filebeat config
├── docker-compose.logging.yml             # Docker Filebeat service
└── docker-compose.gateway.yml             # k8s_gateway with ES forwarding
```

## Maintenance

### Upgrade Components
```bash
# Upgrade Filebeat
cd services/ml/k8s/logging/elastic-stack
helm upgrade filebeat ./filebeat -n logging -f filebeat-values.custom.yaml

# Restart Docker Filebeat
cd services/ops
docker-compose -f docker-compose.logging.yml restart filebeat
```

### Delete Old Indices
```bash
# Delete indices older than 30 days
curl -X DELETE "http://192.168.49.2:30920/.ds-filebeat-docker-2025.09.*"
```

### View Resource Usage
```bash
kubectl top pods -n logging
```

## Performance

- **K8s Logs**: ~218K documents, 141MB
- **Docker Logs**: ~13K documents, 15MB
- **Filebeat Memory**: ~300-400Mi average usage
- **Elasticsearch Storage**: 10Gi allocated, ~200MB used
