#!/usr/bin/env bash
set -euo pipefail

# Purpose: Load only the external/bureau CSVs into ClickHouse application_external database.
# Inputs (host):
#   - data/application_ext.csv      -> application_external.external_score
#   - data/bureau.csv               -> application_external.bureau
#   - data/bureau_balance.csv       -> application_external.bureau_balance
#
# This script mirrors logic from scripts/ch_autoload.sh but targets a different
# database and only these three files.

CH_CONTAINER="${CH_CONTAINER:-clickhouse_dwh}"
DB="${CH_DB:-application_external}"
HOST_DATA_DIR="$(pwd)/data"
IN_CONTAINER_DIR="/var/lib/clickhouse/user_files"   # must be user_files_path
FORMAT="CSVWithNames"

# Minimal client flags
CLIENT_FLAGS=(
  "--date_time_input_format=best_effort"
  "--input_format_csv_empty_as_default=1"
  "--send_logs_level=information"
)

CH_USER="${CH_USER:-default}"
CH_PASSWORD="${CH_PASSWORD:-}"

ch() {
  local auth_flags=()
  if [[ -n "$CH_USER" ]]; then auth_flags+=("--user" "$CH_USER"); fi
  if [[ -n "$CH_PASSWORD" ]]; then auth_flags+=("--password" "$CH_PASSWORD"); fi
  # Close stdin to avoid interactive hang; ensure client exits after query
  docker exec "$CH_CONTAINER" clickhouse-client "${auth_flags[@]}" "${CLIENT_FLAGS[@]}" -q "$1" </dev/null
}

sanitize_table() {
  echo "$1" | sed 's/[^a-zA-Z0-9]/_/g;s/_\{1,\}$//' | tr '[:upper:]' '[:lower:]'
}

in_container_file_exists(){ docker exec "$CH_CONTAINER" sh -lc "test -f \"$1\""; }
host_md5(){ md5sum "$1" | awk '{print $1}'; }
in_container_md5(){ docker exec "$CH_CONTAINER" sh -lc "md5sum \"$1\" | awk '{print \$1}'"; }
host_size(){ stat -c%s "$1"; }
cont_size(){ docker exec "$CH_CONTAINER" sh -lc "stat -c%s \"$1\""; }

# Prep: DB + load log + ensure user_files dir
ch "CREATE DATABASE IF NOT EXISTS ${DB}"
ch "CREATE TABLE IF NOT EXISTS ${DB}._load_log(
      table_name String, file_name String, bytes UInt64, md5 FixedString(32),
      loaded_at DateTime DEFAULT now()
    ) ENGINE=MergeTree ORDER BY (table_name, file_name, md5)"
docker exec "$CH_CONTAINER" sh -lc "mkdir -p ${IN_CONTAINER_DIR} && (command -v md5sum >/dev/null || (apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y coreutils >/dev/null 2>&1 || true))" >/dev/null 2>&1 || true

# Mapping: host file -> table name
declare -A FILE_TABLE_MAP=(
  ["application_ext.csv"]="external_score"
  ["bureau.csv"]="bureau"
  ["bureau_balance.csv"]="bureau_balance"
)

any_found=false
for base in "${!FILE_TABLE_MAP[@]}"; do
  host_file="${HOST_DATA_DIR}/${base}"
  if [[ -f "$host_file" ]]; then
    any_found=true
  fi
done

if [[ "$any_found" == false ]]; then
  echo "No target CSVs found in ${HOST_DATA_DIR} (expected: ${!FILE_TABLE_MAP[@]})"
  exit 0
fi

for base in "${!FILE_TABLE_MAP[@]}"; do
  host_file="${HOST_DATA_DIR}/${base}"
  table="$(sanitize_table "${FILE_TABLE_MAP[$base]}")"
  cont_file="${IN_CONTAINER_DIR}/${base}"

  if [[ ! -f "$host_file" ]]; then
    echo "Skip missing file: $base"
    continue
  fi

  # Copy into user_files if changed (size+md5)
  h_md5=$(host_md5 "$host_file"); h_size=$(host_size "$host_file")
  if in_container_file_exists "$cont_file"; then
    c_size=$(cont_size "$cont_file" || echo 0)
    if [[ "$c_size" -eq "$h_size" ]] && [[ "$(in_container_md5 "$cont_file")" == "$h_md5" ]]; then
      echo "Skip copy: same file exists — $base"
    else
      echo "Copy: $base"
      docker cp "$host_file" "${CH_CONTAINER}:${cont_file}"
    fi
  else
    echo "Copy: $base"
    docker cp "$host_file" "${CH_CONTAINER}:${cont_file}"
  fi

  # Idempotency: skip if this exact file already loaded for this table
  already_loaded=$(ch "SELECT count() FROM ${DB}._load_log WHERE table_name='${table}' AND file_name='${base}' AND md5='${h_md5}'")
  if (( already_loaded > 0 )); then
    echo "Skip ingest (already logged): ${DB}.${table} <= ${base}"
    continue
  fi

  echo ">>> Processing ${base} -> ${DB}.${table}"

  # CREATE structure ONLY (infer schema from CSV), then INSERT data
  exists=$(ch "SELECT count() FROM system.tables WHERE database='${DB}' AND name='${table}'")
  if (( exists == 0 )); then
    echo "Creating empty table (schema inferred from ${base})"
    ch "CREATE TABLE ${DB}.${table}
        ENGINE = MergeTree
        ORDER BY tuple()
        AS SELECT * FROM file('${base}', '${FORMAT}') LIMIT 0"
  else
    echo "Table exists; will insert data"
  fi

  echo "Inserting data from ${base}"
  ch "INSERT INTO ${DB}.${table}
      SELECT * FROM file('${base}', '${FORMAT}')"

  # Log this load (prevents double-insert of same file)
  ch "INSERT INTO ${DB}._load_log(table_name, file_name, bytes, md5)
      VALUES ('${table}', '${base}', ${h_size}, '${h_md5}')"

  rows=$(ch "SELECT total_rows FROM system.tables WHERE database='${DB}' AND name='${table}'")
  echo "Rows now in ${DB}.${table}: ${rows}"
done

echo "Done."
