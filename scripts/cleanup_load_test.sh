#!/usr/bin/env bash
# Reset the K8s prediction pipeline after E2E load tests.
#
# hard: destructive fast reset for local/dev load-test cleanup.
# soft: preserve Debezium slot/topic state and skip backlog by resetting offsets.

set -euo pipefail

MODE="hard"
NS_DATA="data-services"
NS_FEAST="feature-registry"
SKIP_WAIT=0
TIMEOUT_SECONDS=120
TEST_START_TS="${TEST_START_TS:-}"
KAFKA_ADMIN_TIMEOUT_SECONDS="${KAFKA_ADMIN_TIMEOUT_SECONDS:-15}"

DB_NAME="${OPS_DB_NAME:-operations}"
DB_USER="${OPS_DB_USER:-ops_admin}"
DB_PASSWORD="${OPS_DB_PASSWORD:-ops_password}"
DB_PGBOUNCER_HOST="ops-pgbouncer"
DB_DIRECT_HOST="ops-postgres"
DBZ_DEPLOY="debezium-connect"
DBZ_CONNECTOR="postgres-application-connector"
DBZ_URL="http://localhost:8083"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FLINK_CDC_JOB="$REPO_ROOT/platform/data/k8s/stream-processing/02-flink-submit-cdc.yaml"
FLINK_BUREAU_JOB="$REPO_ROOT/platform/data/k8s/stream-processing/03-flink-submit-bureau.yaml"
KAFKA_SOURCE="$REPO_ROOT/platform/ml/k8s/kserve/kafka-source.yaml"
KAFKA_SINK="$REPO_ROOT/platform/ml/k8s/kserve/kafka-sink.yaml"
KAFKA_DLQ_SINK="$REPO_ROOT/platform/ml/k8s/kserve/kafka-dlq-sink.yaml"
SCORING_SEQUENCE="$REPO_ROOT/platform/ml/k8s/kserve/scoring-sequence.yaml"
KAFKA_CHANNEL_OFFSETS="$REPO_ROOT/tests/test_load/capture_kafka_channel_offsets.py"

TOPICS=(
  "hc.applications.public.loan_applications"
  "hc.application_features"
  "hc.application_ext_raw"
  "hc.application_ext"
  "hc.application_dwh"
  "hc.feature_ready"
  "hc.scoring"
  "hc.scoring.dlq"
)

DELETE_ONLY_TOPICS=(
  "knative-messaging-kafka.kserve.scoring-pipeline-kn-sequence-0"
)

KNATIVE_CHANNEL_TOPIC_PATTERN="^knative-messaging-kafka\\.kserve\\.scoring-pipeline-kn-sequence-"
KNATIVE_SEQUENCE_GROUP_PATTERN="^kafka\\.kserve\\.scoring-pipeline-kn-sequence-0"

CONSUMER_GROUPS=(
  "bureau-consumer-group"
  "feature-consumer-group"
  "flink-cdc-applications"
  "flink-bureau-aggregation"
  "feast-materializer-application"
  "feast-materializer-external"
  "feast-materializer-dwh"
  "knative-scoring-consumer"
)

if [[ -t 1 ]]; then
  GREEN=$'\033[32m'
  YELLOW=$'\033[33m'
  BLUE=$'\033[34m'
  RED=$'\033[31m'
  NC=$'\033[0m'
else
  GREEN=""
  YELLOW=""
  BLUE=""
  RED=""
  NC=""
fi

log() { printf "${BLUE}[%s]${NC} %s\n" "$(date +%H:%M:%S)" "$*"; }
ok() { printf "  ${GREEN}ok${NC}   %s\n" "$*"; }
warn() { printf "  ${YELLOW}warn${NC} %s\n" "$*" >&2; }
die() { printf "  ${RED}err${NC}  %s\n" "$*" >&2; exit 1; }

