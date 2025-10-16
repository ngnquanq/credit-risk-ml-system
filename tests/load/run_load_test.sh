#!/bin/bash
# Load test runner script with pre-configured scenarios

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default configuration
API_HOST="${API_HOST:-http://localhost:8000}"
REPORT_DIR="reports"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Create reports directory
mkdir -p "$REPORT_DIR"

echo -e "${BLUE}=================================${NC}"
echo -e "${BLUE}  Home Credit Load Test Runner  ${NC}"
echo -e "${BLUE}=================================${NC}"
echo ""

# Check if locust is installed
if ! command -v locust &> /dev/null; then
    echo -e "${RED}✗ Locust is not installed${NC}"
    echo "  Install with: pip install locust"
    exit 1
fi

echo -e "${GREEN}✓ Locust is installed${NC}"
echo -e "${GREEN}✓ API Host: $API_HOST${NC}"
echo -e "${GREEN}✓ Report directory: $REPORT_DIR${NC}"
echo ""

# Function to run test scenario
run_scenario() {
    local name=$1
    local users=$2
    local spawn_rate=$3
    local run_time=$4

    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}  Scenario: $name${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo "  Users: $users"
    echo "  Spawn Rate: $spawn_rate users/sec"
    echo "  Duration: $run_time"
    echo ""

    local report_prefix="${REPORT_DIR}/${name}_${TIMESTAMP}"

    locust -f tests/locustfile.py \
        --host="$API_HOST" \
        --users "$users" \
        --spawn-rate "$spawn_rate" \
        --run-time "$run_time" \
        --headless \
        --html "${report_prefix}.html" \
        --csv "${report_prefix}"

    echo ""
    echo -e "${GREEN}✓ Test completed!${NC}"
    echo -e "${GREEN}  HTML Report: ${report_prefix}.html${NC}"
    echo -e "${GREEN}  CSV Data: ${report_prefix}_stats.csv${NC}"
    echo ""
}

# Parse command line arguments
case "${1:-smoke}" in
    smoke)
        echo "Running SMOKE TEST (quick validation)..."
        run_scenario "smoke_test" 10 5 "1m"
        ;;

    light)
        echo "Running LIGHT LOAD TEST..."
        run_scenario "light_load" 50 10 "3m"
        ;;

    medium)
        echo "Running MEDIUM LOAD TEST..."
        run_scenario "medium_load" 100 20 "5m"
        ;;

    heavy)
        echo "Running HEAVY LOAD TEST..."
        run_scenario "heavy_load" 200 30 "10m"
        ;;

    stress)
        echo "Running STRESS TEST (push to limits)..."
        run_scenario "stress_test" 500 50 "15m"
        ;;

    spike)
        echo "Running SPIKE TEST..."
        echo "  Phase 1: Normal load (50 users, 2m)"
        run_scenario "spike_test_normal" 50 10 "2m"

        echo ""
        echo "  Phase 2: Spike load (300 users, 3m)"
        run_scenario "spike_test_spike" 300 100 "3m"

        echo ""
        echo "  Phase 3: Recovery (50 users, 2m)"
        run_scenario "spike_test_recovery" 50 10 "2m"
        ;;

    endurance)
        echo "Running ENDURANCE TEST (30 minutes)..."
        run_scenario "endurance_test" 100 20 "30m"
        ;;

    custom)
        if [ -z "$2" ] || [ -z "$3" ] || [ -z "$4" ]; then
            echo -e "${RED}Usage: $0 custom <users> <spawn_rate> <run_time>${NC}"
            echo "Example: $0 custom 150 25 10m"
            exit 1
        fi
        run_scenario "custom_test" "$2" "$3" "$4"
        ;;

    all)
        echo "Running ALL TEST SCENARIOS..."
        run_scenario "01_smoke" 10 5 "1m"
        run_scenario "02_light" 50 10 "3m"
        run_scenario "03_medium" 100 20 "5m"
        run_scenario "04_heavy" 200 30 "10m"
        ;;

    *)
        echo -e "${RED}Unknown scenario: $1${NC}"
        echo ""
        echo "Available scenarios:"
        echo "  smoke      - Quick validation (10 users, 1min)"
        echo "  light      - Light load (50 users, 3min)"
        echo "  medium     - Medium load (100 users, 5min)"
        echo "  heavy      - Heavy load (200 users, 10min)"
        echo "  stress     - Stress test (500 users, 15min)"
        echo "  spike      - Spike test (50→300→50 users)"
        echo "  endurance  - Endurance test (100 users, 30min)"
        echo "  custom     - Custom (specify users, rate, time)"
        echo "  all        - Run all scenarios"
        echo ""
        echo "Usage: $0 [scenario]"
        echo "Example: $0 medium"
        echo "Example: $0 custom 150 25 10m"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Load Test Complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "Reports saved to: $REPORT_DIR/"
echo ""
