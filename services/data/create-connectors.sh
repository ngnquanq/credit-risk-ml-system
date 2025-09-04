  #!/bin/bash
  echo "Creating Debezium connectors..."

  curl -X POST http://localhost:8083/connectors \
    -H "Content-Type: application/json" \
    -d '{
      "name": "postgres-connector",
      "config": {
        "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
        "database.hostname": "$OPS_DB_HOST",
        "database.port": "$OPS_DB_PORT",
        "database.user": "$OPS_DB_USER",
        "database.password": "$OPS_DB_PASSWORD",
        "database.dbname": "$OPS_DB_NAME",
        "database.server.name": "$CDC_TOPIC_PREFIX",
        "plugin.name": "$CDC_PLUGIN_NAME",
        "publication.name": "$CDC_PUBLICATION_NAME",
        "slot.name": "$CDC_SLOT_NAME",
        "table.include.list": "public.applications"
      }
    }'