#!/bin/bash
# End-to-End Prediction Pipeline Load Test Runner (K8s)
#
# Starts port-forwards to Postgres and Kafka, then runs the locust load test.
# Port-forwards are cleaned up automatically on exit.

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

REPORT_DIR="${REPORT_DIR:-tests/test_load/reports}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$REPORT_DIR"
REPORT_PREFIX="${REPORT_DIR}/e2e_prediction_${TIMESTAMP}"
METRICS_START="${REPORT_PREFIX}_cadvisor_start.json"
METRICS_END="${REPORT_PREFIX}_cadvisor_end.json"
METRICS_CSV="${REPORT_PREFIX}_k8s_metrics.csv"
METRICS_MD="${REPORT_PREFIX}_k8s_metrics.md"
POST_RUN_STATE="${REPORT_PREFIX}_post_run_state.txt"
LOCUST_LOG="${REPORT_PREFIX}.log"
KAFKA_CHANNEL_START="${REPORT_PREFIX}_kafkachannel_start.json"
KAFKA_CHANNEL_AFTER_RUN="${REPORT_PREFIX}_kafkachannel_after_run.json"
KAFKA_CHANNEL_AFTER_DRAIN="${REPORT_PREFIX}_kafkachannel_after_drain.json"
KAFKA_CHANNEL_MD="${REPORT_PREFIX}_kafkachannel_offsets.md"
METRICS_SCRIPT="tests/test_load/capture_k8s_cycle_metrics.py"
KAFKA_CHANNEL_SCRIPT="tests/test_load/capture_kafka_channel_offsets.py"
KSERVE_INFERENCE_SERVICE="${KSERVE_INFERENCE_SERVICE:-credit-risk-v2}"
KSERVE_PREDICTOR_SERVICE="${KSERVE_INFERENCE_SERVICE}-predictor"

PF_PIDS=()
CLEANUP_STARTED=0
METRICS_STARTED=0

capture_metrics_start() {
    if [ "${CAPTURE_K8S_METRICS:-1}" != "1" ]; then
        return 0
    fi
    echo -e "${BLUE}Capturing K8s metrics snapshot (start)...${NC}"
    if "${PYTHON:-python}" "$METRICS_SCRIPT" snapshot --out "$METRICS_START"; then
        METRICS_STARTED=1
    else
        echo -e "${YELLOW}⚠ Failed to capture start K8s metrics snapshot${NC}"
    fi
}

capture_metrics_end() {
    if [ "$METRICS_STARTED" != "1" ]; then
        return 0
    fi
    echo -e "${BLUE}Capturing K8s metrics snapshot (end)...${NC}"
    if "${PYTHON:-python}" "$METRICS_SCRIPT" snapshot --out "$METRICS_END" && \
       "${PYTHON:-python}" "$METRICS_SCRIPT" summarize \
           --start "$METRICS_START" \
           --end "$METRICS_END" \
           --csv "$METRICS_CSV" \
           --markdown "$METRICS_MD"; then
        echo -e "${GREEN}✓ K8s metrics captured${NC}"
    else
        echo -e "${YELLOW}⚠ Failed to capture or summarize K8s metrics${NC}"
    fi
    METRICS_STARTED=0
}

capture_kafkachannel_offsets() {
    local phase="$1"
    local out="$2"
    local markdown="${3:-}"

    if [ "${CAPTURE_KAFKACHANNEL_OFFSETS:-1}" != "1" ]; then
        return 0
    fi
    if [ ! -f "$KAFKA_CHANNEL_SCRIPT" ]; then
        echo -e "${YELLOW}⚠ KafkaChannel offset capture script not found${NC}"
        return 0
    fi

    echo -e "${BLUE}Capturing KafkaChannel offsets (${phase})...${NC}"
    local args=(
        "$KAFKA_CHANNEL_SCRIPT"
        --phase "$phase"
        --out "$out"
        --timeout-seconds "${KAFKA_ADMIN_TIMEOUT_SECONDS:-15}"
    )
    if [ -n "$markdown" ]; then
        args+=(--markdown "$markdown")
    fi
    if "${PYTHON:-python}" "${args[@]}"; then
        return 0
    fi

    echo -e "${YELLOW}⚠ Failed to capture KafkaChannel offsets (${phase})${NC}"
    return 0
}

