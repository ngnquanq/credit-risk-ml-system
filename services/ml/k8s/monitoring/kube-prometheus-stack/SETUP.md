# Quick Setup Guide

This is a custom deployment of kube-prometheus-stack with Docker container monitoring for the hc-network.

## Prerequisites

- Minikube running (`minikube -p mlops start`)
- Helm 3 installed
- Docker cAdvisor running (see `services/ops/docker-compose.monitoring.yml`)

## Installation

```bash
# Add Prometheus Community Helm repo
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Install/Upgrade with custom values
helm upgrade --install prometheus-stack prometheus-community/kube-prometheus-stack \
  -n monitoring --create-namespace \
  -f values.custom.yaml

# Apply Docker cAdvisor ServiceMonitor
kubectl apply -f docker-cadvisor-servicemonitor.yaml

# Apply Dashboards (optional, auto-loaded)
kubectl apply -f dashboards/docker-dashboard-configmap.yaml
kubectl apply -f dashboards/cadvisor-dashboard-configmap.yaml
```

## Access

- **Grafana**: http://localhost:30300 (user: `admin`, password: `admin`)
  - **Docker + System Dashboard**: General system monitoring (Dashboard 893)
  - **cAdvisor Exporter**: Container-focused metrics (Dashboard 14282) - **Recommended**
- **Alertmanager**: http://localhost:30903

## Monitoring Sources

1. **Kubelet cAdvisor** - K8s pods (job=`kubelet`)
2. **Docker cAdvisor** - hc-network containers (job=`docker-cadvisor`)

## Query Examples

```promql
# Docker containers memory
container_memory_working_set_bytes{cadvisor_source="docker-hc-network"}

# K8s pods CPU
rate(container_cpu_usage_seconds_total{job="kubelet"}[5m])
```

## Configuration Highlights

- **Timezone**: GMT+7 (Hanoi Time)
- **Retention**: 7 days
- **Scrape interval**: 30s
- **Security**: Only hc-network containers monitored (Minikube/system containers excluded)
