#!/bin/bash
# Setup load testing dependencies in conda environment

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}  Load Test Setup${NC}"
echo -e "${BLUE}================================${NC}"
echo ""

# Check if conda environment exists
if conda env list | grep -q "dataEngineer-env"; then
    echo -e "${GREEN}✓ Found conda environment: dataEngineer-env${NC}"
else
    echo "✗ Conda environment 'dataEngineer-env' not found"
    exit 1
fi

# Activate environment and install dependencies
echo "Installing load test dependencies..."
conda run -n dataEngineer-env pip install \
    locust \
    psycopg2-binary \
    kafka-python

echo ""
echo -e "${GREEN}✓ Dependencies installed in dataEngineer-env${NC}"
echo ""
echo "To run load test:"
echo "  conda activate dataEngineer-env"
echo "  ./tests/run_e2e_load_test.sh"
echo ""