capture_post_run_state() {
    {
        echo "# Post-run State"
        echo
        date -u +"captured_at_utc=%Y-%m-%dT%H:%M:%SZ"
        echo
        echo "## Nodes"
        kubectl top nodes || true
        kubectl describe node mlops | sed -n '/Allocated resources:/,/Events:/p' || true
        echo
        echo "## KServe"
        kubectl get inferenceservice "$KSERVE_INFERENCE_SERVICE" -n kserve || true
        kubectl get ksvc "$KSERVE_PREDICTOR_SERVICE" -n kserve || true
        kubectl get revision -n kserve | grep "$KSERVE_PREDICTOR_SERVICE" || true
        kubectl get pods -n kserve -l "serving.kserve.io/inferenceservice=${KSERVE_INFERENCE_SERVICE}" -o wide || true
        echo
        echo "## Knative Eventing"
        kubectl get sequence,kafkasource,kafkasink,subscription -n kserve || true
        kubectl get kafkachannel scoring-pipeline-kn-sequence-0 -n kserve -o jsonpath='{.status.annotations.default\.topic}{"\n"}' 2>/dev/null || true
        echo
        echo "## KafkaChannel Effective Lag"
        for snapshot in "$KAFKA_CHANNEL_START" "$KAFKA_CHANNEL_AFTER_RUN" "$KAFKA_CHANNEL_AFTER_DRAIN"; do
            if [ -f "$snapshot" ]; then
                echo
                echo "### $(basename "$snapshot")"
                "${PYTHON:-python}" -c 'import json,sys; d=json.load(open(sys.argv[1])); print("phase=%s topic=%s selected_group=%s effective_lag=%s stale_lag=%s raw_lag=%s" % (d.get("phase"), d.get("topic"), d.get("selected_group") or "none", d["totals"]["effective_lag"], d["totals"]["stale_lag"], d["totals"]["raw_lag"]))' "$snapshot" || true
            fi
        done
        echo
        echo "## Kafka Consumer Groups"
        kubectl exec -n data-services kafka-broker-0 -- kafka-consumer-groups --bootstrap-server localhost:9092 --describe --group knative-scoring-consumer || true
        kubectl exec -n data-services kafka-broker-0 -- kafka-consumer-groups --bootstrap-server localhost:9092 --list | \
            grep '^kafka.kserve.scoring-pipeline-kn-sequence-0' | \
            while read -r group; do
                echo
                echo "### $group"
                kubectl exec -n data-services kafka-broker-0 -- kafka-consumer-groups --bootstrap-server localhost:9092 --describe --group "$group" || true
            done
    } > "$POST_RUN_STATE" 2>&1
    echo "Post-run state: ${POST_RUN_STATE}"
}

cleanup() {
    local status=$?
    local cleanup_status=0
    trap - EXIT

    capture_metrics_end

    echo ""
    echo "Cleaning up port-forwards..."
    for pid in "${PF_PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    echo -e "${GREEN}✓ Port-forwards stopped${NC}"

    if [[ "$CLEANUP_STARTED" == "1" ]]; then
        if [[ "${SKIP_CLEANUP:-0}" == "1" ]]; then
            echo -e "${YELLOW}Skipping load-test platform cleanup (SKIP_CLEANUP=1)${NC}"
        else
            echo ""
            echo -e "${BLUE}Resetting platform state after load test...${NC}"
            "$REPO_ROOT/scripts/cleanup_load_test.sh" --mode hard || cleanup_status=$?
            if [[ "$cleanup_status" -ne 0 ]]; then
                echo -e "${YELLOW}⚠ Load-test cleanup failed with exit code $cleanup_status${NC}"
                if [[ "$status" -eq 0 ]]; then
                    status="$cleanup_status"
                fi
            fi
        fi
    fi

    exit "$status"
}
trap cleanup EXIT

echo -e "${BLUE}======================================${NC}"
echo -e "${BLUE}  E2E Prediction Pipeline Load Test  ${NC}"
echo -e "${BLUE}        (K8s / port-forward)         ${NC}"
echo -e "${BLUE}======================================${NC}"
echo ""

# Check dependencies
echo "Checking prerequisites..."
pip show locust psycopg2-binary kafka-python > /dev/null 2>&1 || {
    echo "Installing dependencies..."
    pip install locust psycopg2-binary kafka-python
}
echo -e "${GREEN}✓ Dependencies installed${NC}"

if [[ "${SKIP_CLEANUP:-0}" == "1" ]]; then
    echo -e "${YELLOW}Skipping pre-run platform cleanup (SKIP_CLEANUP=1)${NC}"
elif [[ "${PRE_RUN_CLEANUP:-1}" == "1" ]]; then
    echo ""
    echo -e "${BLUE}Resetting platform state before load test...${NC}"
    "$REPO_ROOT/scripts/cleanup_load_test.sh" --mode hard
