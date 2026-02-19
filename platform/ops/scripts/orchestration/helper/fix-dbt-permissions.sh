#!/bin/bash
# Fix permissions for ml_data_mart to work with both local user and Airflow containers
# Airflow containers run as UID 50000
# This script uses permissive 777 permissions for simplicity (dev/local environment)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ML_DATA_MART_DIR="$SCRIPT_DIR/../../../../../ml_data_mart"

echo "========================================="
echo "Fixing permissions for ml_data_mart directory"
echo "========================================="
echo "Directory: $ML_DATA_MART_DIR"
echo "Current user: $(whoami) (UID: $(id -u))"
echo ""

# Ensure specific directories exist
echo "Step 1: Creating necessary directories..."
mkdir -p "$ML_DATA_MART_DIR/logs"
mkdir -p "$ML_DATA_MART_DIR/target"
mkdir -p "$ML_DATA_MART_DIR/dbt_packages"

# Set permissive permissions on the entire ml_data_mart directory
# This allows both local user and container (UID 50000) to read/write
echo "Step 2: Setting permissive permissions (chmod 777)..."
echo "  Note: This is suitable for local development only!"

chmod -R 777 "$ML_DATA_MART_DIR" 2>/dev/null || {
    echo "  Permission denied, trying with sudo..."
    sudo chmod -R 777 "$ML_DATA_MART_DIR" || {
        echo "  ERROR: Failed to set permissions"
        exit 1
    }
}

echo ""
echo "========================================="
echo "✓ Permissions fixed successfully!"
echo "========================================="
echo ""
echo "All users can now read/write ml_data_mart directory."
echo "You can run dbt:"
echo "  - Locally: cd ml_data_mart && dbt debug"
echo "  - In Airflow: via DAGs or docker exec"
echo ""
echo "Final permissions:"
ls -la "$ML_DATA_MART_DIR" | head -15
