#!/usr/bin/env bash
# Restore the demo applications, decisions and notes in the local stack (E2E runs change them).
# The audit trail is append-only and is left as it is.
set -euo pipefail
cd "$(dirname "$0")"
docker compose exec -T postgres psql -q -U ops_admin -d operations -v ON_ERROR_STOP=1 \
  -c "SET lock_timeout = '10s'" \
  -c "TRUNCATE case_note, application_status_log, policy_change, loan_applications RESTART IDENTITY CASCADE" \
  -f /docker-entrypoint-initdb.d/03-demo-data.sql
echo "demo data reset"
