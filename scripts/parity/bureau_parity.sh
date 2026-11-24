#!/usr/bin/env bash
# Compare the dbt bureau features (training side) with the Flink UDF (serving side) on a sample of customers.
# Needs kubectl and minikube on the PATH and the cluster running (make k8s-load-dwh has been done).
#   SAMPLE=300 ./scripts/parity/bureau_parity.sh
set -euo pipefail

SAMPLE="${SAMPLE:-300}"
PROFILE="${MINIKUBE_PROFILE:-mlops}"
IMAGE="flink-pyflink:${IMAGE_TAG:-dev}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

ch() { kubectl exec -n data-services clickhouse-server-0 -- clickhouse-client --output_format_json_quote_64bit_integers=0 -q "$1"; }

IDS="$(ch "select toString(SK_ID_CURR) from application_mart.mart_bureau_features order by cityHash64(SK_ID_CURR) limit ${SAMPLE} format TSV" | paste -sd, -)"
ch "select * from application_external.bureau where SK_ID_CURR in (${IDS}) format JSONEachRow" > "$WORK/bureau.jsonl"
ch "select SK_ID_BUREAU, MONTHS_BALANCE, STATUS from application_external.bureau_balance where SK_ID_BUREAU in (select SK_ID_BUREAU from application_external.bureau where SK_ID_CURR in (${IDS})) format JSONEachRow" > "$WORK/balance.jsonl"
ch "select * from application_mart.mart_bureau_features where SK_ID_CURR in (${IDS}) format JSONEachRow" > "$WORK/mart.jsonl"

python3 - "$WORK" "$IDS" > "$WORK/all.json" <<'PY'
import json, sys
work, ids = sys.argv[1], sys.argv[2].split(",")
rows = lambda name: [json.loads(line) for line in open(f"{work}/{name}.jsonl") if line.strip()]
print(json.dumps({"ids": ids, "bureau": rows("bureau"), "balance": rows("balance"), "mart": rows("mart")}))
PY

eval "$(minikube -p "$PROFILE" docker-env)"
docker run --rm -i --entrypoint python3 "$IMAGE" -c "$(cat "$HERE/bureau_parity.py")" < "$WORK/all.json"