usage() {
  cat <<EOF
Reset the K8s prediction pipeline after E2E load tests.

Modes:
  hard  Destructive fast reset for local/dev load-test cleanup.
  soft  Preserve Debezium slot/topic state and skip backlog by resetting offsets.

Usage:
  $0 [--mode hard|soft] [--namespace-data NAME] [--namespace-feast NAME]
     [--timeout-seconds N] [--skip-wait] [--test-start-ts TIMESTAMP]

Soft mode requires --test-start-ts or TEST_START_TS.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="${2:-}"
      shift 2
      ;;
    --namespace-data)
      NS_DATA="${2:-}"
      shift 2
      ;;
    --namespace-feast)
      NS_FEAST="${2:-}"
      shift 2
      ;;
    --timeout-seconds)
      TIMEOUT_SECONDS="${2:-}"
      shift 2
      ;;
    --skip-wait)
      SKIP_WAIT=1
      shift
      ;;
    --test-start-ts)
      TEST_START_TS="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      die "unknown argument: $1"
      ;;
  esac
done

[[ "$MODE" == "hard" || "$MODE" == "soft" ]] || die "--mode must be hard or soft"
[[ "$TIMEOUT_SECONDS" =~ ^[0-9]+$ ]] || die "--timeout-seconds must be numeric"
command -v kubectl >/dev/null 2>&1 || die "kubectl is required"

psql_exec() {
  local host="$1"
  local port="$2"
  local sql="$3"
  kubectl -n "$NS_DATA" exec ops-postgres-0 -- \
    env PGPASSWORD="$DB_PASSWORD" \
    psql -h "$host" -p "$port" -U "$DB_USER" -d "$DB_NAME" \
      -v ON_ERROR_STOP=1 -c "$sql"
}

kafka_exec() {
  kubectl -n "$NS_DATA" exec kafka-broker-0 -- timeout "$KAFKA_ADMIN_TIMEOUT_SECONDS" "$@"
}

kafka_sh() {
  kubectl -n "$NS_DATA" exec kafka-broker-0 -- bash -lc "$1"
}

dbz_http_code() {
  local method="$1"
  local path="$2"
  kubectl -n "$NS_DATA" exec "deploy/$DBZ_DEPLOY" -- \
    sh -c "curl -sS -o /dev/null -w '%{http_code}' -X '$method' '$DBZ_URL$path'" \
    2>/dev/null || printf "000"
}

dbz_body() {
  local path="$1"
  kubectl -n "$NS_DATA" exec "deploy/$DBZ_DEPLOY" -- \
    sh -c "curl -fsS '$DBZ_URL$path' || true" 2>/dev/null || true
}

dbz_accept_code() {
  local code="$1"
  [[ "$code" == "200" || "$code" == "202" || "$code" == "204" ]]
}

connector_exists() {
  local code
  code="$(dbz_http_code GET "/connectors/$DBZ_CONNECTOR/status")"
  [[ "$code" == "200" ]]
}

pause_debezium() {
  log "Pausing Debezium connector"
  local code
  code="$(dbz_http_code PUT "/connectors/$DBZ_CONNECTOR/pause")"
  if dbz_accept_code "$code"; then
    ok "Debezium pause requested"
    return 0
  fi
  [[ "$code" == "000" ]] && warn "Debezium Connect is not reachable; assuming CDC is already stopped" && return 0
  [[ "$code" == "404" ]] && warn "Debezium connector is not registered; nothing to pause" && return 0
  die "failed to pause Debezium connector (HTTP $code)"
}

