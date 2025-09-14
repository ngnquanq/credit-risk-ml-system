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

# Create test script to verify ClickHouse connectivity
cat > "$SCRIPT_DIR/test-clickhouse-connection.py" << 'EOF'
#!/usr/bin/env python3
"""
Test ClickHouse connectivity from Spark

Usage:
  spark-submit --master spark://spark-master:7077 \
    services/data/spark/test-clickhouse-connection.py
"""

from pyspark.sql import SparkSession
import sys

def test_clickhouse_connection():
    """Test connection to ClickHouse from Spark."""
    
    print("🔌 Testing ClickHouse connection from Spark...")
    
    # Create Spark session
    spark = SparkSession.builder \
        .appName("ClickHouse-Connection-Test") \
        .config("spark.sql.execution.arrow.pyspark.enabled", "true") \
        .getOrCreate()
    
    try:
        # Test connection to ClickHouse
        clickhouse_url = "jdbc:clickhouse://clickhouse_dwh:8123/application_mart"
        
        # Simple query to test connectivity
        df = spark.read \
            .format("jdbc") \
            .option("url", clickhouse_url) \
            .option("dbtable", "(SELECT 'Hello from ClickHouse!' as message, now() as timestamp) AS test") \
            .option("driver", "com.clickhouse.jdbc.ClickHouseDriver") \
            .option("user", "default") \
            .option("password", "") \
            .load()
        
        print("📊 Test query result:")
        df.show()
        
        # Test application_mart database access
        try:
            tables_df = spark.read \
                .format("jdbc") \
                .option("url", clickhouse_url) \
                .option("dbtable", "(SHOW TABLES FROM application_mart) AS tables") \
                .option("driver", "com.clickhouse.jdbc.ClickHouseDriver") \
                .option("user", "default") \
                .option("password", "") \
                .load()
            
            print("📋 Tables in application_mart:")
            tables_df.show()
            
        except Exception as e:
            print(f"⚠️  Could not list tables in application_mart: {e}")
            print("   This is normal if the database doesn't exist yet")
        
        print("✅ ClickHouse connection successful!")
        return True
        
    except Exception as e:
        print(f"❌ ClickHouse connection failed: {e}")
        return False
        
    finally:
        spark.stop()

if __name__ == "__main__":
    success = test_clickhouse_connection()
    sys.exit(0 if success else 1)
EOF

chmod +x "$SCRIPT_DIR/test-clickhouse-connection.py"
echo "🧪 Created test script: $SCRIPT_DIR/test-clickhouse-connection.py"

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
echo "3. Run training: spark-submit --master spark://spark-master:7077 application/training/spark_clickhouse_training.py"
echo ""
echo "📁 Files created:"
echo "   - $SPARK_JARS_DIR/$CLICKHOUSE_JDBC_JAR"
echo "   - $SPARK_CONF_DIR/spark-defaults.conf"
echo "   - $SCRIPT_DIR/test-clickhouse-connection.py"