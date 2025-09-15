#!/bin/bash
set -eo pipefail

# Superset docker bootstrap script
case "${1}" in
  app-gunicorn)
    exec gunicorn \
        --bind "0.0.0.0:${SUPERSET_PORT:-8088}" \
        --access-logfile '-' \
        --error-logfile '-' \
        --workers 1 \
        --worker-class gthread \
        --threads 20 \
        --timeout 60 \
        --limit-request-line 0 \
        --limit-request-field_size 0 \
        --preload \
        "superset.app:create_app()"
    ;;
  worker)
    exec celery --app=superset.tasks.celery_app:app worker
    ;;
  beat)
    exec celery --app=superset.tasks.celery_app:app beat --pidfile=
    ;;
  *)
    echo "Unknown command: ${1}"
    exit 1
    ;;
esac