stop_debezium_and_reset_offsets() {
  log "Stopping Debezium connector and resetting connector offsets"
  if ! connector_exists; then
    warn "Debezium connector is not registered; skipping connector offset reset"
    return 0
  fi

  local code
  code="$(dbz_http_code PUT "/connectors/$DBZ_CONNECTOR/stop")"
  if ! dbz_accept_code "$code"; then
    die "failed to stop Debezium connector before offset reset (HTTP $code)"
  fi

  local deadline=$((SECONDS + 30))
  while [[ $SECONDS -lt $deadline ]]; do
    if dbz_body "/connectors/$DBZ_CONNECTOR/status" | grep -q '"state":"STOPPED"'; then
      break
    fi
    sleep 1
  done

  code="$(dbz_http_code DELETE "/connectors/$DBZ_CONNECTOR/offsets")"
  if ! dbz_accept_code "$code"; then
    die "failed to reset Debezium connector offsets (HTTP $code)"
  fi
  ok "Debezium connector offsets reset"
}

resume_or_recreate_debezium() {
  log "Resuming Debezium connector"
  local code deadline
  deadline=$((SECONDS + 60))
  while [[ $SECONDS -lt $deadline ]]; do
    code="$(dbz_http_code GET "/connectors/$DBZ_CONNECTOR/status")"
    [[ "$code" != "000" ]] && break
    sleep 2
  done

  code="$(dbz_http_code PUT "/connectors/$DBZ_CONNECTOR/resume")"
  if dbz_accept_code "$code"; then
    ok "Debezium resume requested"
    return 0
  fi

  if [[ "$code" != "404" ]]; then
    warn "Debezium resume returned HTTP $code; attempting connector init job"
  fi

  kubectl -n "$NS_DATA" delete job cdc-connector-init --ignore-not-found --wait=true >/dev/null
  kubectl apply -f "$REPO_ROOT/platform/data/k8s/cdc/01-debezium.yaml" >/dev/null
  ok "cdc-connector-init job reapplied"
}

scale_debezium() {
  local replicas="$1"
  log "Scaling Debezium Connect to $replicas"
  kubectl -n "$NS_DATA" scale "deploy/$DBZ_DEPLOY" --replicas="$replicas" >/dev/null
  if [[ "$replicas" == "0" ]]; then
    local deadline=$((SECONDS + 60))
    while [[ $SECONDS -lt $deadline ]]; do
      if ! kubectl -n "$NS_DATA" get pods -l app=debezium-connect -o name 2>/dev/null | grep -q .; then
        ok "Debezium Connect scaled down"
        return 0
      fi
      sleep 2
    done
    warn "Debezium Connect pods still visible after scale-down timeout"
    return 0
  fi
  kubectl -n "$NS_DATA" rollout status "deploy/$DBZ_DEPLOY" --timeout=120s >/dev/null
  ok "Debezium Connect available"
}

truncate_loan_applications() {
  log "Truncating public.application_status_log and public.loan_applications through PgBouncer"
  psql_exec "$DB_PGBOUNCER_HOST" 6432 \
    "TRUNCATE TABLE public.application_status_log, public.loan_applications RESTART IDENTITY;" >/dev/null
  ok "application_status_log and loan_applications truncated"
}

delete_soft_rows() {
  [[ -n "$TEST_START_TS" ]] || die "soft mode requires --test-start-ts or TEST_START_TS"
  [[ "$TEST_START_TS" =~ ^[0-9TZ:+\ ._-]+$ ]] || die "--test-start-ts contains unsupported characters"

  log "Deleting load-test rows created at or after $TEST_START_TS"
  psql_exec "$DB_PGBOUNCER_HOST" 6432 \
    "DELETE FROM public.loan_applications WHERE created_at >= '$TEST_START_TS'::timestamptz;" >/dev/null
  ok "soft-mode rows deleted"
}

drop_cdc_pg_state() {
  log "Dropping Debezium replication slot/publication"
  psql_exec "$DB_DIRECT_HOST" 5432 \
    "SELECT pg_drop_replication_slot(slot_name) FROM pg_replication_slots WHERE slot_name = 'debezium_slot';" >/dev/null
  psql_exec "$DB_DIRECT_HOST" 5432 "DROP PUBLICATION IF EXISTS debezium_pub;" >/dev/null
  ok "Debezium slot/publication reset"
}

