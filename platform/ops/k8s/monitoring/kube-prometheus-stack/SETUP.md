# Monitoring setup (kube-prometheus-stack)

Prometheus, Alertmanager, Grafana, kube-state-metrics and node-exporter for the Minikube cluster. Deployed by `make k8s-monitoring`, which runs:

```bash
helm upgrade --install kube-prometheus-stack ./kube-prometheus-stack \
  -n monitoring -f kube-prometheus-stack/values.custom.yaml
```

`values.custom.yaml` holds our overrides; everything else in this directory is the upstream chart.

## Access

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80
# Grafana: http://localhost:3000 (default admin / prom-operator; change it)
```

## What is scraped

- Kubelet / cAdvisor: CPU, memory and CFS throttling for every pod (used by `tests/test_load/capture_k8s_cycle_metrics.py`).
- kube-state-metrics and node-exporter.
- ServiceMonitors shipped by other charts (MLflow, KubeRay, MinIO) when their `serviceMonitor` option is enabled.

## Example queries

```promql
# CPU throttling ratio per pod (the load-test bottleneck signal)
sum by (pod) (rate(container_cpu_cfs_throttled_periods_total{namespace="data-services"}[5m]))
  / sum by (pod) (rate(container_cpu_cfs_periods_total{namespace="data-services"}[5m]))

# Pod memory
sum by (pod) (container_memory_working_set_bytes{namespace="kserve"})
```

The Docker-host cAdvisor dashboards and ServiceMonitor from the Docker Compose era were removed with that stack (ADR-0005).
