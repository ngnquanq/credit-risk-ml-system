#!/usr/bin/env bash
# scripts/restart-platform.sh
#
# Start (or resume) the Minikube ML platform and reconcile the bootstrap state
# that does NOT survive `minikube stop && minikube start`:
#
#   * Flink streaming jobs (JobManager has no HA backend; in-memory job graph
#     is lost on pod restart, and the flink-submit-* Jobs are one-shot).
#   * Debezium PostgreSQL connector (cdc-connector-init is a one-shot Job;
#     if Debezium's internal config topic state is ever lost or stale, the
#     connector silently disappears).
#
# Re-running this script is safe (idempotent): healthy components are left
# untouched.
#
# Usage:
#   ./scripts/restart-platform.sh                # full restart + reconcile
#   ./scripts/restart-platform.sh --skip-start   # cluster already up
#   ./scripts/restart-platform.sh --force-flink  # cancel & resubmit Flink jobs
#   ./scripts/restart-platform.sh --no-bounce    # don't restart consumers
#
set -euo pipefail

# ───────────────────────────── Config ─────────────────────────────────────
PROFILE="${MINIKUBE_PROFILE:-mlops}"
NS_DATA="data-services"
NS_FEAT="feature-registry"
FLINK_JM_DEPLOY="flink-jobmanager"
FLINK_JM_URL="http://flink-jobmanager:8081"
DEBEZIUM_DEPLOY="debezium-connect"
DEBEZIUM_URL="http://debezium-connect:8083"
CDC_CONNECTOR="postgres-application-connector"
EXPECTED_FLINK_JOB_COUNT=2

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FLINK_CDC_JOB="$REPO_ROOT/platform/data/k8s/stream-processing/02-flink-submit-cdc.yaml"
FLINK_BUREAU_JOB="$REPO_ROOT/platform/data/k8s/stream-processing/03-flink-submit-bureau.yaml"
DEBEZIUM_MANIFEST="$REPO_ROOT/platform/data/k8s/cdc/01-debezium.yaml"

# ───────────────────────────── Flags ──────────────────────────────────────
SKIP_START=0
FORCE_FLINK=0
NO_BOUNCE=0
for arg in "$@"; do
  case "$arg" in
    --skip-start)  SKIP_START=1 ;;
    --force-flink) FORCE_FLINK=1 ;;
    --no-bounce)   NO_BOUNCE=1 ;;
    -h|--help)
      sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "unknown flag: $arg (use --help)" >&2; exit 2 ;;
  esac
done

# ───────────────────────────── Output helpers ─────────────────────────────
if [[ -t 1 ]]; then
  G="\033[32m"; Y="\033[33m"; R="\033[31m"; B="\033[34m"; D="\033[2m"; N="\033[0m"
else
  G=""; Y=""; R=""; B=""; D=""; N=""
fi
log()   { printf "${B}[%s]${N} %s\n" "$(date +%H:%M:%S)" "$*"; }
ok()    { printf "  ${G}ok${N}   %s\n" "$*"; }
warn()  { printf "  ${Y}warn${N} %s\n" "$*"; }
err()   { printf "  ${R}err${N}  %s\n" "$*" >&2; }
phase() { printf "\n${B}═══ %s ═══${N}\n" "$*"; }

# ───────────────────────── Phase 1: Minikube ──────────────────────────────
start_minikube() {
  phase "Minikube profile '$PROFILE'"
  if [[ "$SKIP_START" == "1" ]]; then
    log "Skipping minikube start (--skip-start)"
  else
    minikube start -p "$PROFILE"
  fi
  kubectl config use-context "$PROFILE" >/dev/null
  ok "kubectl context = $PROFILE"
}

# ─────────────── Phase 2: Wait for core stateful services ─────────────────
wait_pods() {
  local ns="$1" selector="$2" timeout="${3:-300s}"
  log "Waiting for $ns/$selector (timeout $timeout)…"
  # Allow time for the pods to *appear* under the selector before waiting Ready
  local deadline=$((SECONDS + 60))
  while [[ $SECONDS -lt $deadline ]]; do
    if kubectl -n "$ns" get pod -l "$selector" -o name 2>/dev/null | grep -q .; then
      break
    fi
    sleep 3
  done
  if ! kubectl -n "$ns" wait --for=condition=Ready pod -l "$selector" --timeout="$timeout" >/dev/null 2>&1; then
    warn "$ns/$selector not Ready in $timeout — continuing"
    return 1
  fi
  ok "$ns/$selector Ready"
}

