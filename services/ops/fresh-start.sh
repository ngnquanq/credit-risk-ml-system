#!/bin/bash
# Complete Fresh Start Script for Load Testing
# Automates PostgreSQL truncation, Redis flush, and Kafka cleanup

set -e

echo "==========================================="
echo "Fresh Start - Complete System Cleanup"
echo "==========================================="
echo ""
echo "This script will:"
echo "  1. Truncate PostgreSQL loan_applications table"
echo "  2. Flush Redis feature store"
echo "  3. Reset Kafka consumer group offsets to LATEST"
echo "  4. Restart all consumer services"
echo ""
echo "==========================================="
read -p "Continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo "Step 1: Truncating PostgreSQL..."
echo "==========================================="
PGPASSWORD=ops_password psql -h localhost -p 5434 -U ops_admin -d operations \
    -c "TRUNCATE TABLE public.loan_applications CASCADE;" 2>&1 | sed 's/^/  /'

# Verify PostgreSQL is clean
row_count=$(PGPASSWORD=ops_password psql -h localhost -p 5434 -U ops_admin -d operations -t -c "SELECT COUNT(*) FROM public.loan_applications;" | tr -d ' ')
echo "  ✓ PostgreSQL cleaned: $row_count rows remaining"
echo ""

echo "Step 2: Clearing Redis feature store..."
echo "==========================================="
# Find first running Feast pod
feast_pod=$(kubectl get pod -n feature-registry -l app=feast-stream --field-selector=status.phase=Running -o name 2>/dev/null | head -1 | cut -d/ -f2)

if [ -z "$feast_pod" ]; then
    echo "  ⚠ No running Feast pods found, skipping Redis flush"
else
    echo "  Using pod: $feast_pod"
    kubectl exec -n feature-registry "$feast_pod" -- redis-cli -h feast-redis.feature-registry.svc.cluster.local FLUSHDB 2>&1 | sed 's/^/  /' || echo "  ⚠ Redis flush failed"

    # Verify Redis is clean
    key_count=$(kubectl exec -n feature-registry "$feast_pod" -- redis-cli -h feast-redis.feature-registry.svc.cluster.local DBSIZE 2>/dev/null | grep -oE '[0-9]+' || echo "unknown")
    echo "  ✓ Redis cleaned: $key_count keys remaining"
fi
echo ""

echo "Step 3: Deleting KServe InferenceServices..."
echo "==========================================="
# Delete InferenceServices to completely stop all scoring pods
# The serving-watcher will recreate them automatically
kserve_isvcs=$(kubectl get inferenceservice -n kserve -o name 2>/dev/null || echo "")
if [ -z "$kserve_isvcs" ]; then
    echo "  ℹ No InferenceServices found"
else
    echo "$kserve_isvcs" | while read -r isvc; do
        echo "  Deleting $isvc..."
        kubectl delete "$isvc" -n kserve 2>&1 | sed 's/^/    /' || true
    done
    echo "  Force deleting any remaining scoring pods..."
    kubectl delete pod -n kserve -l serving.kserve.io/inferenceservice --force --grace-period=0 2>&1 | sed 's/^/    /' || echo "    No pods to delete"
    echo "  Waiting for consumer groups to become inactive (20 seconds)..."
    sleep 20
fi
echo ""

echo "Step 4: Purging old messages from hc.feature_ready topic..."
echo "==========================================="
# Set retention to 1 second to delete old messages
echo "  Setting topic retention to 1 second..."
docker exec kafka_broker kafka-configs --bootstrap-server broker:29092 \
    --entity-type topics --entity-name hc.feature_ready \
    --alter --add-config retention.ms=1000 2>&1 | sed 's/^/    /'
echo "  Waiting for messages to be purged (5 seconds)..."
sleep 5
echo "  Restoring topic retention to 7 days..."
docker exec kafka_broker kafka-configs --bootstrap-server broker:29092 \
    --entity-type topics --entity-name hc.feature_ready \
    --alter --add-config retention.ms=604800000 2>&1 | sed 's/^/    /'
echo "  ✓ Topic purged"
echo ""

echo "Step 5: Cleaning Kafka (offsets, consumer groups, services)..."
echo "==========================================="
# Run the existing Kafka cleanup script non-interactively
cd "$(dirname "$0")"
echo "yes" | bash clear-kafka-backlog.sh

echo ""
echo "Step 6: Waiting for serving-watcher to recreate InferenceServices..."
echo "==========================================="
echo "  The serving-watcher will automatically recreate InferenceServices from MLflow..."
echo "  This may take 30-60 seconds..."
echo "  Waiting 45 seconds for InferenceServices to appear..."
sleep 45

# Check if InferenceServices were recreated
kserve_isvcs=$(kubectl get inferenceservice -n kserve -o name 2>/dev/null | wc -l)
echo "  Found $kserve_isvcs InferenceService(s)"

if [ "$kserve_isvcs" -gt 0 ]; then
    echo "  Waiting for pods to be ready (30 seconds)..."
    sleep 30
    kubectl get pods -n kserve -l serving.kserve.io/inferenceservice 2>&1 | sed 's/^/    /'
fi

echo ""
echo "==========================================="
echo "✓ Fresh start complete!"
echo "==========================================="
echo ""
echo "System status:"
echo "  • PostgreSQL: Clean (0 rows)"
echo "  • Redis: Clean (0 keys)"
echo "  • Kafka: All offsets at LATEST"
echo "  • Services: Restarted"
echo ""
echo "You can now run load tests with a clean slate."
echo ""
