# Logging (ECK: Elasticsearch, Kibana, Filebeat)

Centralized logs for every pod in the Minikube cluster. Deployed by `make k8s-logging`.

## What gets installed

| Component | How | Source |
|---|---|---|
| ECK operator | `helm upgrade --install elastic-operator ./eck-operator` | `eck-stack/eck-operator/` |
| Elasticsearch + Kibana | `helm upgrade --install elastic-stack ./eck-stack -f eck-values.custom.yaml` | `eck-stack/eck-stack/`, `eck-stack/eck-values.custom.yaml` |
| Filebeat DaemonSet | `kubectl apply -f eck-stack/filebeat-manifest.yaml` | ships container stdout (loguru JSON) from every node |
| Elasticsearch NodePort | `eck-stack/elasticsearch-nodeport-svc.yaml` | optional external access |

All resources live in the `logging` namespace.

## Use

```bash
make k8s-logging
kubectl get pods -n logging
kubectl port-forward -n logging svc/elastic-stack-eck-kibana-kb-http 5601:5601
```

Elasticsearch and Kibana need several GB of memory. On a 32 GB machine running the full platform they often stay `Pending`; the rest of the platform works without them.

## Notes

- The pre-ECK `elastic-stack/` Helm charts were removed; ECK is the only logging path.
- The Docker-host Filebeat and `k8s_gateway` forwarding from the old Docker Compose stack were removed together with that stack (ADR-0005).