wait_core() {
  phase "Core data-services pods"
  wait_pods "$NS_DATA" "app=kafka-broker"      300s
  wait_pods "$NS_DATA" "app=ops-postgres"      180s
  wait_pods "$NS_DATA" "app=debezium-connect"  300s
  wait_pods "$NS_DATA" "app=flink-jobmanager"  240s
  wait_pods "$NS_DATA" "app=flink-taskmanager" 240s
}

# ───────────────── Phase 3: Reconcile Flink streaming jobs ────────────────
flink_jobs_overview() {
  kubectl -n "$NS_DATA" exec "deploy/$FLINK_JM_DEPLOY" -- \
    sh -c "curl -fsS $FLINK_JM_URL/jobs/overview" 2>/dev/null || true
}

flink_running_count() {
  # Number of Flink jobs currently in RUNNING state, queried via JM REST API.
  flink_jobs_overview | tr ',' '\n' | grep -c '"state":"RUNNING"' || true
}

flink_cancel_all_running() {
  log "Cancelling all currently-RUNNING Flink jobs…"
  local ids
  ids="$(flink_jobs_overview \
          | tr '{' '\n' \
          | awk -F'"' '/"state":"RUNNING"/ { for(i=1;i<=NF;i++) if($i=="jid"){print $(i+2); break} }')"
  for id in $ids; do
    kubectl -n "$NS_DATA" exec "deploy/$FLINK_JM_DEPLOY" -- flink cancel "$id" >/dev/null 2>&1 \
      && ok "cancelled $id" || warn "failed to cancel $id"
  done
}

flink_resubmit() {
  log "Re-running Flink submit Jobs…"
  kubectl -n "$NS_DATA" delete job flink-submit-pii flink-submit-bureau \
    --ignore-not-found --wait=true >/dev/null
  kubectl apply -f "$FLINK_CDC_JOB" >/dev/null
  kubectl apply -f "$FLINK_BUREAU_JOB" >/dev/null

  log "Waiting for submit Jobs to complete…"
  for j in flink-submit-pii flink-submit-bureau; do
    if kubectl -n "$NS_DATA" wait --for=condition=complete "job/$j" --timeout=180s >/dev/null 2>&1; then
      ok "$j completed"
    else
      warn "$j did not complete in 180s — see: kubectl logs job/$j -n $NS_DATA"
    fi
  done

  log "Verifying Flink jobs are RUNNING…"
  for _ in 1 2 3 4 5 6; do
    local n; n="$(flink_running_count)"
    if [[ "$n" -ge "$EXPECTED_FLINK_JOB_COUNT" ]]; then
      ok "$n Flink jobs RUNNING"
      return 0
    fi
    sleep 5
  done
  warn "Fewer than $EXPECTED_FLINK_JOB_COUNT RUNNING jobs after resubmit — inspect the JM pod"
}

reconcile_flink() {
  phase "Flink streaming jobs"
  local n; n="$(flink_running_count)"
  log "Currently $n RUNNING Flink job(s) (expected $EXPECTED_FLINK_JOB_COUNT)"

  if [[ "$FORCE_FLINK" == "1" ]]; then
    flink_cancel_all_running
    flink_resubmit
    return
  fi

  if [[ "$n" -ge "$EXPECTED_FLINK_JOB_COUNT" ]]; then
    ok "Flink jobs healthy — skipping"
    return
  fi

  if [[ "$n" -gt 0 ]]; then
    warn "Partial Flink state ($n/$EXPECTED_FLINK_JOB_COUNT). Cancelling stragglers to avoid duplicates."
    flink_cancel_all_running
  fi
  flink_resubmit
}

# ──────────────── Phase 4: Reconcile Debezium connector ───────────────────
dbz_curl_code() {
  kubectl -n "$NS_DATA" exec "deploy/$DEBEZIUM_DEPLOY" -- \
    sh -c "curl -s -o /dev/null -w '%{http_code}' '$1'" 2>/dev/null || echo "000"
}
dbz_curl_body() {
  kubectl -n "$NS_DATA" exec "deploy/$DEBEZIUM_DEPLOY" -- \
    sh -c "curl -fsS '$1' || true" 2>/dev/null || true
}

