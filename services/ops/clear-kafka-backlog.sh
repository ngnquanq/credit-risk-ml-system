#!/bin/bash
# Clear Kafka Consumer Group Backlogs
# This resets all consumer groups to the latest offset (end of topic)
# Use this before load testing to ensure clean state

set -e

echo "=========================================="
echo "Kafka Backlog Cleaner"
echo "=========================================="
echo ""

# Kafka broker details
BROKER="broker:29092"
CONTAINER="kafka_broker"

# List of consumer groups to reset
CONSUMER_GROUPS=(
    "external-bureau-sink"
    "dwh-features-reader"
    "credit-risk-scoring"
    "feast-materializer-external"
    "feast-materializer-application"
    "feast-materializer-dwh"
)

echo "Step 1: Listing current consumer group lag..."
echo ""
for group in "${CONSUMER_GROUPS[@]}"; do
    echo "Consumer group: $group"
    docker exec "$CONTAINER" kafka-consumer-groups \
        --bootstrap-server "$BROKER" \
        --group "$group" \
        --describe 2>/dev/null | grep -E "GROUP|LAG" | head -5 || echo "  Group not found or no lag data"
    echo ""
done

echo "=========================================="
echo "WARNING: This will reset ALL consumer groups to LATEST offset!"
echo "All unprocessed messages will be SKIPPED."
echo "=========================================="
read -p "Continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo "Step 2: Stopping consumer services..."
echo ""

# Stop Docker-based consumers
echo "Stopping Docker query services..."
cd "$(dirname "$0")/../data" 2>/dev/null || cd ../data
docker compose -f docker-compose.query-services.yml down 2>&1 | sed 's/^/  /' || echo "  ⚠ Failed to stop query services"

# Stop Kubernetes-based consumers (Feast materializers)
echo "Scaling down Feast stream processors..."
kubectl scale deployment feast-stream -n feature-registry --replicas=0 2>&1 | sed 's/^/  /' || echo "  ⚠ Feast stream not found"

# Stop KServe serving pods (they also consume from Kafka)
echo "Scaling down KServe serving pods..."
isvc_list=$(kubectl get inferenceservice -A -o jsonpath='{range .items[*]}{.metadata.namespace}{" "}{.metadata.name}{"\n"}{end}' 2>/dev/null || echo "")
if [ -z "$isvc_list" ]; then
    echo "  ℹ No InferenceServices found"
else
    while IFS=' ' read -r ns isvc_name; do
        if [ -n "$isvc_name" ]; then
            predictor_deploy=$(kubectl get deployment -n "$ns" -l serving.kserve.io/inferenceservice="$isvc_name" -o name 2>/dev/null | head -1)
            if [ -n "$predictor_deploy" ]; then
                echo "  Scaling down $ns/$isvc_name..."
                kubectl scale "$predictor_deploy" -n "$ns" --replicas=0 2>&1 | sed 's/^/    /' || true
            fi
        fi
    done <<< "$isvc_list"
fi

# Wait a bit for consumers to disconnect
echo "Waiting for consumers to disconnect (15 seconds)..."
sleep 15
echo ""

echo "Step 3: Resetting consumer groups to latest offset..."
echo ""

for group in "${CONSUMER_GROUPS[@]}"; do
    echo "Resetting $group..."

    # Get all topics for this consumer group
    topics=$(docker exec "$CONTAINER" kafka-consumer-groups \
        --bootstrap-server "$BROKER" \
        --group "$group" \
        --describe 2>/dev/null | grep -v "TOPIC" | awk '{print $1}' | sort -u | grep -v "^$" || echo "")

    if [ -z "$topics" ]; then
        echo "  ⚠ No topics found for $group, skipping"
        continue
    fi

    # Reset to latest for each topic
    for topic in $topics; do
        echo "  Resetting topic: $topic"
        docker exec "$CONTAINER" kafka-consumer-groups \
            --bootstrap-server "$BROKER" \
            --group "$group" \
            --topic "$topic" \
            --reset-offsets \
            --to-latest \
            --execute 2>&1 | sed 's/^/    /' || echo "    ⚠ Failed to reset $topic"
    done
    echo "  ✓ $group reset complete"
    echo ""
done

echo ""
echo "Step 4: Restarting consumer services..."
echo ""

# Restart Docker-based consumers
echo "Restarting Docker query services..."
cd "$(dirname "$0")/../data" 2>/dev/null || cd ../data
docker compose -f docker-compose.query-services.yml up -d 2>&1 | sed 's/^/  /' || echo "  ⚠ Failed to start query services"

# Restart Kubernetes-based consumers
echo "Scaling up Feast stream processors..."
kubectl scale deployment feast-stream -n feature-registry --replicas=1 2>&1 | sed 's/^/  /' || echo "  ⚠ Feast stream not found"

# Restart KServe serving pods (scale back to 4 replicas each)
echo "Scaling up KServe serving pods..."
isvc_list=$(kubectl get inferenceservice -A -o jsonpath='{range .items[*]}{.metadata.namespace}{" "}{.metadata.name}{"\n"}{end}' 2>/dev/null || echo "")
if [ -z "$isvc_list" ]; then
    echo "  ℹ No InferenceServices found"
else
    while IFS=' ' read -r ns isvc_name; do
        if [ -n "$isvc_name" ]; then
            predictor_deploy=$(kubectl get deployment -n "$ns" -l serving.kserve.io/inferenceservice="$isvc_name" -o name 2>/dev/null | head -1)
            if [ -n "$predictor_deploy" ]; then
                echo "  Scaling up $ns/$isvc_name to 4 replicas..."
                kubectl scale "$predictor_deploy" -n "$ns" --replicas=4 2>&1 | sed 's/^/    /' || true
            fi
        fi
    done <<< "$isvc_list"
fi

echo "Waiting for services to start (10 seconds)..."
sleep 10
echo ""

echo "=========================================="
echo "Step 5: Verifying - checking new lag..."
echo "=========================================="
echo ""

for group in "${CONSUMER_GROUPS[@]}"; do
    echo "Consumer group: $group"
    docker exec "$CONTAINER" kafka-consumer-groups \
        --bootstrap-server "$BROKER" \
        --group "$group" \
        --describe 2>/dev/null | grep -E "PARTITION|LAG" | head -10 || echo "  No data"
    echo ""
done

echo "=========================================="
echo "✓ Backlog clear complete!"
echo "=========================================="
echo ""
echo "All consumer groups are now at LATEST offset (LAG = 0)."
echo "You can now start fresh with Locust load testing."
echo ""
