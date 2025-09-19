#!/bin/bash
"""
Setup ClickHouse JDBC Driver for Spark Cluster

This script downloads and configures the ClickHouse JDBC driver
for use with your Spark cluster infrastructure.

Usage:
  ./services/data/spark/setup-clickhouse-jdbc.sh
"""

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SPARK_JARS_DIR="$SCRIPT_DIR/jars"
CLICKHOUSE_JDBC_VERSION="0.4.6"
CLICKHOUSE_JDBC_JAR="clickhouse-jdbc-${CLICKHOUSE_JDBC_VERSION}-all.jar"
CLICKHOUSE_JDBC_URL="https://repo1.maven.org/maven2/com/clickhouse/clickhouse-jdbc/${CLICKHOUSE_JDBC_VERSION}/${CLICKHOUSE_JDBC_JAR}"

echo "🚀 Setting up ClickHouse JDBC driver for Spark..."

# Create jars directory if it doesn't exist
mkdir -p "$SPARK_JARS_DIR"

# Download ClickHouse JDBC driver if not present
if [ ! -f "$SPARK_JARS_DIR/$CLICKHOUSE_JDBC_JAR" ]; then
    echo "📥 Downloading ClickHouse JDBC driver..."
    curl -L -o "$SPARK_JARS_DIR/$CLICKHOUSE_JDBC_JAR" "$CLICKHOUSE_JDBC_URL"
    echo "✅ Downloaded: $CLICKHOUSE_JDBC_JAR"
else
    echo "✅ ClickHouse JDBC driver already exists"
fi

# Verify the JAR file
if [ -f "$SPARK_JARS_DIR/$CLICKHOUSE_JDBC_JAR" ]; then
    JAR_SIZE=$(stat -f%z "$SPARK_JARS_DIR/$CLICKHOUSE_JDBC_JAR" 2>/dev/null || stat -c%s "$SPARK_JARS_DIR/$CLICKHOUSE_JDBC_JAR")
    echo "📊 JAR file size: $JAR_SIZE bytes"
    
    # Basic validation - should be > 1MB
    if [ "$JAR_SIZE" -gt 1048576 ]; then
        echo "✅ JAR file appears valid"
    else
        echo "❌ JAR file seems too small, may be corrupted"
        exit 1
    fi
else
    echo "❌ Failed to download ClickHouse JDBC driver"
    exit 1
fi

# Create Spark configuration for ClickHouse
SPARK_CONF_DIR="$SCRIPT_DIR/conf"
mkdir -p "$SPARK_CONF_DIR"

cat > "$SPARK_CONF_DIR/spark-defaults.conf" << EOF
# ClickHouse JDBC Configuration for Spark
spark.jars                    $SPARK_JARS_DIR/$CLICKHOUSE_JDBC_JAR
spark.driver.extraClassPath   $SPARK_JARS_DIR/$CLICKHOUSE_JDBC_JAR
spark.executor.extraClassPath $SPARK_JARS_DIR/$CLICKHOUSE_JDBC_JAR

# Performance tuning for JDBC operations
spark.sql.execution.arrow.pyspark.enabled      true
spark.sql.adaptive.enabled                     true
spark.sql.adaptive.coalescePartitions.enabled  true
spark.sql.adaptive.advisoryPartitionSizeInBytes 64MB
spark.sql.adaptive.skewJoin.enabled            true

# Memory optimization
spark.executor.memory         2g
spark.driver.memory           2g
spark.executor.cores          2
spark.sql.execution.arrow.maxRecordsPerBatch   10000
EOF

echo "📝 Created Spark configuration: $SPARK_CONF_DIR/spark-defaults.conf"


# Create directory structure for Spark apps
mkdir -p "$SCRIPT_DIR/apps"
mkdir -p "$SCRIPT_DIR/data"
mkdir -p "$SCRIPT_DIR/logs"
mkdir -p "$SCRIPT_DIR/notebooks"

echo ""
echo "🎉 ClickHouse JDBC setup complete!"
echo ""
echo "Next steps:"
echo "1. Start your Spark cluster: docker-compose -f services/data/docker-compose.batch.yml up -d"
echo "2. Test connection: spark-submit --master spark://spark-master:7077 services/data/spark/test-clickhouse-connection.py"
echo ""
echo "📁 Files created:"
echo "   - $SPARK_JARS_DIR/$CLICKHOUSE_JDBC_JAR"
echo "   - $SPARK_CONF_DIR/spark-defaults.conf"
