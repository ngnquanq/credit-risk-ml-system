#!/bin/bash
set -eo pipefail

# Install extra Python packages first (if requested)
if [ -n "${PIP_ADDITIONAL_REQUIREMENTS:-}" ]; then
    echo "Installing additional Python packages (init): ${PIP_ADDITIONAL_REQUIREMENTS}"
    if command -v pip3 >/dev/null 2>&1; then
        pip3 install --no-cache-dir ${PIP_ADDITIONAL_REQUIREMENTS} || true
    elif command -v pip >/dev/null 2>&1; then
        pip install --no-cache-dir ${PIP_ADDITIONAL_REQUIREMENTS} || true
    else
        python3 -m ensurepip --upgrade || true
        python3 -m pip install --no-cache-dir ${PIP_ADDITIONAL_REQUIREMENTS} || true
    fi
fi

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
