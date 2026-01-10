#!/bin/bash
# Flink Job Rollback Script
# Called when deployment fails to restore previous working state

set -euo pipefail

BACKUP_DIR="${1:-/var/jenkins_home/backups/latest}"
FLINK_REST_API="${FLINK_REST_API:-http://flink-jobmanager:8081}"

echo "==================================================================="
echo "Flink Job Rollback Script"
echo "==================================================================="
echo "Restoring from backup: ${BACKUP_DIR}"
echo "==================================================================="

# Check if backup directory exists
if [ ! -d "$BACKUP_DIR" ]; then
    echo "ERROR: Backup directory not found: ${BACKUP_DIR}"
    echo "Cannot perform rollback!"
    exit 1
fi

# Function: Get running job IDs
get_running_jobs() {
    curl -s "${FLINK_REST_API}/jobs/overview" | \
        jq -r '.jobs[] | select(.state=="RUNNING") | .jid' 2>/dev/null || echo ""
}

# Step 1: Cancel current (broken) jobs
echo ""
echo "Step 1: Cancelling current jobs..."
CURRENT_JOBS=$(get_running_jobs)

if [ -n "$CURRENT_JOBS" ]; then
    while IFS= read -r JOB_ID; do
        if [ -n "$JOB_ID" ]; then
            echo "Cancelling job ${JOB_ID}..."
            curl -s -X PATCH "${FLINK_REST_API}/jobs/${JOB_ID}?mode=cancel" || echo "Warning: cancel failed"
        fi
    done <<< "$CURRENT_JOBS"
    sleep 5
else
    echo "No running jobs to cancel"
fi

# Step 2: Restore previous Docker image
echo ""
echo "Step 2: Restoring previous Docker image..."

if [ -f "${BACKUP_DIR}/deployed_image.txt" ]; then
    PREV_IMAGE=$(cat "${BACKUP_DIR}/deployed_image.txt")
    echo "Previous image: ${PREV_IMAGE}"

    # Update docker-compose to use previous image
    sed -i.bak "s|image: hc-flink-jobs:.*|image: ${PREV_IMAGE}|g" \
        services/data/docker-compose.flink.yml

    echo "✓ Restored docker-compose.flink.yml to use ${PREV_IMAGE}"
else
    echo "WARNING: No previous image tag found in backup"
fi

# Step 3: Re-submit old jobs
echo ""
echo "Step 3: Re-submitting previous jobs..."

docker compose -f services/data/docker-compose.flink.yml up -d flink-job-pii flink-job-bureau

echo "Waiting for job submission..."
sleep 15

# Step 4: Verify rollback succeeded
echo ""
echo "Step 4: Verifying rollback..."
sleep 10

RESTORED_JOBS=$(get_running_jobs)
RESTORED_COUNT=$(echo "$RESTORED_JOBS" | grep -c . || echo "0")

if [ "$RESTORED_COUNT" -lt 2 ]; then
    echo "ERROR: Rollback verification failed! Only ${RESTORED_COUNT} jobs running"
    echo "Manual intervention required!"
    exit 1
fi

echo "✓ Rollback verified: ${RESTORED_COUNT} jobs running"
echo "$RESTORED_JOBS"

echo ""
echo "==================================================================="
echo "✓ Rollback successful!"
echo "==================================================================="

exit 0