wipe_kafka_topics() {
  log "Resetting load-test Kafka topics"
  local topic_words=""
  local delete_only_topic_words=""
  local topic
  for topic in "${TOPICS[@]}"; do
    topic_words+=" '$topic'"
  done
  for topic in "${DELETE_ONLY_TOPICS[@]}"; do
    delete_only_topic_words+=" '$topic'"
  done

  kafka_sh "
    set -euo pipefail
    admin_timeout='$KAFKA_ADMIN_TIMEOUT_SECONDS'
    kafka_topic() {
      timeout \"\$admin_timeout\" kafka-topics --bootstrap-server localhost:9092 \"\$@\"
    }
    kafka_offsets() {
      timeout \"\$admin_timeout\" kafka-get-offsets --bootstrap-server localhost:9092 \"\$@\"
    }
    kafka_delete_records() {
      timeout \"\$admin_timeout\" kafka-delete-records --bootstrap-server localhost:9092 \"\$@\"
    }
    topic_exists() {
      kafka_topic --describe --topic \"\$1\" >/dev/null 2>&1
    }
    ensure_topic() {
      local topic=\"\$1\"
      if topic_exists \"\$topic\"; then
        kafka_topic --alter --topic \"\$topic\" --partitions 4 >/dev/null 2>&1 || true
      else
        kafka_topic --create --if-not-exists --topic \"\$topic\" --partitions 4 --replication-factor 1 >/dev/null
      fi
    }
    truncate_topic() {
      local topic=\"\$1\"
      local offsets json first line partition offset
      offsets=\"\$(kafka_offsets --topic \"\$topic\" --time latest 2>/dev/null || true)\"
      [[ -n \"\$offsets\" ]] || return 0
      json=\"/tmp/delete-records-\${topic//[^A-Za-z0-9]/_}.json\"
      printf '{\"partitions\":[' > \"\$json\"
      first=1
      while IFS=: read -r _ partition offset; do
        [[ -n \"\$partition\" && -n \"\$offset\" ]] || continue
        if [[ \"\$first\" == \"0\" ]]; then
          printf ',' >> \"\$json\"
        fi
        printf '{\"topic\":\"%s\",\"partition\":%s,\"offset\":%s}' \"\$topic\" \"\$partition\" \"\$offset\" >> \"\$json\"
        first=0
      done <<< \"\$offsets\"
      printf '],\"version\":1}\n' >> \"\$json\"
      if [[ \"\$first\" == \"0\" ]]; then
        kafka_delete_records --offset-json-file \"\$json\" >/dev/null || true
      fi
      rm -f \"\$json\"
    }
    topics=($topic_words)
    delete_only_topics=($delete_only_topic_words)
    while IFS= read -r topic; do
      [[ -n \"\$topic\" ]] && delete_only_topics+=(\"\$topic\")
    done < <(kafka_topic --list 2>/dev/null | grep -E '$KNATIVE_CHANNEL_TOPIC_PATTERN' || true)
    for topic in \"\${topics[@]}\"; do
      ensure_topic \"\$topic\"
      truncate_topic \"\$topic\"
    done
    for topic in \"\${delete_only_topics[@]}\"; do
      if topic_exists \"\$topic\"; then
        truncate_topic \"\$topic\"
      fi
    done
  "
  ok "Kafka topics exist and records were truncated"
}

reset_knative_sequence_groups() {
  log "Resetting Knative Sequence KafkaChannel consumer groups"
  kafka_sh "
    set -euo pipefail
    admin_timeout='$KAFKA_ADMIN_TIMEOUT_SECONDS'
    kafka_groups() {
      timeout \"\$admin_timeout\" kafka-consumer-groups --bootstrap-server localhost:9092 \"\$@\"
    }
    while IFS= read -r group; do
      [[ -n \"\$group\" ]] || continue
      describe=\"\$(kafka_groups --describe --group \"\$group\" 2>/dev/null || true)\"
      if printf '%s\n' \"\$describe\" | awk '\$1 != \"GROUP\" && \$4 ~ /^-?[0-9]+$/ { found = 1 } END { exit(found ? 0 : 1) }'; then
        kafka_groups --group \"\$group\" --reset-offsets --to-latest --all-topics --execute >/dev/null 2>&1 || true
      fi
      kafka_groups --delete --group \"\$group\" >/dev/null 2>&1 || true
    done < <(kafka_groups --list 2>/dev/null | grep -E '$KNATIVE_SEQUENCE_GROUP_PATTERN' || true)
  "
  ok "Knative Sequence KafkaChannel consumer groups reset/deleted"
}

flush_redis_db() {
  local db="$1"
  log "Flushing Feast Redis DB $db"
  kubectl -n "$NS_FEAST" exec deploy/feast-redis -- redis-cli -n "$db" FLUSHDB >/dev/null
  ok "Redis DB $db flushed"
}

restart_deploy_if_exists() {
  local ns="$1"
  local deploy="$2"
  if ! kubectl -n "$ns" get deploy "$deploy" >/dev/null 2>&1; then
    warn "$ns/$deploy not found; skipping restart"
    return 0
  fi
  kubectl -n "$ns" rollout restart "deploy/$deploy" >/dev/null
  kubectl -n "$ns" rollout status "deploy/$deploy" --timeout=120s >/dev/null
  ok "restarted $ns/$deploy"
}

restart_stateful_workloads() {
  log "Restarting stream consumers and Flink"
  restart_deploy_if_exists "$NS_DATA" bureau-consumer
  restart_deploy_if_exists "$NS_DATA" feature-consumer
  restart_deploy_if_exists "$NS_FEAST" feast-stream
  restart_deploy_if_exists "$NS_DATA" flink-jobmanager
  restart_deploy_if_exists "$NS_DATA" flink-taskmanager
}

delete_knative_pipeline() {
  log "Deleting Knative Sequence/KafkaSource/KafkaSink resources"
  kubectl delete -f "$KAFKA_SOURCE" -f "$SCORING_SEQUENCE" -f "$KAFKA_SINK" -f "$KAFKA_DLQ_SINK" \
    --ignore-not-found=true >/dev/null
  ok "Knative Sequence and Kafka resources deleted"
}

apply_knative_pipeline() {
  log "Applying Knative Sequence/KafkaSource/KafkaSink resources"
  kubectl apply -f "$KAFKA_SINK" -f "$KAFKA_DLQ_SINK" -f "$SCORING_SEQUENCE" -f "$KAFKA_SOURCE" >/dev/null
  ok "Knative Sequence and Kafka resources applied"
}

assert_kafka_channel_effective_lag_zero() {
  [[ -x "$KAFKA_CHANNEL_OFFSETS" || -f "$KAFKA_CHANNEL_OFFSETS" ]] || {
    warn "KafkaChannel offset capture script not found; skipping effective-lag assertion"
    return 0
  }

  log "Asserting regenerated Sequence KafkaChannel has no effective backlog"
  local out="/tmp/scoring-pipeline-kafkachannel-clean.json"
  local deadline=$((SECONDS + 60))
  while [[ $SECONDS -lt $deadline ]]; do
    if "${PYTHON:-python}" "$KAFKA_CHANNEL_OFFSETS" \
        --phase cleanup-ready \
        --out "$out" \
        --data-namespace "$NS_DATA" \
        --kserve-namespace kserve \
        --timeout-seconds "$KAFKA_ADMIN_TIMEOUT_SECONDS" \
        --max-effective-lag 0 >/tmp/scoring-pipeline-kafkachannel-clean.log 2>&1; then
      ok "Sequence KafkaChannel effective backlog is zero"
      return 0
    fi
    sleep 3
  done
  cat /tmp/scoring-pipeline-kafkachannel-clean.log >&2 || true
  die "Sequence KafkaChannel has effective backlog after cleanup"
}

recreate_knative_pipeline() {
  delete_knative_pipeline
  apply_knative_pipeline
}

delete_knative_source() {
  log "Deleting Knative KafkaSource to release its consumer group"
  kubectl delete -f "$KAFKA_SOURCE" --ignore-not-found=true >/dev/null
  ok "KafkaSource deleted"
}

apply_knative_source() {
  log "Reapplying Knative KafkaSource"
  kubectl apply -f "$KAFKA_SOURCE" >/dev/null
  ok "KafkaSource applied"
}

flink_running_ids() {
  local body
  body="$(kubectl -n "$NS_DATA" exec deploy/flink-jobmanager -- \
    sh -c "curl -fsS http://flink-jobmanager:8081/jobs/overview" 2>/dev/null || true)"
  printf "%s" "$body" |
    tr "{" "\n" |
    awk -F'"' '/"state":"RUNNING"/ { for (i = 1; i <= NF; i++) if ($i == "jid") { print $(i + 2); break } }'
}

cancel_flink_jobs() {
  log "Cancelling running Flink jobs"
  local ids id
  ids="$(flink_running_ids)"
  if [[ -z "$ids" ]]; then
    ok "no running Flink jobs to cancel"
    return 0
  fi
  for id in $ids; do
    kubectl -n "$NS_DATA" exec deploy/flink-jobmanager -- flink cancel "$id" >/dev/null || \
      warn "failed to cancel Flink job $id"
  done
  ok "Flink cancel requests sent"
}

resubmit_flink_jobs() {
  log "Resubmitting Flink one-shot submit jobs"
  kubectl -n "$NS_DATA" delete job flink-submit-pii flink-submit-bureau \
    --ignore-not-found --wait=true >/dev/null
  kubectl apply -f "$FLINK_CDC_JOB" -f "$FLINK_BUREAU_JOB" >/dev/null
  ok "Flink submit jobs applied"
}

declare -a RESTORE_REPLICAS=()

record_and_scale_down() {
  local ns="$1"
  local deploy="$2"
  local replicas
  replicas="$(kubectl -n "$ns" get deploy "$deploy" -o jsonpath='{.spec.replicas}' 2>/dev/null || true)"
  if [[ -z "$replicas" ]]; then
    warn "$ns/$deploy not found; skipping scale-down"
    return 0
  fi
  RESTORE_REPLICAS+=("$ns:$deploy:$replicas")
  kubectl -n "$ns" scale "deploy/$deploy" --replicas=0 >/dev/null
  ok "scaled $ns/$deploy to 0"
}

restore_scaled_deployments() {
  local item ns deploy replicas
  log "Restoring scaled deployments"
  for item in "${RESTORE_REPLICAS[@]}"; do
    IFS=: read -r ns deploy replicas <<<"$item"
    kubectl -n "$ns" scale "deploy/$deploy" --replicas="$replicas" >/dev/null
    kubectl -n "$ns" rollout status "deploy/$deploy" --timeout=120s >/dev/null
    ok "restored $ns/$deploy to $replicas"
  done
}

reset_group_to_latest() {
  local group="$1"
  local describe
  describe="$(kafka_exec kafka-consumer-groups --bootstrap-server localhost:9092 \
    --describe --group "$group" 2>&1 || true)"
  if ! printf "%s\n" "$describe" | awk '$1 != "GROUP" && $6 ~ /^-?[0-9]+$/ { found = 1 } END { exit(found ? 0 : 1) }'; then
    ok "consumer group $group has no offsets; skipping"
    return 0
  fi

  kafka_exec kafka-consumer-groups --bootstrap-server localhost:9092 \
    --group "$group" --reset-offsets --to-latest --all-topics --execute >/dev/null
  ok "consumer group $group reset to latest"
}

consumer_group_lag_sum() {
  local group="$1"
  local out
  out="$(kafka_exec kafka-consumer-groups --bootstrap-server localhost:9092 \
    --describe --group "$group" 2>&1 || true)"
  printf "%s\n" "$out" |
    awk '
      BEGIN { sum = 0; found = 0 }
      $1 != "GROUP" && $6 ~ /^-?[0-9]+$/ { sum += $6; found = 1 }
      END { if (found) print sum; else print 0 }
    '
}

flink_running_count() {
  flink_running_ids | wc -l | tr -d " "
}

jobs_complete() {
  local job status
  for job in flink-submit-pii flink-submit-bureau; do
    status="$(kubectl -n "$NS_DATA" get job "$job" \
      -o jsonpath='{.status.conditions[?(@.type=="Complete")].status}' 2>/dev/null || true)"
    [[ "$status" == *"True"* ]] || return 1
  done
}

debezium_running() {
  dbz_body "/connectors/$DBZ_CONNECTOR/status" | grep -q '"state":"RUNNING"'
}

all_consumer_lag_zero() {
  local group lag
  for group in "${CONSUMER_GROUPS[@]}"; do
    lag="$(consumer_group_lag_sum "$group")"
    [[ "$lag" -le 0 ]] || return 1
  done
}

wait_ready() {
  [[ "$SKIP_WAIT" == "0" ]] || { warn "Skipping readiness wait"; return 0; }

  log "Waiting for clean ready state (timeout ${TIMEOUT_SECONDS}s)"
  local deadline=$((SECONDS + TIMEOUT_SECONDS))
  local running
  while [[ $SECONDS -lt $deadline ]]; do
    running="$(flink_running_count)"
    if jobs_complete && [[ "$running" -ge 2 ]] && all_consumer_lag_zero && debezium_running; then
      ok "Flink jobs complete and 2 jobs RUNNING"
      ok "consumer group lag is zero or empty"
      ok "Debezium connector RUNNING"
      return 0
    fi
    sleep 5
  done

  warn "Flink submit jobs complete: $(jobs_complete && printf yes || printf no)"
  warn "Flink RUNNING jobs: $(flink_running_count)"
  warn "Debezium RUNNING: $(debezium_running && printf yes || printf no)"
  local group
  for group in "${CONSUMER_GROUPS[@]}"; do
    warn "lag $group: $(consumer_group_lag_sum "$group")"
  done
  die "cleanup did not reach ready state within ${TIMEOUT_SECONDS}s"
}

hard_reset() {
  log "Starting hard load-test cleanup"
  stop_debezium_and_reset_offsets
  scale_debezium 0
  delete_knative_pipeline
  truncate_loan_applications
  drop_cdc_pg_state
  wipe_kafka_topics
  reset_knative_sequence_groups
  flush_redis_db 0
  flush_redis_db 1
  restart_stateful_workloads
  apply_knative_pipeline
  resubmit_flink_jobs
  scale_debezium 1
  resume_or_recreate_debezium
  wait_ready
  assert_kafka_channel_effective_lag_zero
}

soft_reset() {
  log "Starting soft load-test cleanup"
  pause_debezium
  delete_soft_rows
  record_and_scale_down "$NS_DATA" bureau-consumer
  record_and_scale_down "$NS_DATA" feature-consumer
  record_and_scale_down "$NS_FEAST" feast-stream
  delete_knative_source
  cancel_flink_jobs
  sleep 5
  local group
  for group in "${CONSUMER_GROUPS[@]}"; do
    reset_group_to_latest "$group"
  done
  reset_knative_sequence_groups
  flush_redis_db 1
  restore_scaled_deployments
  apply_knative_source
  resubmit_flink_jobs
  resume_or_recreate_debezium
  wait_ready
}

case "$MODE" in
  hard) hard_reset ;;
  soft) soft_reset ;;
esac

ok "load-test cleanup completed ($MODE)"
