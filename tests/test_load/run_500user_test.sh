#!/bin/bash
# ============================================================================
# 500 Concurrent Users Load Test (K8s)
# ============================================================================
#
# PURPOSE:
#   Test the ML pipeline with 500 concurrent users to validate:
#   - PostgreSQL connection handling under high load
#   - End-to-end prediction latency under high load
#
# ARCHITECTURE:
#   500 Locust Users → port-forward → ops-pgbouncer (K8s, port 6432) → ops-postgres
#
# PREREQUISITES:
#   1. K8s cluster running with ops-postgres and kafka-broker pods healthy
#   2. Full ML pipeline running (CDC, Flink, Feast, KServe)
#
# CONFIGURATION:
#   - Users: 500 concurrent
#   - Spawn rate: 25 users/second (takes 20 seconds to ramp up)
#   - Run time: 5 minutes
#   - Report: reports/e2e_v17_500users.html
#
# ============================================================================

set -e

PF_PIDS=()

cleanup() {
    echo ""
    echo "Cleaning up port-forwards..."
    for pid in "${PF_PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    echo "✓ Port-forwards stopped"
}
trap cleanup EXIT

echo "============================================================================"
echo "  500-User Load Test (K8s)"
echo "============================================================================"
echo ""

# Check prerequisites
echo "Checking prerequisites..."

# Check K8s pods
echo "Checking ops-postgres pod..."
kubectl get pod -n data-services -l app=ops-postgres --no-headers 2>/dev/null | grep -q Running || {
    echo "ERROR: ops-postgres pod not running in data-services namespace"
    echo "Check with: kubectl get pods -n data-services"
    exit 1
}
echo "✓ ops-postgres pod running"

echo "Checking kafka-broker pod..."
kubectl get pod -n data-services -l app=kafka-broker --no-headers 2>/dev/null | grep -q Running || {
    echo "ERROR: kafka-broker pod not running in data-services namespace"
    echo "Check with: kubectl get pods -n data-services"
    exit 1
}
echo "✓ kafka-broker pod running"

# Start port-forwards
echo ""
echo "Starting port-forwards..."

kubectl port-forward -n data-services svc/ops-pgbouncer 6432:6432 > /dev/null 2>&1 &
PF_PIDS+=($!)

kubectl port-forward -n data-services svc/kafka-broker 9092:9092 > /dev/null 2>&1 &
PF_PIDS+=($!)

echo "Waiting for port-forwards to be ready..."
sleep 3

# Verify PostgreSQL via PgBouncer port-forward
PGPASSWORD=ops_password psql -h localhost -p 6432 -U ops_admin -d operations -c "SELECT 1;" > /dev/null 2>&1 || {
    echo "ERROR: PostgreSQL not responding via PgBouncer port-forward"
    exit 1
}
echo "✓ PostgreSQL connected via PgBouncer"

# Verify max_connections
MAX_CONN=$(kubectl exec -n data-services deploy/ops-postgres -- psql -U ops_admin -d operations -t -c "SHOW max_connections;" 2>/dev/null | xargs)
echo "✓ PostgreSQL max_connections: $MAX_CONN"

echo ""
echo "Starting load test..."
echo "  - Users: 500 concurrent"
echo "  - Spawn rate: 25 users/second"
echo "  - Duration: 5 minutes"
echo "  - PostgreSQL: localhost:6432 (PgBouncer port-forward)"
echo ""

mkdir -p reports

# Run Locust (via PgBouncer on port 6432)
OPS_DB_PORT=6432 \
locust -f tests/test_load/locustfile_e2e_prediction.py \
       --host=localhost:9092 \
       --users 500 \
       --spawn-rate 25 \
       --run-time 5m \
       --headless \
       --html reports/e2e_v17_500users.html \
       --csv reports/e2e_v17_500users

echo ""
echo "============================================================================"
echo "  Test Complete!"
echo "============================================================================"
echo ""
echo "Reports generated:"
echo "  - HTML: reports/e2e_v17_500users.html"
echo "  - CSV:  reports/e2e_v17_500users_*.csv"
echo ""
echo "Key Metrics to Check:"
echo "  1. PostgreSQL Insert Success Rate (should be near 100%)"
echo "  2. End-to-End Prediction Latency"
echo ""
