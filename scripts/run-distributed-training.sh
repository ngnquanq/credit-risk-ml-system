#!/bin/bash
"""
Quick Start Script for Distributed ML Training

This script orchestrates the full distributed training pipeline:
1. Sets up ClickHouse JDBC connectivity
2. Starts Spark cluster
3. Runs distributed ML training
4. Integrates with MLflow registry

Usage:
  ./scripts/run-distributed-training.sh [OPTIONS]

Options:
  --sample FRACTION    Sample fraction of data (default: 1.0)
  --experiment NAME    MLflow experiment name (default: credit-risk-clickhouse)
  --stage STAGE        Model stage transition (default: none)
  --help              Show this help
"""

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Default values
SAMPLE_FRACTION=1.0
EXPERIMENT_NAME="credit-risk-clickhouse"
MODEL_NAME="credit_risk_model_spark"
STAGE=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --sample)
            SAMPLE_FRACTION="$2"
            shift 2
            ;;
        --experiment)
            EXPERIMENT_NAME="$2"
            shift 2
            ;;
        --stage)
            STAGE="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --sample FRACTION    Sample fraction of data (default: 1.0)"
            echo "  --experiment NAME    MLflow experiment name (default: credit-risk-clickhouse)"
            echo "  --stage STAGE        Model stage transition (default: none)"
            echo "  --help              Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

cd "$PROJECT_ROOT"

echo "🚀 Starting Distributed ML Training Pipeline"
echo "================================================"
echo "Sample fraction: $SAMPLE_FRACTION"
echo "Experiment: $EXPERIMENT_NAME"
echo "Model name: $MODEL_NAME"
echo "Stage: ${STAGE:-none}"
echo ""

# Step 1: Setup ClickHouse JDBC driver
echo "📦 Step 1: Setting up ClickHouse JDBC driver..."
if [ ! -f "services/data/spark/setup-clickhouse-jdbc.sh" ]; then
    echo "❌ JDBC setup script not found. Please ensure the script exists."
    exit 1
fi

bash services/data/spark/setup-clickhouse-jdbc.sh

# Step 2: Start required infrastructure
echo ""
echo "🏗️  Step 2: Starting infrastructure services..."

# Check if Docker network exists
if ! docker network ls | grep -q "hc-network"; then
    echo "Creating Docker network: hc-network"
    docker network create hc-network
fi

# Start ClickHouse (data warehouse)
echo "Starting ClickHouse data warehouse..."
docker-compose -f services/data/docker-compose.warehouse.yml up -d ch-server

# Wait for ClickHouse to be ready
echo "⏳ Waiting for ClickHouse to be ready..."
for i in {1..30}; do
    if curl -s "http://localhost:8123/?query=SELECT%201" > /dev/null 2>&1; then
        echo "✅ ClickHouse is ready"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "❌ ClickHouse failed to start within 30 seconds"
        exit 1
    fi
    sleep 1
done

# Start MLflow (if not running)
echo "Checking MLflow registry..."
if ! docker ps | grep -q mlflow; then
    echo "Starting MLflow registry..."
    docker-compose -f services/ml/docker-compose.registry.yml up -d
    
    # Wait for MLflow
    echo "⏳ Waiting for MLflow to be ready..."
    for i in {1..30}; do
        if curl -s "http://localhost:5000" > /dev/null 2>&1; then
            echo "✅ MLflow is ready"
            break
        fi
        if [ $i -eq 30 ]; then
            echo "❌ MLflow failed to start within 30 seconds"
            exit 1
        fi
        sleep 2
    done
fi

# Start Spark cluster
echo "Starting Spark cluster..."
docker-compose -f services/data/docker-compose.batch.yml up -d

# Wait for Spark master to be ready
echo "⏳ Waiting for Spark cluster to be ready..."
for i in {1..60}; do
    if curl -s "http://localhost:8080" > /dev/null 2>&1; then
        echo "✅ Spark cluster is ready"
        break
    fi
    if [ $i -eq 60 ]; then
        echo "❌ Spark cluster failed to start within 60 seconds"
        exit 1
    fi
    sleep 1
done

# Step 3: Test connectivity
echo ""
echo "🧪 Step 3: Testing ClickHouse connectivity from Spark..."
docker exec spark_master spark-submit \
    --master spark://spark-master:7077 \
    --executor-memory 1g \
    --driver-memory 1g \
    /opt/spark-apps/test-clickhouse-connection.py || {
    echo "⚠️  ClickHouse connectivity test failed, but continuing..."
}

# Step 4: Run distributed training
echo ""
echo "🤖 Step 4: Running distributed ML training..."

# Set MLflow environment
export MLFLOW_TRACKING_URI="http://localhost:5000"
export MLFLOW_S3_ENDPOINT_URL="http://localhost:9006"
export AWS_ACCESS_KEY_ID="minio_user"
export AWS_SECRET_ACCESS_KEY="changeme123"

# Build spark-submit command
SPARK_SUBMIT_CMD="docker exec spark_master spark-submit \
    --master spark://spark-master:7077 \
    --executor-memory 2g \
    --driver-memory 2g \
    --executor-cores 2 \
    --num-executors 2 \
    --conf spark.sql.adaptive.enabled=true \
    --conf spark.sql.adaptive.coalescePartitions.enabled=true \
    --py-files /opt/spark-apps/application/training/spark_clickhouse_training.py \
    /opt/spark-apps/application/training/spark_clickhouse_training.py"

# Add command arguments
SPARK_SUBMIT_CMD="$SPARK_SUBMIT_CMD --experiment '$EXPERIMENT_NAME'"
SPARK_SUBMIT_CMD="$SPARK_SUBMIT_CMD --register-name '$MODEL_NAME'"
SPARK_SUBMIT_CMD="$SPARK_SUBMIT_CMD --sample $SAMPLE_FRACTION"

if [ -n "$STAGE" ]; then
    SPARK_SUBMIT_CMD="$SPARK_SUBMIT_CMD --stage '$STAGE'"
fi

echo "Running training command:"
echo "$SPARK_SUBMIT_CMD"
echo ""

# Execute training
eval "$SPARK_SUBMIT_CMD"

TRAINING_EXIT_CODE=$?

# Step 5: Show results
echo ""
echo "📊 Step 5: Training Results"
echo "================================================"

if [ $TRAINING_EXIT_CODE -eq 0 ]; then
    echo "✅ Distributed training completed successfully!"
    echo ""
    echo "🔗 Access URLs:"
    echo "   Spark Master UI:     http://localhost:8080"
    echo "   Spark History Server: http://localhost:18080"
    echo "   MLflow UI:           http://localhost:5000"
    echo "   Jupyter Notebook:    http://localhost:8888 (token: spark_notebook_token)"
    echo ""
    echo "📋 Next steps:"
    echo "   1. Check MLflow UI for model metrics and artifacts"
    echo "   2. Review training logs in Spark UI"
    echo "   3. Test model serving with BentoML"
else
    echo "❌ Distributed training failed with exit code: $TRAINING_EXIT_CODE"
    echo ""
    echo "🔍 Debugging steps:"
    echo "   1. Check Spark Master logs: docker logs spark_master"
    echo "   2. Check ClickHouse connectivity: docker logs clickhouse_dwh"
    echo "   3. Verify data exists in application_mart database"
    echo ""
    exit $TRAINING_EXIT_CODE
fi

echo ""
echo "🎉 Distributed ML Training Pipeline Complete!"