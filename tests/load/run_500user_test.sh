#!/bin/bash
# ============================================================================
# 500 Concurrent Users Load Test with PgBouncer Connection Pooling
# ============================================================================
#
# PURPOSE:
#   Test the ML pipeline with 500 concurrent users to validate:
#   - PgBouncer transaction pooling (1000 clients → 50 DB connections)
#   - PostgreSQL max_connections=500 configuration
#   - End-to-end prediction latency under high load
#
# ARCHITECTURE:
#   500 Locust Users → PgBouncer (port 6432) → PostgreSQL (max 50 connections)
#                    Transaction Pooling
#
# CONNECTION MODEL:
#   - WITHOUT PgBouncer: 500 users = 500 PostgreSQL connections (would fail at 200)
#   - WITH PgBouncer: 500 users share 50 PostgreSQL connections (10x multiplexing)
#
# PREREQUISITES:
#   1. PgBouncer running on port 6432 (docker compose -f services/core/docker-compose.operationaldb.yml up -d)
#   2. PostgreSQL max_connections=500
#   3. Full ML pipeline running (CDC, Flink, Feast, KServe)
#   4. Kafka running on localhost:39092
#
# CONFIGURATION:
#   - Users: 500 concurrent
#   - Spawn rate: 25 users/second (takes 20 seconds to ramp up)
#   - Run time: 5 minutes
#   - Report: reports/e2e_v17_500users.html
#
# ============================================================================

set -e  # Exit on error

echo "============================================================================"
echo "  500-User Load Test with PgBouncer Transaction Pooling"
echo "============================================================================"
echo ""

# Check prerequisites
echo "Checking prerequisites..."

# Check PgBouncer
if ! docker ps | grep -q ops_pgbouncer; then
    echo "ERROR: PgBouncer container not running"
    echo "Start with: cd services/core && docker compose -f docker-compose.operationaldb.yml up -d"
    exit 1
fi

# Check PostgreSQL
if ! docker exec ops_postgres psql -U ops_admin -d operations -c "SELECT 1;" > /dev/null 2>&1; then
    echo "ERROR: PostgreSQL not responding"
    exit 1
fi

# Verify max_connections
MAX_CONN=$(docker exec ops_postgres psql -U ops_admin -d operations -t -c "SHOW max_connections;" | xargs)
echo "✓ PostgreSQL max_connections: $MAX_CONN"

# Verify PgBouncer config
echo "✓ PgBouncer running on port 6432"
docker logs ops_pgbouncer 2>&1 | grep -E "pool_mode|max_client_conn|default_pool_size" | head -3

echo ""
echo "Starting load test..."
echo "  - Users: 500 concurrent"
echo "  - Spawn rate: 25 users/second"
echo "  - Duration: 5 minutes"
echo "  - PgBouncer: localhost:6432 (transaction pooling)"
echo ""

# Run Locust
locust -f tests/locustfile_e2e_prediction.py \
       --host=localhost:39092 \
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
echo "  3. PgBouncer connection pooling efficiency"
echo ""
echo "To check PgBouncer stats:"
echo "  docker logs ops_pgbouncer | grep -E 'pool|client'"
echo ""
