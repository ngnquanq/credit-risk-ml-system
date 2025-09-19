# Feature Store Helm Chart

This chart mirrors the docker-compose setup in `services/ml/docker-compose.feature-store.yml`:
- Redis online store
- One-shot Feast apply job (`repository.py`)
- Long-running Feast stream materializer (`repository.py stream`)

## Images
Build and push your Feast repo image (contains `repository.py` etc.) from `application/feast/Dockerfile`:

```
# from repo root
cd application/feast
docker build -t <registry>/feast-repo:latest -f Dockerfile .
docker push <registry>/feast-repo:latest
```

Then set in values:
```
repo:
  image:
    repository: <registry>/feast-repo
    tag: latest
```

## Key values
- `global.kafkaBrokers`, `global.project`
- `global.clickhouse.host|port|database`
- `global.tsFields.app|ext|dwh`
- `redis.*` for Redis deployment/service
- `feastApply.*` and `feastStream.*` to control the job and deployment

## Install
```
helm install feature-store ./services/ml/k8s/feature-store \
  --namespace <ns> --create-namespace \
  -f your-values.yaml
```

## Notes
- The chart assumes your Feast code is baked into the repo image. If you prefer mounting a Git repo or ConfigMap, extend the templates accordingly.
- The stream deployment does not hard-wait for Redis; rely on retries/health or add an initContainer if needed.
 - Kafka is external (running in Docker). Use a bootstrap address reachable from your K8s pods (not `broker:29092`). For example:
   - Docker Desktop: `host.docker.internal:9092`
   - Linux host: `<node-ip>:<host-mapped-port>` from your Docker Compose Kafka
   Ensure Kafka `advertised.listeners` includes that reachable address/port.
