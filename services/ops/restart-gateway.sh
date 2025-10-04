#!/bin/bash
# Helper script to restart k8s_gateway with current Kafka broker IP
# Run this after restarting Docker containers

set -e

cd "$(dirname "$0")"

# Get current Kafka broker IP
KAFKA_IP=$(docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' kafka_broker 2>/dev/null | head -1)

if [ -z "$KAFKA_IP" ]; then
    echo "ERROR: Cannot find kafka_broker container. Is it running?"
    echo "Start Kafka first with: docker start kafka_broker"
    exit 1
fi

echo "Detected Kafka broker IP: $KAFKA_IP"

# Export for docker-compose
export KAFKA_BROKER_IP=$KAFKA_IP

# Restart gateway
echo "Restarting k8s_gateway..."
docker compose -f docker-compose.gateway.yml down
docker compose -f docker-compose.gateway.yml up -d

echo "✓ Gateway restarted successfully"
docker logs k8s_gateway --tail=10
