#!/usr/bin/env bash
# Failover drill (E15): delete one component under load and check that no application is lost
# and none is approved without a score while it is down.
#
#   TARGET=scoring|kafka-1|ops-db|api|decision-recorder|keycloak-0 scripts/chaos/drill.sh
#
# Env:
#   LOAD_CMD     command that generates load for the drill (default: Locust E2E test, 10 users, 10 min)
#   PSQL_POD     pod with psql access to the operational DB (default: ops-postgres-0)
#   SETTLE_SECS  wait after the load ends before counting (default: 300)
# Writes reports/drills/<UTC date>-<target>.md. Exits 1 when the drill fails.
set -euo pipefail

TARGET="${TARGET:?set TARGET}"
LOAD_CMD="${LOAD_CMD:-locust -f tests/test_load/locustfile_e2e_prediction.py --headless -u 10 -r 2 -t 10m}"
PSQL_POD="${PSQL_POD:-ops-postgres-0}"
SETTLE_SECS="${SETTLE_SECS:-300}"
REPORT_DIR="reports/drills"
mkdir -p "$REPORT_DIR"

case "$TARGET" in
  scoring)           NS=kserve;         SELECTOR="serving.kserve.io/inferenceservice";  WAIT="deployment" ;;
  kafka-1)           NS=data-services;  POD=kafka-broker-1;                          WAIT="statefulset/kafka-broker" ;;
  ops-db)            NS=data-services;  SELECTOR="cnpg.io/instanceRole=primary";       WAIT="cluster" ;;
  api)               NS=api-gateway;    SELECTOR="app=api-service";                    WAIT="deployment/api-service" ;;
  decision-recorder) NS=api-gateway;    SELECTOR="app=decision-recorder";              WAIT="deployment/decision-recorder" ;;
  keycloak-0)        NS=identity;       POD=keycloak-0;                                WAIT="statefulset/keycloak" ;;
  *) echo "unknown TARGET $TARGET" >&2; exit 2 ;;
esac

sql() {
  kubectl exec -n data-services "$PSQL_POD" -- psql -U ops_admin -d operations -At -c "$1"
}

started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Drill $TARGET started $started_at"

echo "Starting load: $LOAD_CMD"
bash -c "$LOAD_CMD" > "$REPORT_DIR/load-$TARGET.log" 2>&1 &
LOAD_PID=$!
sleep 60   # let traffic reach steady state

killed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
if [[ -n "${POD:-}" ]]; then
  kubectl delete pod -n "$NS" "$POD" --wait=false
else
  kubectl delete pod -n "$NS" -l "$SELECTOR" --wait=false
fi
kill_epoch=$(date +%s)

case "$WAIT" in
  deployment)  kubectl wait --for=condition=Ready pod -n "$NS" -l "$SELECTOR" --timeout=600s ;;
  cluster)     kubectl wait --for=condition=Ready cluster/ops-db -n "$NS" --timeout=600s ;;
  *)           kubectl rollout status "$WAIT" -n "$NS" --timeout=600s ;;
esac
recovered_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
recovery_secs=$(( $(date +%s) - kill_epoch ))

wait "$LOAD_PID" || true
echo "Load finished; settling ${SETTLE_SECS}s"
sleep "$SETTLE_SECS"

submitted=$(sql "SELECT count(*) FROM loan_applications WHERE created_at >= '$started_at'")
terminal=$(sql "SELECT count(DISTINCT sk_id_curr) FROM application_status_log
                WHERE sk_id_curr IN (SELECT sk_id_curr FROM loan_applications WHERE created_at >= '$started_at')
                  AND status IN ('approved','rejected','manual_review')")
lost=$(( submitted - terminal ))
# An approval without a score inside the fault window would mean a fallback approved (never allowed).
auto_approved=$(sql "SELECT count(*) FROM application_status_log
                     WHERE status = 'approved' AND created_by = 'decision-recorder'
                       AND created_at BETWEEN '$killed_at' AND '$recovered_at'
                       AND (metadata->>'score') IS NULL")
fallbacks=$(sql "SELECT count(*) FROM application_status_log
                 WHERE created_at >= '$killed_at' AND metadata->'reasons' ?| array['scoring_unavailable','features_incomplete']")

result="PASS"
if [[ "$lost" -ne 0 || "$auto_approved" -ne 0 ]]; then result="FAIL"; fi

report="$REPORT_DIR/$(date -u +%Y-%m-%d)-$TARGET.md"
cat > "$report" <<REPORT
# Drill: $TARGET ($result)

| Measure | Value |
|---|---|
| Started | $started_at |
| Pod deleted | $killed_at |
| Recovered | $recovered_at ($recovery_secs s) |
| Applications submitted | $submitted |
| Reached a terminal status | $terminal |
| Lost | $lost |
| Approved without a score during the fault | $auto_approved |
| Fallback decisions (manual review) | $fallbacks |

Pass criteria (E15): lost = 0 and approved without a score = 0.
REPORT
echo "Report: $report ($result)"
[[ "$result" == "PASS" ]]
