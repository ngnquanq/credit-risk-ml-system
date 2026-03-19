#!/bin/bash
# Flink Job Deployment Script
# Called by Jenkins CI/CD pipeline to deploy new Flink jobs
#
# This script:
# 1. Backs up current job state
# 2. Cancels running Flink jobs
# 3. Updates docker-compose with new image
# 4. Submits new jobs
# 5. Verifies deployment succeeded

set -euo pipefail

# Environment variables from Jenkins
FLINK_REST_API="${FLINK_REST_API:-http://flink-jobmanager:8081}"
IMAGE_NAME="${IMAGE_NAME:-hc-flink-jobs:latest}"
BACKUP_DIR="${BACKUP_DIR:-/var/jenkins_home/backups/latest}"
BUILD_ID="${BUILD_ID:-manual}"

echo "==================================================================="
echo "Flink Job Deployment Script"
echo "==================================================================="
echo "Flink REST API: ${FLINK_REST_API}"
echo "New Image: ${IMAGE_NAME}"
echo "Backup Directory: ${BACKUP_DIR}"
echo "Build ID: ${BUILD_ID}"
echo "==================================================================="

# Function: Get running job IDs
get_running_jobs() {
    curl -s "${FLINK_REST_API}/jobs/overview" | \
        jq -r '.jobs[] | select(.state=="RUNNING") | .jid' 2>/dev/null || echo ""
}

# Function: Cancel job (simple cancel, no savepoint for POC)
cancel_job() {
    local JOB_ID=$1
    echo "Cancelling job ${JOB_ID}..."

    curl -s -X PATCH "${FLINK_REST_API}/jobs/${JOB_ID}?mode=cancel" || {
        echo "WARNING: Failed to cancel job ${JOB_ID}"
        return 1
    }

    echo "✓ Job ${JOB_ID} cancelled"
    return 0
}

# Step 1: Create backup directory
echo ""
echo "Step 1: Creating backup directory..."
mkdir -p "${BACKUP_DIR}"

# Step 2: Backup current job state
echo ""
echo "Step 2: Backing up current job state..."
RUNNING_JOBS=$(get_running_jobs)

if [ -n "$RUNNING_JOBS" ]; then
    echo "$RUNNING_JOBS" > "${BACKUP_DIR}/running_jobs.txt"
    JOB_COUNT=$(echo "$RUNNING_JOBS" | wc -l)
    echo "Found ${JOB_COUNT} running jobs:"
    echo "$RUNNING_JOBS"
else
    echo "No running jobs found (may be first deployment)"
    echo "" > "${BACKUP_DIR}/running_jobs.txt"
fi

# Save current image tag for rollback
echo "${IMAGE_NAME}" > "${BACKUP_DIR}/deployed_image.txt"

# Step 3: Cancel old jobs
echo ""
echo "Step 3: Cancelling old jobs..."
if [ -n "$RUNNING_JOBS" ]; then
    while IFS= read -r JOB_ID; do
        if [ -n "$JOB_ID" ]; then
            cancel_job "$JOB_ID" || echo "Continuing despite cancellation failure..."
        fi
    done <<< "$RUNNING_JOBS"

    # Wait for jobs to fully terminate
    echo "Waiting for jobs to terminate..."
    sleep 5
else
    echo "No jobs to cancel"
fi

# Step 4: Update docker-compose with new image
echo ""
echo "Step 4: Updating docker-compose.flink.yml with new image..."

# Update image tag in docker-compose file
sed -i.bak "s|image: hc-flink-jobs:.*|image: ${IMAGE_NAME}|g" \
    services/data/docker-compose.flink.yml

echo "✓ Updated docker-compose.flink.yml"

# Step 5: Submit new jobs
echo ""
echo "Step 5: Submitting new Flink jobs..."

# Restart job submission containers (they will use the new image)
docker compose -f services/data/docker-compose.flink.yml up -d flink-job-pii flink-job-bureau

echo "Waiting for job submission to complete..."
# Wait for submission containers to exit (they run 'flink run -d' then exit)
sleep 15

# Step 6: Verify new jobs are running
echo ""
echo "Step 6: Verifying deployment..."

# Wait a bit more for jobs to start
sleep 10

NEW_JOBS=$(get_running_jobs)
NEW_JOB_COUNT=$(echo "$NEW_JOBS" | grep -c . || echo "0")

if [ "$NEW_JOB_COUNT" -lt 2 ]; then
    echo "ERROR: Expected 2 running jobs, found ${NEW_JOB_COUNT}"
    echo "Current jobs:"
    echo "$NEW_JOBS"
    echo ""
    echo "Deployment FAILED!"
    exit 1
fi

echo "✓ Deployment verified: ${NEW_JOB_COUNT} jobs running"
echo "$NEW_JOBS"

echo ""
echo "==================================================================="
echo "✓ Deployment successful!"
echo "==================================================================="
echo "New jobs:"
echo "$NEW_JOBS"
echo ""

exit 0
