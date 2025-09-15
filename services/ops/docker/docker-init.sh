#!/bin/bash
set -eo pipefail

# Initialize the database
superset db upgrade

# Create admin user
superset fab create-admin \
    --username admin \
    --firstname Superset \
    --lastname Admin \
    --email admin@superset.com \
    --password admin || true

# Initialize Superset
superset init

# Load example data if requested
if [ "${SUPERSET_LOAD_EXAMPLES}" = "yes" ]; then
    superset load_examples
fi

echo "Superset initialization completed successfully!"