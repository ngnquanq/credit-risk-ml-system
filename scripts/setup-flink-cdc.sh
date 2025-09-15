#!/bin/bash
"""
Complete Flink CDC Setup Script
Sets up Flink cluster and deploys the CDC to Features transformation job.
"""

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
NETWORK_NAME=${NETWORK_NAME:-hc-network}
KAFKA_BOOTSTRAP_SERVERS=${KAFKA_BOOTSTRAP_SERVERS:-broker:29092}
CDC_TOPIC=${CDC_TOPIC_PREFIX:-hc.applications}.public.loan_applications
FEATURES_TOPIC=${FEAST_TOPIC_APP_FEATURES:-hc.application_features}

echo -e "${BLUE}🚀 Setting up Flink CDC to Features Pipeline${NC}"
echo -e "${BLUE}============================================${NC}"

# Step 1: Ensure Docker network exists
echo -e "${YELLOW}📡 Ensuring Docker network exists...${NC}"
if ! docker network inspect $NETWORK_NAME >/dev/null 2>&1; then
    docker network create $NETWORK_NAME
    echo -e "${GREEN}✅ Created Docker network: $NETWORK_NAME${NC}"
else
    echo -e "${GREEN}✅ Docker network already exists: $NETWORK_NAME${NC}"
fi

# Step 2: Start Flink cluster
echo -e "${YELLOW}🏗️  Starting Flink cluster...${NC}"
cd /home/nhatquang/home-credit-credit-risk-model-stability/services/data
docker-compose -f docker-compose.flink.yml up -d

# Wait for Flink to be ready
echo -e "${YELLOW}⏳ Waiting for Flink Job Manager to be ready...${NC}"
timeout 120s bash -c '
while ! curl -f http://localhost:8085/overview > /dev/null 2>&1; do
    echo "   Waiting for Flink Job Manager..."
    sleep 5
done
'
echo -e "${GREEN}✅ Flink cluster is ready${NC}"

# Step 3: Create Kafka topics if they don't exist
echo -e "${YELLOW}📝 Creating Kafka topics...${NC}"
python3 - <<EOF
import sys
from kafka.admin import KafkaAdminClient, NewTopic
from kafka import KafkaProducer
from kafka.errors import TopicAlreadyExistsError

def create_topic(admin, topic_name, num_partitions=3, replication_factor=1):
    topic = NewTopic(
        name=topic_name,
        num_partitions=num_partitions,
        replication_factor=replication_factor
    )
    try:
        admin.create_topics([topic])
        print(f"✅ Created topic: {topic_name}")
    except TopicAlreadyExistsError:
        print(f"✅ Topic already exists: {topic_name}")
    except Exception as e:
        print(f"❌ Failed to create topic {topic_name}: {e}")

try:
    admin = KafkaAdminClient(
        bootstrap_servers=['localhost:9092'],
        request_timeout_ms=10000
    )
    
    # Create topics
    create_topic(admin, '${CDC_TOPIC}')
    create_topic(admin, '${FEATURES_TOPIC}')
    
    print("✅ All topics ready")
except Exception as e:
    print(f"❌ Failed to setup topics: {e}")
    sys.exit(1)
EOF

# Step 4: Deploy Flink job
echo -e "${YELLOW}🔧 Building and deploying Flink job...${NC}"
cd /home/nhatquang/home-credit-credit-risk-model-stability/services/data

# Build Flink job image
echo -e "${YELLOW}🏗️  Building Flink job image...${NC}"
docker-compose -f docker-compose.flink.yml build flink-job

# Deploy the job by recreating the job container
echo -e "${YELLOW}🚀 Deploying CDC transformation job...${NC}"
docker-compose -f docker-compose.flink.yml up -d flink-job

# Step 5: Verify deployment
echo -e "${YELLOW}🔍 Verifying deployment...${NC}"
sleep 10

# Check Flink job status
echo -e "${BLUE}📊 Flink Job Status:${NC}"
curl -s http://localhost:8085/jobs | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    jobs = data.get('jobs', [])
    if jobs:
        for job in jobs:
            status = job['status']
            color = '🟢' if status == 'RUNNING' else '🟡' if status == 'CREATED' else '🔴'
            print(f'{color} Job {job[\"id\"][:8]}: {status}')
    else:
        print('🟡 No jobs found yet (may still be starting)')
except:
    print('❌ Failed to get job status')
"

echo -e ""
echo -e "${GREEN}🎉 Flink CDC Pipeline Setup Complete!${NC}"
echo -e "${BLUE}📊 Flink Web UI: http://localhost:8085${NC}"
echo -e "${BLUE}📝 Source Topic: ${CDC_TOPIC}${NC}"
echo -e "${BLUE}📤 Features Topic: ${FEATURES_TOPIC}${NC}"
echo -e ""
echo -e "${YELLOW}💡 To test the pipeline:${NC}"
echo -e "   1. Send CDC messages to: ${CDC_TOPIC}"
echo -e "   2. Monitor features output on: ${FEATURES_TOPIC}"
echo -e "   3. Check logs: docker logs flink_job_submitter"