reconcile_debezium() {
  phase "Debezium CDC connector"
  local code state
  code="$(dbz_curl_code "$DEBEZIUM_URL/connectors/$CDC_CONNECTOR/status")"

  if [[ "$code" == "200" ]]; then
    state="$(dbz_curl_body "$DEBEZIUM_URL/connectors/$CDC_CONNECTOR/status" \
              | tr ',' '\n' | grep -o '"state":"[^"]*"' | head -1)"
    if echo "$state" | grep -q RUNNING; then
      ok "connector '$CDC_CONNECTOR' RUNNING"
      return
    fi
    warn "connector exists but state=$state — will recreate"
    kubectl -n "$NS_DATA" exec "deploy/$DEBEZIUM_DEPLOY" -- \
      sh -c "curl -fsS -X DELETE $DEBEZIUM_URL/connectors/$CDC_CONNECTOR" >/dev/null 2>&1 || true
  else
    warn "connector '$CDC_CONNECTOR' not registered (HTTP $code)"
  fi

  log "Re-running cdc-connector-init Job…"
  kubectl -n "$NS_DATA" delete job cdc-connector-init --ignore-not-found --wait=true >/dev/null
  kubectl apply -f "$DEBEZIUM_MANIFEST" >/dev/null

  if kubectl -n "$NS_DATA" wait --for=condition=complete job/cdc-connector-init --timeout=180s >/dev/null 2>&1; then
    ok "cdc-connector-init completed"
  else
    warn "cdc-connector-init did not complete in 180s — see: kubectl logs job/cdc-connector-init -n $NS_DATA"
  fi

  code="$(dbz_curl_code "$DEBEZIUM_URL/connectors/$CDC_CONNECTOR/status")"
  if [[ "$code" == "200" ]]; then
    ok "connector '$CDC_CONNECTOR' registered"
  else
    warn "connector still not responding (HTTP $code)"
  fi
}

# ─────────────── Phase 5: Bounce consumers (clean reconnect) ──────────────
bounce_consumers() {
  phase "Bounce stream consumers"
  if [[ "$NO_BOUNCE" == "1" ]]; then
    log "Skipping (--no-bounce)"
    return
  fi
  for d in bureau-consumer feature-consumer; do
    if kubectl -n "$NS_DATA" get deploy "$d" >/dev/null 2>&1; then
      kubectl -n "$NS_DATA" rollout restart "deploy/$d" >/dev/null
      ok "restarted $NS_DATA/$d"
    fi
  done
  if kubectl -n "$NS_FEAT" get deploy feast-stream >/dev/null 2>&1; then
    kubectl -n "$NS_FEAT" rollout restart deploy/feast-stream >/dev/null
    ok "restarted $NS_FEAT/feast-stream"
  fi
}

# ───────────────────────── Phase 6: Summary ───────────────────────────────
summary() {
  phase "Summary"
  printf "${D}data-services pods:${N}\n"
  kubectl -n "$NS_DATA" get pods --no-headers 2>/dev/null \
    | awk '{printf "  %-50s %-10s %s\n", $1, $3, $5}'
  printf "\n${D}Flink jobs (RUNNING):${N} %s\n" "$(flink_running_count)"
  kubectl -n "$NS_DATA" exec "deploy/$FLINK_JM_DEPLOY" -- flink list 2>/dev/null \
    | grep -E 'RUNNING|FINISHED|FAILED' | sed 's/^/  /' || true

  printf "\n${D}Debezium connector status:${N}\n"
  local body; body="$(dbz_curl_body "$DEBEZIUM_URL/connectors/$CDC_CONNECTOR/status")"
  if [[ -n "$body" ]]; then
    echo "$body" | sed 's/^/  /'
  else
    echo "  (no response)"
  fi

  printf "\n${G}Platform reconciliation finished.${N}\n"
}

main() {
  start_minikube
  wait_core
  reconcile_flink
  reconcile_debezium
  bounce_consumers
  summary
}

main "$@"
