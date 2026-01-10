#!/bin/bash
# Fix permissions for Airflow orchestration directories
# The airflow-init container runs chown to UID 50000 on bind-mounted directories
# This script sets permissive 777 permissions so both local user and Airflow can edit files

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AIRFLOW_ORCHESTRATION_DIR="$SCRIPT_DIR/.."

echo "========================================="
echo "Fixing Airflow orchestration permissions"
echo "========================================="
echo "Directory: $AIRFLOW_ORCHESTRATION_DIR"
echo "Current user: $(whoami) (UID: $(id -u))"
echo "Airflow UID: 50000"
echo ""

# Fix Airflow orchestration directories permissions
echo "Setting permissive permissions (chmod 777)..."
echo "  Note: This is suitable for local development only!"
echo ""

for dir in dags logs plugins config include data; do
    if [ -d "$AIRFLOW_ORCHESTRATION_DIR/$dir" ]; then
        echo "  Processing $dir..."
        chmod -R 777 "$AIRFLOW_ORCHESTRATION_DIR/$dir" 2>/dev/null || {
            echo "    Permission denied, trying with sudo..."
            sudo chmod -R 777 "$AIRFLOW_ORCHESTRATION_DIR/$dir" || {
                echo "    WARNING: Could not set permissions on $dir"
                continue
            }
        }
        echo "    ✓ $dir permissions set"
    fi
done

echo ""
echo "========================================="
echo "✓ Permissions fixed successfully!"
echo "========================================="
echo ""
echo "You can now edit Airflow DAGs and configuration files locally."
echo ""
echo "Final permissions:"
ls -la "$AIRFLOW_ORCHESTRATION_DIR" | grep -E "dags|logs|plugins|config|include"
