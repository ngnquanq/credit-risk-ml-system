#!/usr/bin/env bash
# Restore drill (E15): recover the operational DB from the MinIO backup into a new CloudNativePG
# cluster, then compare row counts with the live primary. Target: RPO <= 5 min, RTO <= 15 min.
#
#   scripts/chaos/restore.sh
#
# Writes reports/drills/<UTC date>-restore.md. Exits 1 when the RTO target is missed or data is short.
set -euo pipefail

NS=data-services
RESTORED=ops-db-restore
REPORT_DIR="reports/drills"
mkdir -p "$REPORT_DIR"
start=$(date +%s)
target_time="$(date -u -d '-1 minute' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -v-1M +%Y-%m-%dT%H:%M:%SZ)"

kubectl apply -f - <<MANIFEST
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: $RESTORED
  namespace: $NS
spec:
  instances: 1
  imageName: ghcr.io/cloudnative-pg/postgresql:16.4
  storage: {size: 5Gi}
  bootstrap:
    recovery:
      source: ops-db
      recoveryTarget: {targetTime: "$target_time"}
  externalClusters:
    - name: ops-db
      barmanObjectStore:
        destinationPath: s3://pg-backups/ops-db
        endpointURL: http://data-minio-server.data-services.svc:9000
        s3Credentials:
          accessKeyId: {name: minio-root-credentials, key: MINIO_ROOT_USER}
          secretAccessKey: {name: minio-root-credentials, key: MINIO_ROOT_PASSWORD}
MANIFEST

kubectl wait --for=condition=Ready "cluster/$RESTORED" -n "$NS" --timeout=1200s
rto=$(( $(date +%s) - start ))

count() {
  kubectl exec -n "$NS" "$1" -- psql -U postgres -d operations -At -c \
    "SELECT count(*) FROM loan_applications WHERE created_at <= '$target_time'"
}
live_primary=$(kubectl get pod -n "$NS" -l cnpg.io/cluster=ops-db,cnpg.io/instanceRole=primary -o name | head -1 | cut -d/ -f2)
live=$(count "$live_primary")
restored=$(count "${RESTORED}-1")
missing=$(( live - restored ))

result="PASS"
if [[ "$rto" -gt 900 || "$missing" -ne 0 ]]; then result="FAIL"; fi

cat > "$REPORT_DIR/$(date -u +%Y-%m-%d)-restore.md" <<REPORT
# Restore drill ($result)

| Measure | Value |
|---|---|
| Recovery target time | $target_time |
| Time to ready (RTO) | $rto s (target <= 900 s) |
| Applications up to the target time, live | $live |
| Applications up to the target time, restored | $restored |
| Missing | $missing |
REPORT

kubectl delete cluster "$RESTORED" -n "$NS" --wait=false
echo "Restore drill: $result"
[[ "$result" == "PASS" ]]
