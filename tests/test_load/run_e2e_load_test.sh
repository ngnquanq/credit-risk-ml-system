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

REPORT_DIR="reports"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$REPORT_DIR"

PF_PIDS=()

cleanup() {
    echo ""
    echo "Cleaning up port-forwards..."
    for pid in "${PF_PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    echo -e "${GREEN}✓ Port-forwards stopped${NC}"
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
PGPASSWORD=ops_password psql -h localhost -p 6432 -U ops_admin -d operations -c "SELECT 1" > /dev/null 2>&1 && \
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

# Run load test (via PgBouncer on port 6432)
OPS_DB_PORT=6432 \
locust -f tests/test_load/locustfile_e2e_prediction.py \
    --host=localhost:9092 \
    --users "${USERS:-50}" \
    --spawn-rate "${SPAWN_RATE:-10}" \
    --run-time "${RUN_TIME:-5m}" \
    --headless \
    --html "${REPORT_DIR}/e2e_prediction_${TIMESTAMP}.html" \
    --csv "${REPORT_DIR}/e2e_prediction_${TIMESTAMP}"

echo ""
echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}  Test Complete!${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""
echo "Reports:"
echo "  HTML: ${REPORT_DIR}/e2e_prediction_${TIMESTAMP}.html"
echo "  CSV:  ${REPORT_DIR}/e2e_prediction_${TIMESTAMP}_stats.csv"
echo ""
