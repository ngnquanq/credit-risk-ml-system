#!/usr/bin/env bash
set -euo pipefail

# K8s-adapted ClickHouse data loader
# Copies CSVs from host to ClickHouse pod and loads them into databases.
#
# Usage: bash platform/data/scripts/dwh/k8s_load_data.sh

NAMESPACE="data-services"
POD="clickhouse-server-0"
HOST_DATA_DIR="$(pwd)/data"
IN_POD_DIR="/var/lib/clickhouse/user_files"
FORMAT="CSVWithNames"
CLIENT_FLAGS="--date_time_input_format=best_effort --input_format_csv_empty_as_default=1"

ch() {
  kubectl exec -n "$NAMESPACE" "$POD" -- clickhouse-client $CLIENT_FLAGS -n --query "$1"
}

load_csv() {
  local db="$1" table="$2" csv_file="$3"
  local base
  base="$(basename "$csv_file")"

  echo ">>> Copying $base into pod..."
  kubectl cp "$csv_file" "${NAMESPACE}/${POD}:${IN_POD_DIR}/${base}"

  echo ">>> Creating table ${db}.${table} (schema inferred from CSV)..."
  local exists
  exists=$(ch "SELECT count() FROM system.tables WHERE database='${db}' AND name='${table}'")
  if (( exists == 0 )); then
    ch "CREATE TABLE ${db}.${table}
        ENGINE = MergeTree
        ORDER BY tuple()
        AS SELECT * FROM file('${base}', '${FORMAT}') LIMIT 0"
  else
    echo "    Table already exists, skipping CREATE"
  fi

  echo ">>> Inserting data from $base into ${db}.${table}..."
  ch "INSERT INTO ${db}.${table} SELECT * FROM file('${base}', '${FORMAT}')"

  local rows
  rows=$(ch "SELECT count() FROM ${db}.${table}")
  echo "    ✅ ${db}.${table}: ${rows} rows"
  echo ""
}

# Ensure user_files dir exists
kubectl exec -n "$NAMESPACE" "$POD" -- mkdir -p "$IN_POD_DIR"

# ── 1. Internal data (application_dwh) ──────────────────────────
echo "═══════════════════════════════════════════════"
echo "  Loading internal data → application_dwh"
echo "═══════════════════════════════════════════════"
ch "CREATE DATABASE IF NOT EXISTS application_dwh"

# Map CSV file → table name
declare -A INTERNAL_FILES=(
  ["application_train.csv"]="application_train"
  ["application_test.csv"]="application_test"
  ["previous_application.csv"]="previous_application"
  ["installments_payments.csv"]="installments_payments"
  ["POS_CASH_balance.csv"]="pos_cash_balance"
  ["credit_card_balance.csv"]="credit_card_balance"
)

for csv_file in "${!INTERNAL_FILES[@]}"; do
  full_path="${HOST_DATA_DIR}/${csv_file}"
  if [[ -f "$full_path" ]]; then
    load_csv "application_dwh" "${INTERNAL_FILES[$csv_file]}" "$full_path"
  else
    echo "Skip: $csv_file not found"
  fi
done

# ── 2. External/Bureau data (application_external) ──────────────
echo "═══════════════════════════════════════════════"
echo "  Loading external data → application_external"
echo "═══════════════════════════════════════════════"
ch "CREATE DATABASE IF NOT EXISTS application_external"

declare -A EXTERNAL_FILES=(
  ["application_ext.csv"]="external_score"
  ["bureau.csv"]="bureau"
  ["bureau_balance.csv"]="bureau_balance"
)

for csv_file in "${!EXTERNAL_FILES[@]}"; do
  full_path="${HOST_DATA_DIR}/${csv_file}"
  if [[ -f "$full_path" ]]; then
    load_csv "application_external" "${EXTERNAL_FILES[$csv_file]}" "$full_path"
  else
    echo "Skip: $csv_file not found"
  fi
done

# ── Summary ─────────────────────────────────────────────────────
echo "═══════════════════════════════════════════════"
echo "  Data loading complete! Summary:"
echo "═══════════════════════════════════════════════"
ch "SELECT database, name AS table, total_rows, formatReadableSize(total_bytes) AS size
    FROM system.tables
    WHERE database IN ('application_dwh', 'application_external')
    ORDER BY database, name
    FORMAT PrettyCompact"

echo ""
echo "✅ All done!"