fi

capture_kafkachannel_offsets "before-run" "$KAFKA_CHANNEL_START" "$KAFKA_CHANNEL_MD"

# Check K8s pods
echo "Checking K8s pods..."
kubectl get pods -n data-services --no-headers 2>/dev/null | head -5
echo ""

# Start port-forwards
echo "Starting port-forwards..."

kubectl port-forward -n data-services svc/ops-pgbouncer 6432:6432 > /dev/null 2>&1 &
PF_PIDS+=($!)

kubectl port-forward -n data-services svc/kafka-broker 9092:9092 > /dev/null 2>&1 &
PF_PIDS+=($!)

echo "Waiting for port-forwards to be ready..."
sleep 3

# Check PostgreSQL (via PgBouncer)
echo "Checking PostgreSQL connection (via PgBouncer)..."
PGPASSWORD=${OPS_DB_PASSWORD:?OPS_DB_PASSWORD required} psql -h localhost -p 6432 -U ops_admin -d operations -c "SELECT 1" > /dev/null 2>&1 && \
    echo -e "${GREEN}✓ PostgreSQL connected (via PgBouncer)${NC}" || \
    echo -e "${YELLOW}⚠ PostgreSQL not accessible via PgBouncer (will fail during test)${NC}"

# Check Kafka
echo "Checking Kafka..."
nc -zv localhost 9092 > /dev/null 2>&1 && \
    echo -e "${GREEN}✓ Kafka accessible${NC}" || \
    echo -e "${YELLOW}⚠ Kafka not accessible on port 9092${NC}"

echo ""
echo -e "${YELLOW}Starting load test...${NC}"
echo ""
CLEANUP_STARTED=1
capture_metrics_start

# Run load test (via PgBouncer on port 6432)
if [ "${UI:-false}" = "true" ]; then
    echo "Starting Locust Web UI on http://localhost:8089 with 4 worker processes"
    OPS_DB_PORT=6432 \
    E2E_MONITOR_SAMPLE_PATH="${REPORT_PREFIX}_scoring_sample.json" \
    locust -f tests/test_load/locustfile_e2e_prediction.py \
        --host=localhost:9092 \
        --processes 4
else
    set +e
    OPS_DB_PORT=6432 \
    E2E_MONITOR_SAMPLE_PATH="${REPORT_PREFIX}_scoring_sample.json" \
    locust -f tests/test_load/locustfile_e2e_prediction.py \
        --host=localhost:9092 \
        --processes 4 \
        --users "${USERS:-50}" \
        --spawn-rate "${SPAWN_RATE:-1}" \
        --run-time "${RUN_TIME:-3m}" \
        --headless \
        --logfile "$LOCUST_LOG" \
        --html "${REPORT_PREFIX}.html" \
        --csv "${REPORT_PREFIX}"
    LOCUST_STATUS=$?
    set -e
fi

if [ -f "$LOCUST_LOG" ] && grep -q "FAIL:" "$LOCUST_LOG"; then
    echo -e "${YELLOW}⚠ Locust log contains monitor FAIL lines${NC}"
    LOCUST_STATUS=1
fi

capture_kafkachannel_offsets "after-run" "$KAFKA_CHANNEL_AFTER_RUN"

if [ "${POST_RUN_DRAIN_SECONDS:-0}" -gt 0 ]; then
    echo ""
    echo -e "${BLUE}Waiting ${POST_RUN_DRAIN_SECONDS}s for post-run pipeline drain...${NC}"
    sleep "${POST_RUN_DRAIN_SECONDS}"
fi
capture_kafkachannel_offsets "after-drain" "$KAFKA_CHANNEL_AFTER_DRAIN" "$KAFKA_CHANNEL_MD"
capture_post_run_state

if [ -f "$LOCUST_LOG" ] && grep -q "FAIL:" "$LOCUST_LOG"; then
    echo -e "${YELLOW}⚠ Locust log contains monitor FAIL lines${NC}"
    LOCUST_STATUS=1
fi

if [ "${UI:-false}" != "true" ] && [ "${LOCUST_STATUS:-0}" -ne 0 ]; then
    exit "$LOCUST_STATUS"
fi

echo ""
echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}  Test Complete!${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""
echo "Reports:"
echo "  HTML: ${REPORT_PREFIX}.html"
echo "  CSV:  ${REPORT_PREFIX}_stats.csv"
echo "  Log:  ${LOCUST_LOG}"
echo "  K8s:  ${METRICS_MD}"
echo "  KafkaChannel: ${KAFKA_CHANNEL_MD}"
echo ""
