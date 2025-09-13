#!/bin/bash
"""
Flink Job Deployment Script
Builds and deploys the CDC to Features transformation job to Flink cluster.
"""

set -e

# Configuration
FLINK_JOB_MANAGER=${FLINK_JOB_MANAGER:-flink-jobmanager:8081}
KAFKA_BOOTSTRAP_SERVERS=${KAFKA_BOOTSTRAP_SERVERS:-broker:29092}
CDC_TOPIC=${CDC_TOPIC:-hc.applications.public.loan_applications}
FEATURES_TOPIC=${FEATURES_TOPIC:-hc.application_features}

echo "🚀 Deploying Flink CDC to Features transformation job..."
echo "   Job Manager: $FLINK_JOB_MANAGER"
echo "   Kafka Brokers: $KAFKA_BOOTSTRAP_SERVERS" 
echo "   Source Topic: $CDC_TOPIC"
echo "   Sink Topic: $FEATURES_TOPIC"

# Wait for Flink Job Manager to be ready
echo "⏳ Waiting for Flink Job Manager to be ready..."
timeout 60s bash -c 'until curl -f http://'$FLINK_JOB_MANAGER'/overview > /dev/null 2>&1; do sleep 2; done'

# Wait for Kafka to be ready
echo "⏳ Waiting for Kafka to be ready..."
timeout 60s bash -c 'until python3 -c "
from kafka import KafkaProducer
try:
    producer = KafkaProducer(bootstrap_servers=[\"'$KAFKA_BOOTSTRAP_SERVERS'\"], request_timeout_ms=5000)
    producer.close()
    print(\"Kafka ready\")
except: exit(1)
" 2>/dev/null; do sleep 2; done'

# Set environment variables for the job
export KAFKA_BOOTSTRAP_SERVERS
export CDC_SOURCE_TOPIC=$CDC_TOPIC
export SINK_TOPIC_FEATURES=$FEATURES_TOPIC

# Submit the PyFlink job
echo "📊 Submitting PyFlink CDC transformation job..."
flink run \
    -m $FLINK_JOB_MANAGER \
    -d \
    -py /opt/app/jobs/cdc_application_etl.py \
    -pyfs /opt/app/jobs \
    --pyFiles /opt/app/jobs/cdc_udfs.py

echo "✅ Flink job submitted successfully!"
echo "🔍 Monitor job status at: http://localhost:8085"

# Verify job is running
sleep 5
echo "📈 Checking job status..."
curl -s http://$FLINK_JOB_MANAGER/jobs | python3 -c "
import json, sys
data = json.load(sys.stdin)
jobs = data.get('jobs', [])
if jobs:
    job = jobs[0]
    print(f\"Job {job['id']}: {job['status']}\")
else:
    print('No jobs found')
"