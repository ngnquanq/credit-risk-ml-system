#!/usr/bin/env bash
set -euo pipefail

CH_CONTAINER="clickhouse_dwh"
DB="application_dwh"
HOST_DATA_DIR="$(pwd)/data"
IN_CONTAINER_DIR="/var/lib/clickhouse/user_files"   # must be user_files_path
FORMAT="CSVWithNames"
CH_USER="${CH_USER:-default}"
CH_PASSWORD="${CH_PASSWORD:-}"

# Minimal client flags (avoid duplicate --set issues)
CLIENT_FLAGS=(
  "--date_time_input_format=best_effort"
  "--input_format_csv_empty_as_default=1"
  "--send_logs_level=information"   # progress/logs
)

ch() {
      local auth=()
      [[ -n "$CH_USER" ]] && auth+=(--user "$CH_USER")
      [[ -n "$CH_PASSWORD" ]] && auth+=(--password "$CH_PASSWORD")
      # Close stdin to avoid interactive hang; ensure client exits after query
      docker exec "$CH_CONTAINER" clickhouse-client "${auth[@]}" "${CLIENT_FLAGS[@]}" -q "$1" </dev/null
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

shopt -s nullglob
CSV_LIST=("${HOST_DATA_DIR}"/*.csv)
if [ ${#CSV_LIST[@]} -eq 0 ]; then
  echo \"No CSVs found in ${HOST_DATA_DIR}\"
  exit 0
fi

for host_file in "${CSV_LIST[@]}"; do
  base="$(basename "$host_file")"            # e.g. application_train.csv
  name_no_ext="${base%.csv}"
  table="$(sanitize_table "$name_no_ext")"
  cont_file="${IN_CONTAINER_DIR}/${base}"    # absolute path inside container

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
    # file('...') path must be RELATIVE to user_files_path
    ch "CREATE TABLE ${DB}.${table}
        ENGINE = MergeTree
        ORDER BY tuple()
        AS SELECT * FROM file('${base}', '${FORMAT}') LIMIT 0"
    # LIMIT 0 -> create empty table with inferred schema; load happens next. :contentReference[oaicite:2]{index=2}
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
